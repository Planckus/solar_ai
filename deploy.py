#!/usr/bin/env python3
"""Deploy battery_arbitrage integration + Lovelace dashboard to Home Assistant.

Usage:
    python3 deploy.py [--dashboard-only]

Requirements:
    pip install websockets PyYAML
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

import yaml

# ── Configuration ─────────────────────────────────────────────────────────────

HA_URL = "http://192.168.1.2:8123"
HA_WS = "ws://192.168.1.2:8123/api/websocket"
MAC_IP = "192.168.1.50"   # Mac LAN address visible from HA host
HTTP_PORT = 8765
TARBALL_NAME = "battery_arbitrage.tar.gz"

# Token: read from Claude Desktop config
def _read_token() -> str:
    cfg_path = Path(os.path.expanduser(
        "~/Library/Application Support/Claude/claude_desktop_config.json"
    ))
    if cfg_path.exists():
        with open(cfg_path) as f:
            cfg = json.load(f)
        # Walk the env sections to find HASS_TOKEN
        for server in cfg.get("mcpServers", {}).values():
            token = server.get("env", {}).get("HASS_TOKEN")
            if token:
                return token
    token = os.environ.get("HASS_TOKEN", "")
    if not token:
        raise RuntimeError(
            "HASS_TOKEN not found in Claude config or environment.\n"
            "Set it with:  export HASS_TOKEN=<your-long-lived-token>"
        )
    return token


HASS_TOKEN = _read_token()

REPO_ROOT = Path(__file__).parent
INTEGRATION_SRC = REPO_ROOT / "custom_components" / "battery_arbitrage"
DASHBOARD_YAML = REPO_ROOT / "dashboard" / "battery_arbitrage_dashboard.yaml"

DASHBOARD_URL_PATH = "battery-arbitrage"
DASHBOARD_TITLE = "Battery Arbitrage"
DASHBOARD_ICON = "mdi:battery-charging"


# ── Helpers ────────────────────────────────────────────────────────────────────

async def ws_auth(ws):
    """Authenticate on a fresh WebSocket connection."""
    import websockets
    msg = json.loads(await ws.recv())
    assert msg["type"] == "auth_required", f"Unexpected: {msg}"
    await ws.send(json.dumps({"type": "auth", "access_token": HASS_TOKEN}))
    msg = json.loads(await ws.recv())
    assert msg["type"] == "auth_ok", f"Auth failed: {msg}"


async def ws_send_recv(ws, payload: dict, msg_id: int) -> dict:
    payload["id"] = msg_id
    await ws.send(json.dumps(payload))
    while True:
        raw = json.loads(await ws.recv())
        if raw.get("id") == msg_id:
            return raw


async def get_ingress_session() -> tuple[str, str]:
    """Return (ingress_url, session_token) for the File Editor add-on."""
    import websockets
    async with websockets.connect(HA_WS) as ws:
        await ws_auth(ws)

        # Get ingress URL for File Editor (core_configurator)
        info = await ws_send_recv(ws, {
            "type": "supervisor/api",
            "endpoint": "/addons/core_configurator/info",
            "method": "get",
        }, 1)
        # HA supervisor API may nest result as data or directly
        result = info.get("result", {})
        ingress_url = result.get("ingress_url") or result.get("data", {}).get("ingress_url")
        if not ingress_url:
            raise RuntimeError(f"Could not find ingress_url in response: {info}")

        # Create ingress session
        sess = await ws_send_recv(ws, {
            "type": "supervisor/api",
            "endpoint": "/ingress/session",
            "method": "post",
        }, 2)
        sess_result = sess.get("result", {})
        session_token = (
            sess_result.get("session")
            or sess_result.get("data", {}).get("session")
        )
        if not session_token:
            raise RuntimeError(f"Could not find session token in response: {sess}")

    return f"http://192.168.1.2:8123{ingress_url}", session_token


async def exec_command(base_url: str, session: str, command: str, timeout: int = 60) -> str:
    """Run a shell command on the HA host via File Editor exec_command."""
    import urllib.request
    import urllib.parse

    body = urllib.parse.urlencode({"command": command, "timeout": timeout}).encode()
    req = urllib.request.Request(
        f"{base_url}api/exec_command",
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": f"ingress_session={session}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout + 5) as resp:
        result = json.loads(resp.read())
    # Response has stdout/stderr/returncode (not "output")
    rc = result.get("returncode", 0)
    stdout = result.get("stdout", "")
    stderr = result.get("stderr", "")
    if rc != 0 or result.get("error"):
        raise RuntimeError(f"Command failed (rc={rc}): stderr={stderr!r} stdout={stdout!r}")
    return stdout


# ── Build tarball ──────────────────────────────────────────────────────────────

def build_tarball(dest: Path) -> None:
    print("Building tarball …")
    with tarfile.open(dest, "w:gz") as tar:
        # Add integration under custom_components/battery_arbitrage/
        tar.add(
            INTEGRATION_SRC,
            arcname="custom_components/battery_arbitrage",
            filter=lambda ti: None if "__pycache__" in ti.name or ti.name.endswith(".pyc") else ti,
        )
    print(f"  → {dest} ({dest.stat().st_size // 1024} KB)")


# ── Deploy integration ─────────────────────────────────────────────────────────

async def deploy_integration() -> None:
    import websockets

    tarball = Path(tempfile.gettempdir()) / TARBALL_NAME
    build_tarball(tarball)

    print("Starting HTTP server …")
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(HTTP_PORT)],
        cwd=tempfile.gettempdir(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)

    try:
        print("Getting File Editor ingress session …")
        base_url, session = await get_ingress_session()
        print(f"  Ingress URL: {base_url}")

        print("Downloading tarball on HA host …")
        out = await exec_command(
            base_url, session,
            f"sh -c 'wget -q http://{MAC_IP}:{HTTP_PORT}/{TARBALL_NAME} -O /tmp/{TARBALL_NAME} && echo OK'",
        )
        print(f"  wget: {out.strip()}")

        print("Extracting …")
        out = await exec_command(
            base_url, session,
            f"sh -c 'tar -xzf /tmp/{TARBALL_NAME} -C /homeassistant && echo DONE'",
        )
        print(f"  extract: {out.strip()}")

        print("Cleaning macOS resource forks …")
        await exec_command(
            base_url, session,
            r"sh -c 'find /homeassistant/custom_components/battery_arbitrage -name \"._*\" -delete && echo CLEAN'",
        )

    finally:
        print("Stopping HTTP server …")
        server_proc.terminate()
        server_proc.wait()

    print("Restarting Home Assistant …")
    await restart_ha()
    print("Waiting for HA to come back online …")
    await wait_for_ha()
    print("HA is back online.")


async def restart_ha() -> None:
    import urllib.request
    req = urllib.request.Request(
        f"{HA_URL}/api/services/homeassistant/restart",
        data=b"{}",
        headers={
            "Authorization": f"Bearer {HASS_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception:
        pass  # HA may close the connection immediately on restart


async def wait_for_ha(timeout: int = 120) -> None:
    import urllib.request
    import urllib.error
    deadline = time.time() + timeout
    while time.time() < deadline:
        await asyncio.sleep(5)
        try:
            req = urllib.request.Request(
                f"{HA_URL}/api/",
                headers={"Authorization": f"Bearer {HASS_TOKEN}"},
            )
            with urllib.request.urlopen(req, timeout=5):
                return
        except Exception:
            pass
    raise TimeoutError("HA did not come back online within timeout")


# ── Deploy dashboard ───────────────────────────────────────────────────────────

async def deploy_dashboard() -> None:
    import websockets

    print("Loading dashboard YAML …")
    with open(DASHBOARD_YAML) as f:
        dashboard_config = yaml.safe_load(f)

    async with websockets.connect(HA_WS) as ws:
        await ws_auth(ws)

        # List existing dashboards to see if ours already exists
        resp = await ws_send_recv(ws, {"type": "lovelace/dashboards/list"}, 10)
        existing = {d["url_path"]: d for d in (resp.get("result") or [])}
        print(f"  Existing dashboards: {list(existing.keys())}")

        if DASHBOARD_URL_PATH not in existing:
            print(f"  Creating dashboard '{DASHBOARD_URL_PATH}' …")
            resp = await ws_send_recv(ws, {
                "type": "lovelace/dashboards/create",
                "url_path": DASHBOARD_URL_PATH,
                "title": DASHBOARD_TITLE,
                "icon": DASHBOARD_ICON,
                "show_in_sidebar": True,
                "require_admin": False,
                "mode": "storage",
            }, 11)
            if not resp.get("success"):
                print(f"  WARNING: could not create dashboard: {resp}")
            else:
                print("  Dashboard created.")
        else:
            print(f"  Dashboard '{DASHBOARD_URL_PATH}' already exists, updating config.")

        # Save config to the dashboard
        print("  Saving dashboard config …")
        resp = await ws_send_recv(ws, {
            "type": "lovelace/config/save",
            "url_path": DASHBOARD_URL_PATH,
            "config": dashboard_config,
        }, 12)
        if resp.get("success"):
            print(f"  Dashboard deployed → {HA_URL}/{DASHBOARD_URL_PATH}")
        else:
            print(f"  ERROR saving dashboard: {resp}")


# ── Main ───────────────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy battery_arbitrage to HA")
    parser.add_argument(
        "--dashboard-only",
        action="store_true",
        help="Skip integration deploy, only push the Lovelace dashboard",
    )
    args = parser.parse_args()

    if not args.dashboard_only:
        await deploy_integration()

    await deploy_dashboard()
    print("\nAll done.")


if __name__ == "__main__":
    try:
        import websockets  # noqa: F401
    except ImportError:
        print("Missing dependency. Run:  pip install websockets PyYAML")
        sys.exit(1)

    asyncio.run(main())
