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
from collections import deque
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

    def __init__(self, cp_id: str, connection: Any, remote_start_cooldown_s: int = 30) -> None:
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
        # v0.40.4 — command/telemetry observability (surfaced via the OCPP
        # diagnostics sensor). Outcome + timestamp of the last outbound
        # commands and the last inbound MeterValues, so desyncs are visible
        # without log-diving.
        self.last_set_profile_status: str | None = None
        self.last_set_profile_ts: datetime | None = None
        self.last_remote_start_status: str | None = None
        self.last_remote_start_ts: datetime | None = None
        self.last_metervalues_ts: datetime | None = None
        # v0.40.5 — last auto-heal action taken by the desync watchdog.
        self.last_recovery_action: str | None = None
        self.last_recovery_ts: datetime | None = None
        # v0.40.6 — rolling event log (a queryable history without a file log).
        # Boot / status changes / commands + results / recoveries land here;
        # the newest-last list is surfaced on the diagnostics sensor.
        self.events: deque = deque(maxlen=50)
        # GetCompositeSchedule support probe (None = unknown, set after first try).
        self._composite_schedule_supported: bool | None = None

        # ── Outbound throttle: last commanded amps (avoid no-op writes) ───
        self.last_commanded_amps: int | None = None

        # ── RemoteStartTransaction cooldown (v0.27.1, configurable v0.28.7) ─
        # Don't spam RemoteStartTransaction every tick if the charger keeps
        # ignoring us. Cooldown is now user-configurable (5-300 s, default 30).
        self.last_remote_start_attempt: datetime | None = None
        self.remote_start_cooldown_s: int = int(remote_start_cooldown_s)

    # ────────────────────────────────────────────────────────────────────
    # Event log (v0.40.6)
    # ────────────────────────────────────────────────────────────────────

    def _log_event(self, kind: str, detail: str = "") -> None:
        """Append a compact entry to the rolling event log (max 50, newest last)."""
        self.events.append({
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kind": kind,
            "detail": str(detail),
        })

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
        # A fresh boot clears any charging profile on the charger, so it
        # reverts to its built-in default (full current). Drop the cached
        # commanded value so the next set_current actually re-sends the
        # limit instead of being skipped as a no-op.
        self.last_commanded_amps = None
        # A freshly booted charger has no active transaction — clear any stale
        # session flag so the controller can RemoteStart a fresh session.
        self.session_active = False
        self._log_event("boot", f"{self.model} fw={self.firmware}")  # v0.40.6
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
        # v0.40.3 — a charger reporting Available/Preparing has no active
        # charging transaction. Clear a stale `session_active` flag (e.g. left
        # True across a reconnect/reboot when the closing StopTransaction was
        # missed) so the controller's RemoteStartTransaction — which only fires
        # when `not session_active` — can start a fresh session. Without this
        # the charger wedges in Preparing while the controller commands charge
        # but never sends Start.
        if new_status in ("Available", "Preparing"):
            self.session_active = False
        if new_status != self.status:
            self._log_event("status", new_status)  # v0.40.6
        self.status = new_status
        self.last_seen = datetime.now(timezone.utc)
        _LOGGER.debug(
            "OCPP charger %s status: %s (connector=%s error=%s)",
            self.id, self.status, connector_id, error_code,
        )
        return call_result.StatusNotification()

    @on(Action.meter_values if hasattr(Action, "meter_values") else "MeterValues")
    async def on_meter_values(self, connector_id=None, meter_value=None,
                              transaction_id=None, **kwargs):
        self.last_seen = datetime.now(timezone.utc)
        self.last_metervalues_ts = self.last_seen  # v0.40.4 — telemetry freshness

        # v0.37.0 — Transaction-id recovery.
        # OCPP 1.6 specifies `transactionId` as an OPTIONAL field on
        # MeterValues.req. When a session is active, well-behaved chargers
        # include it on every MeterValues frame. We use it to:
        #   (a) RECOVER state after a HA restart killed our session tracking
        #       (the canonical Item 5 OCPP bug — charger keeps draining the
        #        EV while Solar AI thinks IDLE and can't issue RemoteStop
        #        because the transaction id is None). The first MeterValues
        #        after reconnect re-syncs us to the active transaction.
        #   (b) DETECT drift if the charger ended one session and started
        #       another while we weren't watching (e.g. car re-plugged
        #       during HA downtime). We adopt the new id and reset session
        #       counters.
        try:
            incoming_tx = int(transaction_id) if transaction_id is not None else None
        except (TypeError, ValueError):
            incoming_tx = None
        if incoming_tx and incoming_tx > 0:
            if self.session_transaction_id is None or not self.session_active:
                # Recovered session — populate the bare minimum so RemoteStop
                # can target it. session_start_ts is best-effort (we don't
                # know the real start); session_start_energy_wh is taken
                # from the current Energy.Active.Import.Register if present
                # in the same frame (handled below by the existing loop).
                _LOGGER.info(
                    "OCPP charger %s: recovered active transaction id=%d "
                    "from MeterValues (was untracked — likely after HA restart)",
                    self.id, incoming_tx,
                )
                self.session_active = True
                self.session_transaction_id = incoming_tx
                if self.session_start_ts is None:
                    self.session_start_ts = datetime.now(timezone.utc)
            elif self.session_transaction_id != incoming_tx:
                # Drift — adopt the charger's view and reset counters.
                _LOGGER.warning(
                    "OCPP charger %s: transaction id drift "
                    "(tracked=%d, charger reports=%d) — resyncing",
                    self.id, self.session_transaction_id, incoming_tx,
                )
                self.session_transaction_id = incoming_tx
                self.session_start_ts = datetime.now(timezone.utc)
                self.session_start_energy_wh = None
                self.session_energy_wh = 0.0
                self.session_solar_wh = 0.0
                self.session_grid_wh = 0.0
                self._session_split_last_ts = None

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
                    # v0.37.0 — if this is the FIRST MeterValues after a
                    # recovered transaction (session_start_energy_wh still
                    # None), seed the start register from this value so the
                    # in-session counter starts from now rather than going
                    # negative against a stale start.
                    if (self.session_active
                            and self.session_start_energy_wh is None):
                        self.session_start_energy_wh = wh
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
        # A new transaction starts at the charger's own default current until
        # we (re-)assert a profile. Drop the cached value so the controller's
        # next set_current is actually sent rather than skipped as a no-op.
        self.last_commanded_amps = None
        self._log_event("tx_start", f"tx={self.session_transaction_id}")  # v0.40.6
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
        self._log_event("tx_stop", f"{delivered_kwh:.2f} kWh")  # v0.40.6
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

    async def set_current(self, amps: int, force: bool = False, retries: int = 2) -> bool:
        """Send a SetChargingProfile setting the connector's max current.

        OCPP 1.6 has no direct "set amps" message — we wrap the current in a
        TxDefaultProfile with a single charging period at the target amps.
        Returns True only when the charger replies Accepted.

        `force=True` bypasses the duplicate-write skip so the controller can
        periodically re-assert the active limit (recovers a charger that
        silently dropped its profile and reverted to full current).

        v0.40.4 — the response status is verified and recorded
        (`last_set_profile_status`/`_ts`). On a non-Accepted reply or an
        exception the call is retried up to `retries` times with backoff,
        and `last_commanded_amps` is only updated on an Accepted reply (so a
        rejected write isn't cached as applied and the controller's re-assert
        keeps trying).
        """
        amps = max(0, int(amps))
        # Skip duplicate writes — the EV controller already gates this,
        # but cheap defence-in-depth. `force` overrides for periodic re-assert.
        if not force and amps == self.last_commanded_amps:
            return True
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
        for attempt in range(retries + 1):
            try:
                response = await self.call(req)
                status = getattr(response, "status", None)
                self.last_set_profile_status = str(status)
                self.last_set_profile_ts = datetime.now(timezone.utc)
                if str(status).lower() == "accepted" or status is True:
                    self.last_commanded_amps = amps
                    self._log_event("set_profile", f"{amps} A → Accepted")  # v0.40.6
                    _LOGGER.info(
                        "OCPP charger %s: SetChargingProfile %d A → Accepted%s",
                        self.id, amps,
                        f" (attempt {attempt + 1})" if attempt else "",
                    )
                    return True
                self._log_event("set_profile", f"{amps} A → {status} (attempt {attempt + 1})")
                _LOGGER.warning(
                    "OCPP charger %s: SetChargingProfile %d A → %s (attempt %d/%d)",
                    self.id, amps, status, attempt + 1, retries + 1,
                )
            except Exception as err:  # noqa: BLE001
                self.protocol_errors += 1
                self.last_protocol_error = f"set_current({amps}A): {err}"
                self.last_set_profile_status = f"error: {err}"
                self.last_set_profile_ts = datetime.now(timezone.utc)
                self._log_event("set_profile", f"{amps} A → error: {err}")  # v0.40.6
                _LOGGER.warning(
                    "OCPP charger %s: set_current(%d A) failed (attempt %d/%d): %s",
                    self.id, amps, attempt + 1, retries + 1, err,
                )
            if attempt < retries:
                await asyncio.sleep(1.5 * (attempt + 1))
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
        cooldown_s = self.remote_start_cooldown_s
        if self.last_remote_start_attempt is not None:
            elapsed = (now - self.last_remote_start_attempt).total_seconds()
            if elapsed < cooldown_s:
                _LOGGER.debug(
                    "OCPP charger %s: RemoteStartTransaction skipped (cooldown, %.1f s left)",
                    self.id, cooldown_s - elapsed,
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
            self.last_remote_start_status = str(status)  # v0.40.4
            self.last_remote_start_ts = now
            self._log_event("remote_start", str(status))  # v0.40.6
            _LOGGER.info(
                "OCPP charger %s: RemoteStartTransaction(idTag=%s, connector=%d) → %s",
                self.id, id_tag, connector_id, status,
            )
            return accepted
        except Exception as err:  # noqa: BLE001
            self.protocol_errors += 1
            self.last_protocol_error = f"RemoteStartTransaction: {err}"
            self.last_remote_start_status = f"error: {err}"  # v0.40.4
            self.last_remote_start_ts = now
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
        # v0.37.0 — added MeterValues to the trigger list. If a session is
        # active when we (re)connect, the charger's response includes the
        # current transactionId, which `on_meter_values` uses to recover
        # session tracking (Item 5 fix). Order matters: ask for Status
        # first so on_status fires before on_meter_values, ensuring the
        # charger's "Charging" status is recorded before we treat the
        # incoming tx_id as authoritative.
        for msg_type in ("StatusNotification", "BootNotification", "MeterValues"):
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

    async def change_availability(self, operative: bool, connector_id: int = 1) -> bool:
        """Send ChangeAvailability to take the connector Operative/Inoperative (v0.40.5).

        Used by the desync watchdog as a last-resort nudge: cycling a wedged
        connector Inoperative → Operative forces most chargers to drop a stuck
        Preparing/Finishing state and re-handshake the car, after which the
        normal RemoteStartTransaction can begin a clean session. Standard OCPP
        op — does NOT reboot the charger (unlike Reset).
        """
        typ = "Operative" if operative else "Inoperative"
        try:
            req = call.ChangeAvailability(connector_id=connector_id, type=typ)
            response = await self.call(req)
            status = getattr(response, "status", None)
            self._log_event("availability", f"{typ} → {status}")  # v0.40.6
            _LOGGER.info(
                "OCPP charger %s: ChangeAvailability(connector=%d, %s) → %s",
                self.id, connector_id, typ, status,
            )
            return str(status).lower() in ("accepted", "scheduled")
        except Exception as err:  # noqa: BLE001
            self.protocol_errors += 1
            self.last_protocol_error = f"ChangeAvailability({typ}): {err}"
            _LOGGER.warning(
                "OCPP charger %s: ChangeAvailability(%s) failed: %s",
                self.id, typ, err,
            )
            return False

    async def verify_applied_limit(self) -> float | None:
        """Read back the charger's composite schedule to learn the *applied*
        current limit in amps (v0.40.6).

        Diagnostic only — logs the result (applied vs commanded) as an event so
        a charger silently ignoring SetChargingProfile is visible. Many OCPP 1.6
        chargers (incl. some FoxESS units) don't implement GetCompositeSchedule;
        on the first NotSupported/error reply the probe disables itself
        (`_composite_schedule_supported = False`) and is never retried — the
        periodic re-assert remains the primary safety net. Returns the applied
        amps, or None if unknown/unsupported.
        """
        if self._composite_schedule_supported is False:
            return None
        try:
            req = call.GetCompositeSchedule(connector_id=1, duration=1)
            response = await self.call(req)
            status = getattr(response, "status", None)
            if str(status).lower() != "accepted":
                self._composite_schedule_supported = False
                self._log_event("composite_schedule", f"unsupported ({status})")
                return None
            self._composite_schedule_supported = True
            sched = getattr(response, "charging_schedule", None)
            periods = None
            if isinstance(sched, dict):
                periods = (sched.get("chargingSchedulePeriod")
                           or sched.get("charging_schedule_period"))
            elif sched is not None:
                periods = (getattr(sched, "charging_schedule_period", None)
                           or getattr(sched, "chargingSchedulePeriod", None))
            if not periods:
                return None
            p0 = periods[0]
            limit = p0.get("limit") if isinstance(p0, dict) else getattr(p0, "limit", None)
            if limit is None:
                return None
            applied = float(limit)
            self._log_event(
                "composite_schedule",
                f"applied {applied:.0f} A (commanded {self.last_commanded_amps})",
            )
            return applied
        except Exception as err:  # noqa: BLE001
            self._composite_schedule_supported = False
            self._log_event("composite_schedule", f"error: {err}")
            return None

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
        remote_start_cooldown_s: int = 30,
    ) -> None:
        self.port = port
        self.charge_points: dict[str, ChargePoint] = {}
        self._server: Any = None
        self._running: bool = False
        # v0.28.7: passed through to every ChargePoint instance created
        # by the server. Configurable in OCPP Settings.
        self.remote_start_cooldown_s: int = int(remote_start_cooldown_s)
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
            # Capture metadata + session state from the previous instance so a
            # within-session reconnect doesn't lose vendor/model/serial AND
            # transaction tracking (v0.37.0 — Item 5 fix).
            old_cp = self.charge_points[cp_id]
            if old_cp.vendor or old_cp.model or old_cp.serial or old_cp.session_active:
                self.persisted_metadata[cp_id] = {
                    "vendor": old_cp.vendor,
                    "model": old_cp.model,
                    "firmware": old_cp.firmware,
                    "serial": old_cp.serial,
                    "last_energy_wh_total": old_cp.energy_wh_total,
                    # v0.37.0 — session state survives a reconnect within
                    # the same HA process. Cross-restart survival comes
                    # from the coordinator's _persist_charger_metadata
                    # snapshot, which writes the same fields to disk.
                    "session_active": old_cp.session_active,
                    "session_transaction_id": old_cp.session_transaction_id,
                    "session_start_ts": (
                        old_cp.session_start_ts.isoformat()
                        if old_cp.session_start_ts is not None else None
                    ),
                    "session_start_energy_wh": old_cp.session_start_energy_wh,
                    "session_energy_wh": old_cp.session_energy_wh,
                    "session_solar_wh": old_cp.session_solar_wh,
                    "session_grid_wh": old_cp.session_grid_wh,
                }
        cp = ChargePoint(cp_id, connection, remote_start_cooldown_s=self.remote_start_cooldown_s)
        # Pre-populate from persisted metadata (v0.27.3) — vendor/model/serial
        # survive HA restarts, so sensors show real data even before the
        # charger sends a fresh BootNotification (which it usually won't).
        # v0.37.0 — extended to restore session-tracking state so RemoteStop
        # works after a restart that happened mid-session.
        md = self.persisted_metadata.get(cp_id)
        if md:
            cp.vendor = md.get("vendor", "")
            cp.model = md.get("model", "")
            cp.firmware = md.get("firmware", "")
            cp.serial = md.get("serial", "")
            cp.energy_wh_total = md.get("last_energy_wh_total", 0.0)
            # v0.37.0 — session state restore. The transaction id is the
            # critical piece for RemoteStop to work. If MeterValues come in
            # with a different id, on_meter_values syncs to the new one.
            if md.get("session_active"):
                cp.session_active = True
                cp.session_transaction_id = md.get("session_transaction_id")
                start_ts = md.get("session_start_ts")
                if start_ts:
                    try:
                        cp.session_start_ts = datetime.fromisoformat(start_ts)
                    except (TypeError, ValueError):
                        cp.session_start_ts = datetime.now(timezone.utc)
                cp.session_start_energy_wh = md.get("session_start_energy_wh")
                cp.session_energy_wh = md.get("session_energy_wh", 0.0)
                cp.session_solar_wh = md.get("session_solar_wh", 0.0)
                cp.session_grid_wh = md.get("session_grid_wh", 0.0)
                _LOGGER.info(
                    "OCPP charger %s: restored active session (tx=%s, energy=%.2f kWh) "
                    "from persisted metadata — RemoteStop is now wired",
                    cp_id, cp.session_transaction_id,
                    (cp.session_energy_wh or 0) / 1000.0,
                )
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
