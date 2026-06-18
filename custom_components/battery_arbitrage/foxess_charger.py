"""FoxESS L11PMC EV charger — direct Modbus TCP backend.

Drives the charger over Modbus TCP. The charger must be put into "Modbus TCP"
mode in the FoxESS app; OCPP and Modbus are mutually exclusive on the device,
so this backend and the embedded-OCPP backend cannot run at the same time.

Register addresses and behaviour are verified against the official FoxESS EV
Charger Modbus TCP Protocol 1.6 and a live test on an L11PMC (11 kW, 16 A/phase).

Three facts drive the design:

  * Setpoints are not sticky. The max-current (0x3001) and max-power (0x3002)
    registers expire ~180 s after the last write (Time Validity, 0x3005); on
    expiry the charger reverts to full three-phase at its default current. The
    caller must re-assert the setpoint on a heartbeat well inside that window —
    `async_apply` is written to be called every control cycle for exactly this.

  * The power cap selects the phase count. With auto-switching enabled
    (0x300A = 1), a power cap in the 1.4-4.2 kW band keeps the charger in
    single-phase; >= 4.2 kW runs three-phase. Phase 1 forces single-phase by
    holding the cap at `EV_MODBUS_SINGLE_PHASE_CAP_KW` and modulating current.

  * The live phase count must be read from the per-phase currents (0x100B-D),
    never from 0x1010 ("Current Phase Sequence") — that register read 0
    ("three-phase") during a confirmed single-phase session.

The client uses non-blocking asyncio streams (never a blocking socket on the
event loop) and frames responses by the MBAP length field, because this device
sometimes splits a response across two TCP segments.
"""
from __future__ import annotations

import asyncio
import logging
import struct

_LOGGER = logging.getLogger(__name__)

# ── Register map (holding registers, FC3 read) ────────────────────────────
REG_STATUS          = 0x1003   # EVC status, UINT16 (see EVC_STATUS_* below)
REG_PHASE_CURRENT   = 0x100B   # L1/L2/L3 current, 3 × UINT16, 0.1 A
REG_ACTIVE_POWER    = 0x100E   # active power, UINT16, 0.1 kW
REG_WORK_MODE       = 0x3000   # 0=controlled 1=plug-and-charge 2=lock (W/R)
REG_MAX_CURRENT     = 0x3001   # max charging current, UINT16, 0.1 A (W/R)
REG_MAX_POWER       = 0x3002   # max charging power, UINT16, 0.1 kW (W/R)
REG_TIME_VALIDITY   = 0x3005   # EMS setpoint validity window, seconds (W/R)
REG_AUTO_PHASE      = 0x300A   # single/three-phase auto switching 0/1 (W/R)
REG_SUSPEND_INTERVAL = 0x300B  # min interval before a phase switch, minutes (W/R)
REG_CHARGING_CTRL   = 0x4001   # 0=no-op 1=start 2=stop (write-only)

# Read/write registers must use FC16 (write-multiple); write-only registers
# (0x40xx) use FC6 (write-single). FC6 on a 0x30xx register is rejected.

# ── EVC status values (0x1003) ────────────────────────────────────────────
EVC_STATUS_IDLE       = 0   # no car connected
EVC_STATUS_CONNECTED  = 1   # car connected, waiting for a start command
EVC_STATUS_START      = 2   # starting
EVC_STATUS_CHARGING   = 3   # charging
EVC_STATUS_PAUSE      = 4
EVC_STATUS_FINISH     = 5   # session ended
EVC_STATUS_FAULT      = 6
EVC_STATUS_RESERVE    = 7
EVC_STATUS_LOCKED      = 8
EVC_STATUS_SWITCHING  = 9   # transient, seen during a phase switch

_STATUS_LABELS = {
    EVC_STATUS_IDLE: "idle",
    EVC_STATUS_CONNECTED: "connected",
    EVC_STATUS_START: "starting",
    EVC_STATUS_CHARGING: "charging",
    EVC_STATUS_PAUSE: "paused",
    EVC_STATUS_FINISH: "finished",
    EVC_STATUS_FAULT: "fault",
    EVC_STATUS_RESERVE: "reserved",
    EVC_STATUS_LOCKED: "locked",
    EVC_STATUS_SWITCHING: "switching",
}

# A car is "connected" (plugged in) for every status except idle. Finished and
# paused still mean the cable is in and a new start command can resume it.
_CONNECTED_STATUSES = frozenset({
    EVC_STATUS_CONNECTED, EVC_STATUS_START, EVC_STATUS_CHARGING,
    EVC_STATUS_PAUSE, EVC_STATUS_FINISH, EVC_STATUS_SWITCHING,
})

# Per-phase current (A) above which a phase is considered "live" when
# inferring single- vs three-phase from the measured currents.
_PHASE_LIVE_AMPS = 0.5


def status_label(status: int) -> str:
    """Human-readable label for an EVC status code."""
    return _STATUS_LABELS.get(status, f"unknown({status})")


def is_connected(status: int) -> bool:
    """True when a car is plugged in (any state except idle)."""
    return status in _CONNECTED_STATUSES


def is_charging(status: int) -> bool:
    """True when the charger is actively delivering energy."""
    return status == EVC_STATUS_CHARGING


def phases_from_currents(
    l1: float, l2: float, l3: float, *, threshold: float = _PHASE_LIVE_AMPS
) -> int:
    """Infer the live phase count from per-phase currents.

    Returns the number of phases carrying current above `threshold`. Used
    instead of register 0x1010, which misreports the phase sequence. When no
    phase is live (not charging) this returns 0.
    """
    return sum(1 for a in (l1, l2, l3) if a > threshold)


def single_phase_amps_from_surplus(
    surplus_kw: float,
    *,
    voltage: float = 230.0,
    min_amps: int = 6,
    max_amps: int = 16,
) -> int:
    """Map a solar surplus (kW) to a single-phase current (A).

    Floors to whole amps so any fractional surplus flows to the house battery
    rather than being pulled from the grid. Returns 0 when the surplus cannot
    sustain the single-phase minimum (~1.4 kW at 6 A), signalling "stop".
    """
    if surplus_kw <= 0:
        return 0
    raw = int(surplus_kw * 1000.0 // voltage)  # floor to whole amps
    if raw < min_amps:
        return 0
    return min(max_amps, raw)


class ModbusError(Exception):
    """A Modbus transaction failed (exception response or transport error)."""


class FoxessModbusClient:
    """Minimal async Modbus TCP client for the FoxESS charger.

    Not a general-purpose library: it implements only the function codes this
    backend needs (FC3 read, FC6 write-single, FC16 write-multiple) and frames
    by the MBAP length so split TCP segments cannot desync the stream. A lock
    serialises transactions over the single connection.
    """

    def __init__(self, host: str, port: int = 502, unit_id: int = 1, *, timeout: float = 5.0):
        self._host = host
        self._port = port
        self._unit = unit_id
        self._timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._tid = 0
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def async_connect(self) -> None:
        if self.connected:
            return
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self._host, self._port), timeout=self._timeout
        )

    async def async_close(self) -> None:
        writer, self._writer, self._reader = self._writer, None, None
        if writer is not None:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:  # noqa: BLE001 — closing best-effort
                pass

    async def _ensure(self) -> None:
        if not self.connected:
            await self.async_connect()

    async def _txn(self, pdu: bytes) -> bytes:
        """Send one PDU, return the response PDU (starting at the function code).

        Reconnects once and retries on a transport error so a dropped
        connection between heartbeats doesn't fail the cycle.
        """
        async with self._lock:
            for attempt in (1, 2):
                try:
                    await self._ensure()
                    return await asyncio.wait_for(self._txn_once(pdu), timeout=self._timeout)
                except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError) as err:
                    await self.async_close()
                    if attempt == 2:
                        raise ModbusError(f"transport error: {err}") from err
            raise ModbusError("unreachable")  # pragma: no cover

    async def _txn_once(self, pdu: bytes) -> bytes:
        assert self._reader is not None and self._writer is not None
        self._tid = (self._tid + 1) & 0xFFFF
        frame = struct.pack(">HHHB", self._tid, 0, len(pdu) + 1, self._unit) + pdu
        self._writer.write(frame)
        await self._writer.drain()
        header = await self._reader.readexactly(7)  # tid, proto, len, unit
        length = struct.unpack(">H", header[4:6])[0]
        rest = await self._reader.readexactly(length - 1)  # length includes the unit byte
        return rest  # begins with the function code

    async def read(self, addr: int, count: int) -> list[int]:
        """FC3 read of `count` holding registers from `addr`."""
        resp = await self._txn(struct.pack(">BHH", 3, addr, count))
        if resp[0] & 0x80:
            raise ModbusError(f"read 0x{addr:04X} exception {resp[1]}")
        byte_count = resp[1]
        data = resp[2:2 + byte_count]
        return [struct.unpack(">H", data[i:i + 2])[0] for i in range(0, byte_count, 2)]

    async def write_single(self, addr: int, value: int) -> None:
        """FC6 write to a single (write-only) register."""
        resp = await self._txn(struct.pack(">BHH", 6, addr, value & 0xFFFF))
        if resp[0] & 0x80:
            raise ModbusError(f"write_single 0x{addr:04X} exception {resp[1]}")

    async def write_multi(self, addr: int, values: list[int]) -> None:
        """FC16 write to one or more read/write registers."""
        count = len(values)
        pdu = struct.pack(">BHHB", 16, addr, count, count * 2)
        pdu += b"".join(struct.pack(">H", v & 0xFFFF) for v in values)
        resp = await self._txn(pdu)
        if resp[0] & 0x80:
            raise ModbusError(f"write_multi 0x{addr:04X} exception {resp[1]}")


class FoxessModbusCharger:
    """Single-phase EV charger backend (Phase 1).

    Wraps a `FoxessModbusClient` with charger semantics: read a state snapshot,
    start/stop, and a single `async_apply` heartbeat that holds single-phase
    and sets the requested current. The control loop calls `async_apply` every
    cycle so the setpoint never expires.
    """

    def __init__(
        self,
        host: str,
        port: int,
        unit_id: int,
        *,
        single_phase_cap_kw: float,
        three_phase_cap_kw: float,
        min_amps: int,
        max_amps: int,
        suspend_interval_min: int,
    ):
        self._client = FoxessModbusClient(host, port, unit_id)
        # 0x3002 unit = 0.1 kW. The cap selects the phase count: the single
        # value keeps the charger single-phase, the three value lets it run
        # three-phase (auto-switching picks based on the cap).
        self._single_cap_raw = int(round(single_phase_cap_kw * 10))
        self._three_cap_raw = int(round(three_phase_cap_kw * 10))
        self._min_amps = min_amps
        self._max_amps = max_amps
        self._suspend_interval_min = suspend_interval_min
        self._interval_set = False   # write 0x300B once per connection

    async def async_close(self) -> None:
        await self._client.async_close()

    async def read_state(self) -> dict:
        """Return a snapshot: status, label, connected/charging, currents, power, phases."""
        block = await self._client.read(REG_STATUS, 1)
        status = block[0]
        currents_raw = await self._client.read(REG_PHASE_CURRENT, 3)
        l1, l2, l3 = (c * 0.1 for c in currents_raw)
        power_raw = await self._client.read(REG_ACTIVE_POWER, 1)
        return {
            "status": status,
            "status_label": status_label(status),
            "connected": is_connected(status),
            "charging": is_charging(status),
            "l1": round(l1, 1),
            "l2": round(l2, 1),
            "l3": round(l3, 1),
            "power_kw": round(power_raw[0] * 0.1, 2),
            "live_phases": phases_from_currents(l1, l2, l3),
        }

    async def async_start(self) -> None:
        # The charger rejects a start (exception 3) when it's in a state where
        # one is invalid — e.g. already charging, or "finished" and not yet
        # ready to resume. That's expected, not an error worth surfacing, so
        # swallow it (debug-only) instead of failing the whole heartbeat.
        try:
            await self._client.write_single(REG_CHARGING_CTRL, 1)
        except ModbusError as err:
            _LOGGER.debug("FoxESS charger declined start (%s) — will retry when idle", err)

    async def async_stop(self) -> None:
        await self._client.write_single(REG_CHARGING_CTRL, 2)

    async def async_set_current(self, amps: int) -> None:
        """Set the per-phase max current (0x3001), clamped to the envelope."""
        clamped = max(self._min_amps, min(self._max_amps, amps))
        await self._client.write_multi(REG_MAX_CURRENT, [clamped * 10])

    async def async_apply(
        self, amps: int, *, phases: int = 1, status: int | None = None, drawing: bool = False,
    ) -> None:
        """Heartbeat: hold the requested phase mode and assert the current.

        Must be called every control cycle. `amps <= 0` stops charging;
        otherwise this ensures the session is running and re-asserts the power
        cap (which selects single- vs three-phase) and current so the setpoint
        never expires. `phases` is 1 or 3 — the controller decides it with
        hysteresis and respects the suspend interval before changing it.

        `drawing` is whether the charger is actually pulling current right now.
        The start command is only sent when it is NOT drawing — the L11PMC
        occasionally blips to "finished" mid-charge, and firing start then just
        gets rejected (exception 3) and adds churn while it's already charging.

        Pass `status` from a prior `read_state` to avoid an extra read; when
        omitted it is fetched.
        """
        if status is None:
            status = (await self._client.read(REG_STATUS, 1))[0]

        if amps <= 0:
            if is_charging(status):
                await self.async_stop()
            return

        # Hold the suspend interval at its minimum so a phase downshift switches
        # promptly instead of pausing the session. Idempotent; write once.
        if not self._interval_set:
            try:
                await self._client.write_multi(
                    REG_SUSPEND_INTERVAL, [self._suspend_interval_min])
                self._interval_set = True
            except ModbusError:
                pass  # retry next cycle

        # Keep auto-switching on and write the cap for the requested phase mode,
        # then set the current.
        cap_raw = self._three_cap_raw if phases == 3 else self._single_cap_raw
        await self._client.write_multi(REG_AUTO_PHASE, [1])
        await self._client.write_multi(REG_MAX_POWER, [cap_raw])
        await self.async_set_current(amps)

        # Start the session only if a car is connected AND not already drawing
        # current — so a momentary "finished" blip during an active charge
        # doesn't trigger a futile (rejected) start.
        if not drawing and status in (EVC_STATUS_CONNECTED, EVC_STATUS_FINISH, EVC_STATUS_PAUSE):
            await self.async_start()
