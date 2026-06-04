#!/usr/bin/env python3
"""Solar AI — deploy / install / uninstall script for Home Assistant.

Usage:
    python3 deploy.py                  # redeploy files + push dashboard
    python3 deploy.py --files-only     # redeploy integration files + restart ONLY (never touches the dashboard)
    python3 deploy.py --dashboard-only # push dashboard config only
    python3 deploy.py --install        # full fresh install (files + config flow + dashboard)
    python3 deploy.py --uninstall      # remove integration, files and dashboard from HA

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

import os

import yaml

# ── Configuration ─────────────────────────────────────────────────────────────
#
# Configure via environment variables (or edit the fallback values below):
#
#   HA_HOST     — your Home Assistant host:port             (default: homeassistant.local:8123)
#   HA_PROTO    — http or https                              (default: http)
#   MAC_IP      — this dev machine's LAN IP                  (REQUIRED for tarball pull)
#                  e.g.  export MAC_IP=$(ipconfig getifaddr en0)   on macOS
#                        export MAC_IP=$(hostname -I | awk '{print $1}')  on Linux
#   EVCC_URL    — your EVCC instance                         (default: http://your-ha-ip:7070)
#
# Find your HA's IP under Settings → System → Network.

_HA_HOST  = os.environ.get("HA_HOST",  "homeassistant.local:8123")
_HA_PROTO = os.environ.get("HA_PROTO", "http")
HA_URL    = f"{_HA_PROTO}://{_HA_HOST}"
HA_WS     = f"{'wss' if _HA_PROTO == 'https' else 'ws'}://{_HA_HOST}/api/websocket"
MAC_IP    = os.environ.get("MAC_IP", "")
HTTP_PORT = int(os.environ.get("HTTP_PORT", "8765"))
TARBALL_NAME = "battery_arbitrage.tar.gz"

if not MAC_IP:
    print(
        "⚠  MAC_IP is empty. The HA host needs to fetch the tarball from this\n"
        "   machine over LAN. Export MAC_IP before running, e.g.:\n"
        "      export MAC_IP=$(ipconfig getifaddr en0)        # macOS\n"
        "      export MAC_IP=$(hostname -I | awk '{print $1}') # Linux"
    )

# Default config-flow answers — edit these if your setup differs
INSTALL_DEFAULTS = {
    "evcc_url":                   os.environ.get("EVCC_URL", "http://your-ha-ip:7070"),
    "foxess_inverter_id":         "0c6d23d42d87264a4f0a0dccb6061b12",
    "foxess_work_mode_entity":    "select.foxessmodbus_work_mode",
    "foxess_force_charge_entity": "number.foxessmodbus_force_charge_power",
    "foxess_force_discharge_entity": "number.foxessmodbus_force_discharge_power",
    "stromligning_entity":        "sensor.stromligning_spotprice_ex_vat",
    "battery_capacity":           11.52,
    "battery_floor_soc":          50,
    "battery_max_soc":            100,
    "round_trip_efficiency":      92,   # integer percent (70–100)
    "min_spread_arbitrage":       1.0,
    "min_solar_export_price":     0.50,
    "forecast_hours":             24,
    "dashboard_url_path":         "battery-arbitrage",
}


def _read_token() -> str:
    cfg_path = Path(os.path.expanduser(
        "~/Library/Application Support/Claude/claude_desktop_config.json"
    ))
    if cfg_path.exists():
        with open(cfg_path) as f:
            cfg = json.load(f)
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

REPO_ROOT       = Path(__file__).parent
INTEGRATION_SRC = REPO_ROOT / "custom_components" / "battery_arbitrage"
DASHBOARD_YAML  = INTEGRATION_SRC / "dashboards" / "dashboard_da.yaml"
# v0.51.0 — the canonical dashboards now live inside the integration package
# (custom_components/battery_arbitrage/dashboards/) so they ship via HACS and
# can be auto-created at setup. Previously they were at the repo-root dashboard/.

DOMAIN              = "battery_arbitrage"
DASHBOARD_URL_PATH  = "battery-arbitrage"
DASHBOARD_TITLE     = "Solar AI"
DASHBOARD_ICON      = "mdi:solar-power"
INTEGRATION_DIR     = "/homeassistant/custom_components/battery_arbitrage"


# ── WebSocket helpers ──────────────────────────────────────────────────────────

async def ws_auth(ws) -> None:
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


# ── File Editor ingress ────────────────────────────────────────────────────────

async def get_ingress_session() -> tuple[str, str]:
    """Return (base_url, session_token) for the File Editor add-on."""
    import websockets
    async with websockets.connect(HA_WS) as ws:
        await ws_auth(ws)

        info = await ws_send_recv(ws, {
            "type": "supervisor/api",
            "endpoint": "/addons/core_configurator/info",
            "method": "get",
        }, 1)
        result = info.get("result", {})
        ingress_url = result.get("ingress_url") or result.get("data", {}).get("ingress_url")
        if not ingress_url:
            raise RuntimeError(f"Could not find ingress_url: {info}")

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
            raise RuntimeError(f"Could not find session token: {sess}")

    return f"{HA_URL}{ingress_url}", session_token


async def exec_command(base_url: str, session: str, command: str, timeout: int = 60) -> str:
    import urllib.request, urllib.parse
    body = urllib.parse.urlencode({"command": command, "timeout": timeout}).encode()
    req = urllib.request.Request(
        f"{base_url}api/exec_command", data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": f"ingress_session={session}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout + 5) as resp:
        result = json.loads(resp.read())
    rc = result.get("returncode", 0)
    stdout = result.get("stdout", "")
    stderr = result.get("stderr", "")
    if rc != 0 or result.get("error"):
        raise RuntimeError(f"Command failed (rc={rc}): stderr={stderr!r} stdout={stdout!r}")
    return stdout


# ── HA REST helper ─────────────────────────────────────────────────────────────

def ha_request(method: str, path: str, body: dict | None = None) -> dict | list | None:
    import urllib.request
    req = urllib.request.Request(
        f"{HA_URL}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {HASS_TOKEN}", "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception:
        return None


# ── Build & deploy files ───────────────────────────────────────────────────────

def build_tarball(dest: Path) -> None:
    print("Building tarball …")
    with tarfile.open(dest, "w:gz") as tar:
        tar.add(
            INTEGRATION_SRC,
            arcname="custom_components/battery_arbitrage",
            filter=lambda ti: None if "__pycache__" in ti.name or ti.name.endswith(".pyc") else ti,
        )
    print(f"  → {dest} ({dest.stat().st_size // 1024} KB)")


async def deploy_files() -> None:
    tarball = Path(tempfile.gettempdir()) / TARBALL_NAME
    build_tarball(tarball)

    print("Starting HTTP server …")
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(HTTP_PORT)],
        cwd=tempfile.gettempdir(),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(1)

    try:
        print("Getting File Editor ingress session …")
        base_url, session = await get_ingress_session()

        print("Downloading tarball on HA host …")
        out = await exec_command(base_url, session,
            f"sh -c 'wget -q http://{MAC_IP}:{HTTP_PORT}/{TARBALL_NAME} -O /tmp/{TARBALL_NAME} && echo OK'")
        print(f"  wget: {out.strip()}")

        print("Extracting …")
        out = await exec_command(base_url, session,
            f"sh -c 'tar -xzf /tmp/{TARBALL_NAME} -C /homeassistant && echo DONE'")
        print(f"  extract: {out.strip()}")

        print("Cleaning macOS resource forks …")
        await exec_command(base_url, session,
            r"sh -c 'find /homeassistant/custom_components/battery_arbitrage -name \"._*\" -delete'")
    finally:
        print("Stopping HTTP server …")
        server_proc.terminate()
        server_proc.wait()


async def restart_ha() -> None:
    import urllib.request
    print("Restarting Home Assistant …")
    req = urllib.request.Request(
        f"{HA_URL}/api/services/homeassistant/restart",
        data=b"{}",
        headers={"Authorization": f"Bearer {HASS_TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception:
        pass


async def wait_for_ha(timeout: int = 180) -> None:
    import urllib.request
    print("Waiting for HA to come back online ", end="", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        await asyncio.sleep(5)
        print(".", end="", flush=True)
        try:
            req = urllib.request.Request(f"{HA_URL}/api/",
                headers={"Authorization": f"Bearer {HASS_TOKEN}"})
            with urllib.request.urlopen(req, timeout=5):
                print(" online.")
                return
        except Exception:
            pass
    raise TimeoutError("HA did not come back online within timeout")


# ── Dashboard ──────────────────────────────────────────────────────────────────

async def deploy_dashboard() -> None:
    import websockets
    print("Loading dashboard YAML …")
    with open(DASHBOARD_YAML) as f:
        dashboard_config = yaml.safe_load(f)

    async with websockets.connect(HA_WS) as ws:
        await ws_auth(ws)

        resp = await ws_send_recv(ws, {"type": "lovelace/dashboards/list"}, 10)
        existing = {d["url_path"]: d for d in (resp.get("result") or [])}

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
            print(f"  Dashboard '{DASHBOARD_URL_PATH}' exists, updating …")

        resp = await ws_send_recv(ws, {
            "type": "lovelace/config/save",
            "url_path": DASHBOARD_URL_PATH,
            "config": dashboard_config,
        }, 12)
        if resp.get("success"):
            print(f"  Dashboard deployed → {HA_URL}/{DASHBOARD_URL_PATH}")
        else:
            print(f"  ERROR saving dashboard: {resp}")


# ── Config flow ────────────────────────────────────────────────────────────────

async def run_config_flow() -> None:
    """Walk through the Solar AI config flow using INSTALL_DEFAULTS."""
    import urllib.request

    def post(path: str, body: dict) -> dict:
        req = urllib.request.Request(
            f"{HA_URL}{path}",
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {HASS_TOKEN}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())

    # Check if already configured
    entries = ha_request("GET", "/api/config/config_entries/entry") or []
    existing = [e for e in entries if e.get("domain") == DOMAIN]
    if existing:
        print(f"  Integration already configured (entry: {existing[0]['entry_id']}) — skipping config flow.")
        return

    print("  Starting config flow …")
    r = post("/api/config/config_entries/flow", {"handler": DOMAIN})
    fid = r["flow_id"]

    steps = [
        # step_id → keys to submit
        ("user",        ["evcc_url"]),
        ("foxess",      ["foxess_inverter_id", "foxess_work_mode_entity",
                         "foxess_force_charge_entity", "foxess_force_discharge_entity"]),
        ("stromligning",["stromligning_entity"]),
        ("battery",     ["battery_capacity", "battery_floor_soc", "battery_max_soc",
                         "round_trip_efficiency", "min_spread_arbitrage",
                         "min_solar_export_price", "forecast_hours"]),
        ("dashboard",   ["dashboard_url_path"]),
    ]

    for step_id, keys in steps:
        data = {k: INSTALL_DEFAULTS[k] for k in keys}
        r = post(f"/api/config/config_entries/flow/{fid}", data)
        errors = r.get("errors") or {}
        if errors:
            raise RuntimeError(f"Config flow step '{step_id}' failed: {errors}")
        result_type = r.get("type", "")
        print(f"  Step '{step_id}' → {result_type}")
        if result_type == "create_entry":
            print(f"  Entry created: {r.get('result', {}).get('entry_id', '?')}")
            return

    raise RuntimeError("Config flow did not complete — check HA logs")


# ── Install ────────────────────────────────────────────────────────────────────

async def full_install() -> None:
    print("=" * 60)
    print("Solar AI — Full Install")
    print("=" * 60)

    print("\n[1/4] Deploying integration files …")
    await deploy_files()

    print("\n[2/4] Restarting HA …")
    await restart_ha()
    await wait_for_ha()

    print("\n[3/4] Running config flow …")
    await run_config_flow()

    print("\n[4/4] Deploying dashboard …")
    await deploy_dashboard()

    print("\n" + "=" * 60)
    print("Install complete!")
    print(f"Dashboard: {HA_URL}/{DASHBOARD_URL_PATH}")
    print("The arbitrage switch is OFF by default.")
    print("Turn it on via the dashboard once the system has")
    print("had a few days to learn solar accuracy and house load.")
    print("=" * 60)


# ── Uninstall ──────────────────────────────────────────────────────────────────

async def full_uninstall() -> None:
    import websockets

    print("=" * 60)
    print("Solar AI — Uninstall")
    print("=" * 60)

    # Step 1: Remove config entry (triggers cleanup — restores inverter/EVCC/automation)
    print("\n[1/4] Removing config entry …")
    entries = ha_request("GET", "/api/config/config_entries/entry") or []
    ba_entries = [e for e in entries if e.get("domain") == DOMAIN]
    if ba_entries:
        for entry in ba_entries:
            eid = entry["entry_id"]
            result = ha_request("DELETE", f"/api/config/config_entries/{eid}")
            print(f"  Removed entry {eid}: {result}")
        # Give HA a moment to run the unload/cleanup code
        await asyncio.sleep(5)
    else:
        print("  No config entry found — already removed or never installed.")

    # Step 2: Delete integration files from HA
    print("\n[2/4] Deleting integration files from HA …")
    base_url, session = await get_ingress_session()
    try:
        out = await exec_command(base_url, session,
            f"sh -c 'rm -rf {INTEGRATION_DIR} && echo DONE'")
        print(f"  Files removed: {out.strip()}")
    except Exception as e:
        print(f"  WARNING: could not delete files: {e}")

    # Step 3: Remove the dashboard
    print("\n[3/4] Removing dashboard …")
    async with websockets.connect(HA_WS) as ws:
        await ws_auth(ws)
        resp = await ws_send_recv(ws, {"type": "lovelace/dashboards/list"}, 10)
        existing = {d["url_path"]: d for d in (resp.get("result") or [])}
        if DASHBOARD_URL_PATH in existing:
            dash_id = existing[DASHBOARD_URL_PATH]["id"]
            resp = await ws_send_recv(ws, {
                "type": "lovelace/dashboards/delete",
                "dashboard_id": dash_id,
            }, 11)
            if resp.get("success"):
                print(f"  Dashboard '{DASHBOARD_URL_PATH}' removed.")
            else:
                print(f"  WARNING: could not remove dashboard: {resp}")
        else:
            print(f"  Dashboard '{DASHBOARD_URL_PATH}' not found — already removed.")

    # Step 4: Restart HA to fully deregister the integration
    print("\n[4/4] Restarting HA …")
    await restart_ha()
    await wait_for_ha()

    print("\n" + "=" * 60)
    print("Uninstall complete. HA is back to its original state.")
    print("=" * 60)


# ── Main ───────────────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Solar AI — deploy/install/uninstall for Home Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
commands:
  (no flag)          redeploy integration files + push dashboard
  --files-only       redeploy integration files + restart ONLY (never touches the dashboard)
  --install          full fresh install: files + config flow + dashboard
  --uninstall        remove everything from HA and restore original state
  --dashboard-only   push dashboard config only (no file deploy, no restart)
        """,
    )
    parser.add_argument("--install",        action="store_true", help="Full fresh install")
    parser.add_argument("--uninstall",      action="store_true", help="Remove everything from HA")
    parser.add_argument("--dashboard-only", action="store_true", help="Push dashboard only")
    parser.add_argument("--files-only",     action="store_true", help="Deploy integration files + restart only; never touches the dashboard")
    args = parser.parse_args()

    if args.install:
        await full_install()
    elif args.uninstall:
        await full_uninstall()
    elif args.dashboard_only:
        await deploy_dashboard()
        print("\nAll done.")
    elif args.files_only:
        await deploy_files()
        await restart_ha()
        await wait_for_ha()
        print("\nFiles deployed and HA restarted. Dashboard left untouched.")
    else:
        await deploy_files()
        await restart_ha()
        await wait_for_ha()
        await deploy_dashboard()
        print("\nAll done.")


if __name__ == "__main__":
    try:
        import websockets  # noqa: F401
    except ImportError:
        print("Missing dependency. Run:  pip install websockets PyYAML")
        sys.exit(1)

    asyncio.run(main())
