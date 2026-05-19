"""Embedded OCPP 1.6 server for Solar AI (v0.27.0).

Replaces the `lbbrhzn/ocpp` HA integration with a small WebSocket server
hosted inside Solar AI itself. Goals:

  * Self-contained — no external HACS integration required for EV control
  * Permissive — tolerates non-standard charger frames (e.g. the FoxESS
    L11PMC's empty-array keepalive `'[]'`) without dropping the connection
  * Single-charger v1 — one CPID per Solar AI install; multi-charger is
    a future version

Architecture:

  ┌──────────────┐  ws://ha:9000/<cpid>/   ┌──────────────────┐
  │ Charger      │ ───────────────────────►│ websockets.serve │
  │  (L11PMC)    │ ◄───────────────────────┤   (asyncio)      │
  └──────────────┘                          └────────┬─────────┘
                                                     │ dispatch by URL path
                                                     ▼
                                          ┌──────────────────┐
                                          │ ChargePoint(cp_id)│
                                          │  inbound  → state │
                                          │  outbound → cmd   │
                                          └──────────────────┘

The coordinator reads `OcppServer.charge_points[cpid]` to:
  * Get live status / power / session info  (used by sensors + EV controller)
  * Send `set_current(amps)` outbound        (called from EV controller)

5-minute disconnect timeout: if no heartbeat / message in 300 s,
`effective_status()` reports `"Disconnected"` even though the WebSocket
may still be (silently) open.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import websockets

try:
    # python-ocpp library (added to requirements)
    from ocpp.routing import on
    from ocpp.v16 import ChargePoint as _Cp
    from ocpp.v16 import call, call_result
    from ocpp.v16.enums import (
        Action,
        AuthorizationStatus,
        DataTransferStatus,
        RegistrationStatus,
    )
except ImportError:  # pragma: no cover - dependency missing at install time
    _Cp = None  # type: ignore

_LOGGER = logging.getLogger(__name__)

# Spec: 5-minute disconnect grace period
DISCONNECT_TIMEOUT_SECONDS = 300

# Spec: tell the charger to heartbeat every 30 s (well under the 5-min timeout)
HEARTBEAT_INTERVAL_SECONDS = 30


class ChargePoint(_Cp if _Cp is not None else object):
    """Per-charger handler.

    Inbound OCPP messages update live state on `self`; sensors read directly
    from these attributes via the coordinator. The handler is permissive:
    schema validation is disabled, and unexpected message shapes are logged
    + counted but don't tear down the connection.
    """

    # python-ocpp checks this attribute on the instance; disabling validation
    # lets non-standard chargers (like the L11PMC) talk to us without their
    # frames being rejected as "invalid".
    _skip_schema_validation = True

    def __init__(self, cp_id: str, connection: Any) -> None:
        super().__init__(cp_id, connection)
        self._connection = connection

        # ── Live state read by sensors ────────────────────────────────────
        self.status: str = "Unknown"                  # last StatusNotification
        self.power_w: float = 0.0                     # latest active power
        self.voltage_v: float | None = None
        self.energy_wh_total: float = 0.0             # lifetime register read
        self.last_heartbeat: datetime | None = None
        self.last_seen: datetime = datetime.now(timezone.utc)

        # Boot info (filled at BootNotification)
        self.vendor: str = ""
        self.model: str = ""
        self.firmware: str = ""
        self.serial: str = ""

        # ── Session state ────────────────────────────────────────────────
        self.session_active: bool = False
        self.session_start_ts: datetime | None = None
        self.session_start_energy_wh: float | None = None
        self.session_energy_wh: float = 0.0
        self.session_transaction_id: int | None = None
        # v0.28.4: per-session grid vs solar energy split, integrated by the
        # coordinator tick from live PV/load/EV power. Approximate — depends
        # on tick cadence and live state — but useful to show how much of a
        # session was actually from the panels vs from the grid.
        self.session_solar_wh: float = 0.0
        self.session_grid_wh: float = 0.0
        self._session_split_last_ts: datetime | None = None
        # When a session closes, we publish summary here for the sensor /
        # session_log to pick up
        self.last_session_summary: dict | None = None

        # ── Diagnostics ──────────────────────────────────────────────────
        self.protocol_errors: int = 0
        self.last_protocol_error: str = ""

        # ── Outbound throttle: last commanded amps (avoid no-op writes) ───
        self.last_commanded_amps: int | None = None

        # ── RemoteStartTransaction cooldown (v0.27.1) ────────────────────
        # Don't spam RemoteStartTransaction every tick if the charger keeps
        # ignoring us. Cooldown is 30 s between attempts.
        self.last_remote_start_attempt: datetime | None = None

    # ────────────────────────────────────────────────────────────────────
    # Inbound handlers (charger → us)
    # ────────────────────────────────────────────────────────────────────

    @on(Action.boot_notification if hasattr(Action, "boot_notification") else "BootNotification")
    async def on_boot(self, charge_point_vendor=None, charge_point_model=None, **kwargs):
        self.vendor = str(charge_point_vendor or "")
        self.model = str(charge_point_model or "")
        self.firmware = str(kwargs.get("firmware_version", ""))
        self.serial = str(kwargs.get("charge_point_serial_number", ""))
        self.last_seen = datetime.now(timezone.utc)
        _LOGGER.info(
            "OCPP charger %s booted: vendor=%s model=%s fw=%s serial=%s",
            self.id, self.vendor, self.model, self.firmware, self.serial,
        )
        return call_result.BootNotification(
            current_time=datetime.now(timezone.utc).isoformat(),
            interval=HEARTBEAT_INTERVAL_SECONDS,
            status=RegistrationStatus.accepted,
        )

    @on(Action.heartbeat if hasattr(Action, "heartbeat") else "Heartbeat")
    async def on_heartbeat(self, **kwargs):
        now = datetime.now(timezone.utc)
        self.last_heartbeat = now
        self.last_seen = now
        return call_result.Heartbeat(current_time=now.isoformat())

    @on(Action.status_notification if hasattr(Action, "status_notification") else "StatusNotification")
    async def on_status(self, connector_id=None, error_code=None, status=None, **kwargs):
        new_status = str(status) if status is not None else "Unknown"
        # v0.28.0 fix: when charger reports it's no longer actively charging,
        # zero out power_w. Previously cp.power_w stayed at the last MeterValues
        # reading if the charger didn't send a final 0-W frame on session end
        # — leaving lader_effekt sensor stuck at e.g. 4.7 kW after the car
        # finished charging.
        if new_status in ("Available", "Finishing", "Faulted", "Unavailable", "Reserved"):
            self.power_w = 0.0
        self.status = new_status
        self.last_seen = datetime.now(timezone.utc)
        _LOGGER.debug(
            "OCPP charger %s status: %s (connector=%s error=%s)",
            self.id, self.status, connector_id, error_code,
        )
        return call_result.StatusNotification()

    @on(Action.meter_values if hasattr(Action, "meter_values") else "MeterValues")
    async def on_meter_values(self, connector_id=None, meter_value=None, **kwargs):
        self.last_seen = datetime.now(timezone.utc)
        if not meter_value:
            return call_result.MeterValues()
        for mv in meter_value:
            for sv in mv.get("sampled_value", []) or []:
                try:
                    measurand = sv.get("measurand", "Energy.Active.Import.Register")
                    unit = sv.get("unit", "Wh")
                    value = float(sv.get("value", 0))
                except (TypeError, ValueError):
                    continue
                if measurand == "Power.Active.Import":
                    # Normalise W
                    self.power_w = value * 1000.0 if unit in ("kW",) else value
                elif measurand == "Voltage":
                    self.voltage_v = value
                elif measurand == "Energy.Active.Import.Register":
                    wh = value * 1000.0 if unit == "kWh" else value
                    self.energy_wh_total = wh
                    if self.session_active and self.session_start_energy_wh is not None:
                        self.session_energy_wh = max(
                            0.0, wh - self.session_start_energy_wh,
                        )
        return call_result.MeterValues()

    @on(Action.authorize if hasattr(Action, "authorize") else "Authorize")
    async def on_authorize(self, id_tag=None, **kwargs):
        # LAN-only — accept everything. id_tag is just the user's RFID/card
        return call_result.Authorize(
            id_tag_info={"status": AuthorizationStatus.accepted},
        )

    @on(Action.start_transaction if hasattr(Action, "start_transaction") else "StartTransaction")
    async def on_start_transaction(
        self, connector_id=None, id_tag=None, meter_start=None,
        timestamp=None, **kwargs,
    ):
        self.session_active = True
        self.session_start_ts = datetime.now(timezone.utc)
        self.session_start_energy_wh = float(meter_start or 0)
        self.session_energy_wh = 0.0
        # v0.28.4: reset grid/solar split accumulators for the new session
        self.session_solar_wh = 0.0
        self.session_grid_wh = 0.0
        self._session_split_last_ts = None
        # Synthetic transaction ID — the L11PMC ignores the value, it just
        # needs a non-zero int. Use seconds-since-epoch to ensure uniqueness.
        self.session_transaction_id = int(datetime.now().timestamp())
        _LOGGER.info(
            "OCPP charger %s: transaction started (meter start %s Wh, tx=%d)",
            self.id, meter_start, self.session_transaction_id,
        )
        return call_result.StartTransaction(
            transaction_id=self.session_transaction_id,
            id_tag_info={"status": AuthorizationStatus.accepted},
        )

    @on(Action.stop_transaction if hasattr(Action, "stop_transaction") else "StopTransaction")
    async def on_stop_transaction(
        self, meter_stop=None, timestamp=None, transaction_id=None, **kwargs,
    ):
        end_wh = float(meter_stop or 0)
        delivered_wh = 0.0
        if self.session_active and self.session_start_energy_wh is not None:
            delivered_wh = max(0.0, end_wh - self.session_start_energy_wh)
        # Capture summary for the session log
        now = datetime.now(timezone.utc)
        duration_min = 0.0
        if self.session_start_ts is not None:
            duration_min = (now - self.session_start_ts).total_seconds() / 60.0
        # v0.28.4: include the integrated grid/solar split in the session
        # summary. Note: solar+grid may not exactly equal energy_kwh because
        # the split is integrated from per-tick live power readings while
        # energy_kwh comes from the charger's meter — small drift is normal.
        delivered_kwh = round(delivered_wh / 1000.0, 3)
        session_solar_kwh = round(self.session_solar_wh / 1000.0, 3)
        session_grid_kwh = round(self.session_grid_wh / 1000.0, 3)
        # If we missed some ticks, the split may sum to less than the meter.
        # Allocate the residual to grid (conservative — assume worst case).
        residual = max(0.0, delivered_kwh - session_solar_kwh - session_grid_kwh)
        if residual > 0:
            session_grid_kwh = round(session_grid_kwh + residual, 3)
        self.last_session_summary = {
            "start_ts": self.session_start_ts.isoformat() if self.session_start_ts else None,
            "end_ts": now.isoformat(),
            "duration_min": round(duration_min, 1),
            "energy_kwh": delivered_kwh,
            "energy_kwh_solar": session_solar_kwh,
            "energy_kwh_grid": session_grid_kwh,
            "avg_power_kw": round(
                delivered_kwh / (duration_min / 60.0), 2,
            ) if duration_min > 0 else 0.0,
        }
        self.session_energy_wh = delivered_wh
        self.session_active = False
        # v0.28.0 fix: zero out power_w on session end so the lader_effekt
        # sensor doesn't stay stuck at the last MeterValues reading.
        self.power_w = 0.0
        # v0.28.1 fix: clear the RemoteStartTransaction cooldown when a
        # session ends. Otherwise a stale `last_remote_start_attempt` from
        # earlier in the day can silently block the next legitimate restart
        # attempt for up to 30 s after the cool-down stop. With the session
        # confirmed closed, there's no reason to throttle the next start.
        self.last_remote_start_attempt = None
        _LOGGER.info(
            "OCPP charger %s: transaction stopped (%.2f kWh, %.1f min)",
            self.id, delivered_wh / 1000.0, duration_min,
        )
        return call_result.StopTransaction()

    @on(Action.data_transfer if hasattr(Action, "data_transfer") else "DataTransfer")
    async def on_data_transfer(self, vendor_id=None, **kwargs):
        # Vendor-specific extensions — accept + ignore
        return call_result.DataTransfer(status=DataTransferStatus.accepted)

    # ────────────────────────────────────────────────────────────────────
    # Outbound (us → charger)
    # ────────────────────────────────────────────────────────────────────

    async def set_current(self, amps: int) -> bool:
        """Send a SetChargingProfile setting the connector's max current.

        OCPP 1.6 has no direct "set amps" message — we wrap the current in a
        TxDefaultProfile with a single charging period at the target amps.
        Returns True on success, False if the call failed.
        """
        amps = max(0, int(amps))
        # Skip duplicate writes — the EV controller already gates this,
        # but cheap defence-in-depth.
        if amps == self.last_commanded_amps:
            return True
        try:
            req = call.SetChargingProfile(
                connector_id=1,
                cs_charging_profiles={
                    "chargingProfileId": 1,
                    "stackLevel": 0,
                    "chargingProfilePurpose": "TxDefaultProfile",
                    "chargingProfileKind": "Absolute",
                    "chargingSchedule": {
                        "chargingRateUnit": "A",
                        "chargingSchedulePeriod": [
                            {"startPeriod": 0, "limit": float(amps)},
                        ],
                    },
                },
            )
            response = await self.call(req)
            self.last_commanded_amps = amps
            _LOGGER.info(
                "OCPP charger %s: SetChargingProfile %d A → %s",
                self.id, amps, getattr(response, "status", "ok"),
            )
            return True
        except Exception as err:  # noqa: BLE001
            self.protocol_errors += 1
            self.last_protocol_error = f"set_current({amps}A): {err}"
            _LOGGER.warning(
                "OCPP charger %s: set_current(%d A) failed: %s",
                self.id, amps, err,
            )
            return False

    async def remote_start_transaction(
        self, id_tag: str = "solar_ai", connector_id: int = 1,
    ) -> bool:
        """Send RemoteStartTransaction to begin a charging session (v0.27.1).

        Required for chargers that don't auto-start when a car plugs in
        (i.e. no "Plug & Charge" mode, or `AuthorizeRemoteTxRequests=true`
        but no whitelist).  `SetChargingProfile` only sets the *limit* — to
        actually deliver power, the CSMS must initiate the transaction.

        Built-in cooldown: won't re-attempt within 30 s of the previous try,
        even if called repeatedly. Charger acknowledges with `Accepted` /
        `Rejected`; on Accepted, the charger then sends a `StartTransaction`
        request which our `on_start_transaction` handler responds to.
        """
        now = datetime.now(timezone.utc)
        if self.last_remote_start_attempt is not None:
            elapsed = (now - self.last_remote_start_attempt).total_seconds()
            if elapsed < 30:
                _LOGGER.debug(
                    "OCPP charger %s: RemoteStartTransaction skipped (cooldown, %.1f s left)",
                    self.id, 30 - elapsed,
                )
                return False
        self.last_remote_start_attempt = now
        try:
            req = call.RemoteStartTransaction(
                id_tag=id_tag,
                connector_id=connector_id,
            )
            response = await self.call(req)
            status = getattr(response, "status", None)
            accepted = (str(status).lower() == "accepted") or (status is True)
            _LOGGER.info(
                "OCPP charger %s: RemoteStartTransaction(idTag=%s, connector=%d) → %s",
                self.id, id_tag, connector_id, status,
            )
            return accepted
        except Exception as err:  # noqa: BLE001
            self.protocol_errors += 1
            self.last_protocol_error = f"RemoteStartTransaction: {err}"
            _LOGGER.warning(
                "OCPP charger %s: RemoteStartTransaction failed: %s",
                self.id, err,
            )
            return False

    async def request_status_refresh(self) -> bool:
        """Ask the charger to re-emit StatusNotification + BootNotification (v0.27.3).

        Used after a transport reconnect (HA restart, network blip) to get
        the charger to re-introduce itself. Most OCPP 1.6 chargers don't
        re-send Boot/Status on a plain WebSocket reconnect — they just
        resume Heartbeats, leaving our sensors with stale or empty data.

        Sends OCPP `TriggerMessage` for each message type. Charger responds
        Accepted / Rejected / NotImplemented / NotSupported. If Accepted,
        the charger then immediately sends the requested message which our
        existing @on_status / @on_boot handlers process normally.

        Returns True if at least one trigger was Accepted. Gracefully
        handles chargers that don't implement TriggerMessage at all
        (just logs at debug, no error spam).
        """
        any_accepted = False
        for msg_type in ("StatusNotification", "BootNotification"):
            try:
                req = call.TriggerMessage(
                    requested_message=msg_type,
                    connector_id=1,
                )
                response = await self.call(req)
                status = getattr(response, "status", None)
                accepted = str(status).lower() == "accepted"
                _LOGGER.info(
                    "OCPP charger %s: TriggerMessage(%s) → %s",
                    self.id, msg_type, status,
                )
                if accepted:
                    any_accepted = True
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug(
                    "OCPP charger %s: TriggerMessage(%s) failed (charger may not support it): %s",
                    self.id, msg_type, err,
                )
        return any_accepted

    async def remote_stop_transaction(self, transaction_id: int) -> bool:
        """Send RemoteStopTransaction to end an active charging session (v0.27.1).

        Charger responds with `Accepted` / `Rejected`. On Accepted, the
        charger then sends a `StopTransaction` request which our
        `on_stop_transaction` handler responds to.
        """
        try:
            req = call.RemoteStopTransaction(transaction_id=int(transaction_id))
            response = await self.call(req)
            status = getattr(response, "status", None)
            accepted = (str(status).lower() == "accepted") or (status is True)
            _LOGGER.info(
                "OCPP charger %s: RemoteStopTransaction(tx=%d) → %s",
                self.id, transaction_id, status,
            )
            return accepted
        except Exception as err:  # noqa: BLE001
            self.protocol_errors += 1
            self.last_protocol_error = f"RemoteStopTransaction: {err}"
            _LOGGER.warning(
                "OCPP charger %s: RemoteStopTransaction failed: %s",
                self.id, err,
            )
            return False

    # ────────────────────────────────────────────────────────────────────
    # Permissive parse override (catch malformed L11PMC keepalive frames)
    # ────────────────────────────────────────────────────────────────────

    async def start(self):
        """Override python-ocpp's read loop with a permissive variant.

        The standard `start()` calls `route_message(message)` directly inside
        the loop; if `route_message` raises (e.g. on the L11PMC's empty `[]`
        message), the exception propagates and the connection dies.

        We wrap each message in try/except so a single malformed frame is
        logged + counted but doesn't drop the connection.
        """
        while True:
            try:
                message = await self._connection.recv()
            except websockets.ConnectionClosed:
                _LOGGER.info("OCPP charger %s: WebSocket closed", self.id)
                return
            try:
                # Empty / malformed shortcut — skip without invoking the parser
                stripped = (message or "").strip()
                if stripped in ("", "[]"):
                    self.protocol_errors += 1
                    self.last_protocol_error = f"empty/malformed frame: {stripped!r}"
                    _LOGGER.debug(
                        "OCPP charger %s: ignored malformed frame %r",
                        self.id, stripped,
                    )
                    continue
                await self.route_message(message)
                self.last_seen = datetime.now(timezone.utc)
            except Exception as err:  # noqa: BLE001
                self.protocol_errors += 1
                self.last_protocol_error = str(err)
                _LOGGER.debug(
                    "OCPP charger %s: parse/handle error (ignored): %s",
                    self.id, err,
                )
                # Keep the connection alive — do not re-raise

    # ────────────────────────────────────────────────────────────────────
    # Derived state for sensors
    # ────────────────────────────────────────────────────────────────────

    @property
    def seconds_since_seen(self) -> float:
        return (datetime.now(timezone.utc) - self.last_seen).total_seconds()

    @property
    def is_disconnected(self) -> bool:
        """True if we haven't heard from the charger in DISCONNECT_TIMEOUT_SECONDS."""
        return self.seconds_since_seen > DISCONNECT_TIMEOUT_SECONDS

    def effective_status(self) -> str:
        """Status with the 5-min disconnect timeout applied.

        Even if the WebSocket is still nominally open, if no heartbeat /
        message has arrived in 5 min we report Disconnected so downstream
        consumers (EV controller, sensors) know the charger is unreachable.
        """
        if self.is_disconnected:
            return "Disconnected"
        return self.status or "Unknown"

    def session_duration_min(self) -> float:
        if not self.session_active or self.session_start_ts is None:
            return 0.0
        return (datetime.now(timezone.utc) - self.session_start_ts).total_seconds() / 60.0


class OcppServer:
    """WebSocket server that accepts OCPP 1.6 charger connections.

    Started once per integration setup; one server per Solar AI install.
    Charger connections are keyed by URL path (= CPID) in `charge_points`.
    A reconnect from the same CPID replaces the previous instance cleanly.
    """

    def __init__(
        self,
        port: int = 9000,
        persisted_metadata: dict | None = None,
    ) -> None:
        self.port = port
        self.charge_points: dict[str, ChargePoint] = {}
        self._server: Any = None
        self._running: bool = False
        # Charger metadata persisted across HA restarts (v0.27.3). Keyed by
        # cpid. Shared by-reference with coordinator._stored["charger_metadata"]
        # so updates from either side propagate. Used to pre-populate a new
        # ChargePoint instance on connect, so sensors don't go blank while
        # waiting for the charger to re-send Boot/Status (which it usually
        # won't, on a transport reconnect — see request_status_refresh()).
        self.persisted_metadata: dict = persisted_metadata if persisted_metadata is not None else {}

    async def start(self) -> None:
        """Bind the WebSocket server. Raises OSError on port conflict."""
        if self._running:
            return
        _LOGGER.info("Starting Solar AI embedded OCPP server on port %d", self.port)
        try:
            self._server = await websockets.serve(
                self._handle_connection,
                host="0.0.0.0",
                port=self.port,
                subprotocols=["ocpp1.6"],
            )
            self._running = True
            _LOGGER.info(
                "Solar AI OCPP server listening on ws://0.0.0.0:%d/<cpid>/",
                self.port,
            )
        except OSError as err:
            _LOGGER.error(
                "Solar AI OCPP server failed to bind port %d (%s). "
                "Another OCPP integration (e.g. lbbrhzn/ocpp) might still be "
                "installed and holding the port. Uninstall it and restart HA.",
                self.port, err,
            )
            raise

    async def stop(self) -> None:
        """Shut down the WebSocket server. Keeps charge_points dict (sensors
        keep reporting last-known state with `Disconnected` once timeout fires).
        """
        if not self._running:
            return
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._running = False
        _LOGGER.info("Solar AI OCPP server stopped")

    async def _handle_connection(self, connection: Any) -> None:
        """Per-connection handler.

        The URL path is the CPID. Replace any existing instance for the same
        CPID (handles reconnects after charger reboot). A connection with
        empty CPID is rejected.
        """
        # websockets v14+ uses connection.request.path; older uses connection.path
        path = getattr(getattr(connection, "request", None), "path", None) or \
            getattr(connection, "path", "")
        cp_id = (path or "").strip("/")
        if not cp_id:
            _LOGGER.warning("Charger connected with empty CPID — closing")
            try:
                await connection.close(1008, "CPID required in URL path")
            except Exception:  # noqa: BLE001
                pass
            return

        if cp_id in self.charge_points:
            _LOGGER.info(
                "OCPP charger %s reconnecting — replacing previous instance", cp_id,
            )
            # Capture metadata from the previous instance so a within-session
            # reconnect doesn't lose vendor/model/serial.
            old_cp = self.charge_points[cp_id]
            if old_cp.vendor or old_cp.model or old_cp.serial:
                self.persisted_metadata[cp_id] = {
                    "vendor": old_cp.vendor,
                    "model": old_cp.model,
                    "firmware": old_cp.firmware,
                    "serial": old_cp.serial,
                    "last_energy_wh_total": old_cp.energy_wh_total,
                }
        cp = ChargePoint(cp_id, connection)
        # Pre-populate from persisted metadata (v0.27.3) — vendor/model/serial
        # survive HA restarts, so sensors show real data even before the
        # charger sends a fresh BootNotification (which it usually won't).
        md = self.persisted_metadata.get(cp_id)
        if md:
            cp.vendor = md.get("vendor", "")
            cp.model = md.get("model", "")
            cp.firmware = md.get("firmware", "")
            cp.serial = md.get("serial", "")
            cp.energy_wh_total = md.get("last_energy_wh_total", 0.0)
            _LOGGER.info(
                "OCPP charger %s: pre-populated from persisted metadata (model=%s, serial=%s)",
                cp_id, cp.model, cp.serial,
            )
        self.charge_points[cp_id] = cp
        _LOGGER.info("OCPP charger %s connected (URL path /%s)", cp_id, cp_id)

        # Schedule a TriggerMessage shortly after connect (v0.27.3). 2-second
        # delay so the read loop is up and route_message can dispatch the
        # responses. Background task — doesn't block the main read loop.
        asyncio.create_task(self._post_connect_refresh(cp))

        try:
            await cp.start()
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception(
                "OCPP charger %s handler crashed (kept in state for timeout): %s",
                cp_id, err,
            )
        # Don't pop cp from self.charge_points on disconnect — the 5-min
        # timeout logic in effective_status() handles "is the charger alive?"
        # and we want sensors to keep reporting last-known state until then.

    async def _post_connect_refresh(self, cp: "ChargePoint") -> None:
        """Send TriggerMessage shortly after a charger (re)connects.

        Sleeps briefly to let the read loop come up (so route_message can
        dispatch the responses), then asks the charger to re-emit its
        Boot and Status notifications. Most OCPP 1.6 chargers don't
        re-send these on a transport reconnect — TriggerMessage forces
        the issue. If the charger doesn't support TriggerMessage, the
        persisted metadata + next natural status change still cover us.
        """
        try:
            await asyncio.sleep(2)
            await cp.request_status_refresh()
        except asyncio.CancelledError:
            pass
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug(
                "OCPP charger %s: post-connect refresh failed: %s",
                cp.id, err,
            )

    def get(self, cp_id: str) -> ChargePoint | None:
        """Convenience accessor used by the coordinator + sensors."""
        return self.charge_points.get(cp_id)
