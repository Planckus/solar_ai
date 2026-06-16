"""Tests for the FoxESS Modbus charger backend (foxess_charger.py).

Covers the pure decision helpers (status semantics, phase inference,
surplus→amps mapping) and the Modbus client's framing — specifically that
a response split across two TCP segments is reassembled by the MBAP length
field rather than desyncing the stream (the bug seen against the real device).

No network or Home Assistant is required: the client is exercised against a
fake asyncio reader/writer pair.
"""
from __future__ import annotations

import asyncio
import struct

import pytest

from custom_components.battery_arbitrage import foxess_charger as fc


# ── Pure helpers ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("status,connected,charging", [
    (fc.EVC_STATUS_IDLE, False, False),
    (fc.EVC_STATUS_CONNECTED, True, False),
    (fc.EVC_STATUS_CHARGING, True, True),
    (fc.EVC_STATUS_PAUSE, True, False),
    (fc.EVC_STATUS_FINISH, True, False),
    (fc.EVC_STATUS_SWITCHING, True, False),
    (fc.EVC_STATUS_IDLE, False, False),
])
def test_status_semantics(status, connected, charging):
    assert fc.is_connected(status) is connected
    assert fc.is_charging(status) is charging


def test_phases_from_currents():
    assert fc.phases_from_currents(0.0, 0.0, 0.0) == 0      # not charging
    assert fc.phases_from_currents(16.0, 0.0, 0.0) == 1     # single-phase (the test result)
    assert fc.phases_from_currents(6.0, 6.0, 6.0) == 3      # three-phase
    # Noise on idle phases must not count as live.
    assert fc.phases_from_currents(15.9, 0.1, 0.2) == 1


@pytest.mark.parametrize("surplus_kw,expected", [
    (0.0, 0),       # nothing
    (1.0, 0),       # below single-phase 6 A minimum (~1.38 kW) → stop
    (1.4, 6),       # just enough for 6 A
    (2.3, 10),      # 2300 / 230 = 10 A
    (3.68, 16),     # 16 A ceiling
    (5.0, 16),      # clamped at max
])
def test_single_phase_amps_from_surplus(surplus_kw, expected):
    assert fc.single_phase_amps_from_surplus(surplus_kw) == expected


def test_single_phase_amps_floors_to_battery():
    # 2.45 kW → 10 A (2.3 kW), the 0.15 kW remainder goes to the battery, not grid.
    assert fc.single_phase_amps_from_surplus(2.45) == 10


# ── Modbus client framing ────────────────────────────────────────────────

class _FakeWriter:
    def __init__(self):
        self.sent = bytearray()
        self._closing = False

    def write(self, data):
        self.sent += data

    async def drain(self):
        return None

    def is_closing(self):
        return self._closing

    def close(self):
        self._closing = True

    async def wait_closed(self):
        return None


class _FakeReader:
    """Serves bytes from a queue of chunks, honouring readexactly across chunks."""

    def __init__(self, chunks: list[bytes]):
        self._buf = bytearray()
        self._chunks = list(chunks)

    def feed(self, data: bytes):
        self._chunks.append(data)

    async def readexactly(self, n: int) -> bytes:
        while len(self._buf) < n:
            if not self._chunks:
                raise asyncio.IncompleteReadError(bytes(self._buf), n)
            self._buf += self._chunks.pop(0)
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out


def _mbap(tid: int, pdu: bytes, unit: int = 1) -> bytes:
    return struct.pack(">HHHB", tid, 0, len(pdu) + 1, unit) + pdu


def _make_client(reader, writer) -> fc.FoxessModbusClient:
    client = fc.FoxessModbusClient("127.0.0.1")
    client._reader = reader
    client._writer = writer
    return client


def test_read_reassembles_split_response():
    """A read response delivered in two TCP segments must parse correctly."""
    # FC3 reply: 3 registers (6 bytes): 160, 0, 0
    pdu = bytes([3, 6]) + struct.pack(">HHH", 160, 0, 0)
    frame = _mbap(1, pdu)
    # Split mid-PDU so a naive single recv() would desync.
    reader = _FakeReader([frame[:5], frame[5:]])
    writer = _FakeWriter()
    client = _make_client(reader, writer)

    regs = asyncio.get_event_loop().run_until_complete(client.read(fc.REG_MAX_CURRENT, 3))
    assert regs == [160, 0, 0]


def test_read_raises_on_exception_response():
    pdu = bytes([0x83, 0x02])  # FC3 | 0x80, exception code 2
    reader = _FakeReader([_mbap(1, pdu)])
    client = _make_client(reader, _FakeWriter())
    with pytest.raises(fc.ModbusError):
        asyncio.get_event_loop().run_until_complete(client.read(0x9999, 1))


def test_write_multi_frames_fc16():
    pdu_resp = struct.pack(">BHH", 16, fc.REG_MAX_POWER, 1)  # echo addr + count
    reader = _FakeReader([_mbap(1, pdu_resp)])
    writer = _FakeWriter()
    client = _make_client(reader, writer)

    asyncio.get_event_loop().run_until_complete(client.write_multi(fc.REG_MAX_POWER, [30]))
    # Request PDU: unit(1) + fc(0x10) + addr + count + bytecount + value
    sent_pdu = writer.sent[7:]
    assert sent_pdu[0] == 16
    addr, count, bytecount = struct.unpack(">HHB", sent_pdu[1:6])
    assert (addr, count, bytecount) == (fc.REG_MAX_POWER, 1, 2)
    assert struct.unpack(">H", sent_pdu[6:8])[0] == 30
