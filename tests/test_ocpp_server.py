"""Unit tests for the embedded OCPP server ChargePoint.

Covers the reliability behaviours added across v0.40.2–v0.40.6:
  - SetChargingProfile verify + retry (only cache commanded amps on Accepted)
  - duplicate-write dedupe + force override
  - session_active reset on boot and on Available/Preparing status
  - the rolling event log cap

These require the `ocpp` library; the whole module skips cleanly if it's
not installed (e.g. a minimal test env), so it never fails the suite.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("ocpp")  # skip all tests here if the OCPP lib is absent

from custom_components.battery_arbitrage.ocpp_server import ChargePoint  # noqa: E402


def _make_cp() -> ChargePoint:
    """A ChargePoint wired to a mock websocket connection."""
    return ChargePoint("CP_TEST", MagicMock())


def _resp(status):
    r = MagicMock()
    r.status = status
    return r


@pytest.mark.asyncio
async def test_set_current_accepted_caches_and_records():
    cp = _make_cp()
    cp.call = AsyncMock(return_value=_resp("Accepted"))
    assert await cp.set_current(6) is True
    assert cp.last_commanded_amps == 6
    assert cp.last_set_profile_status == "Accepted"
    assert any(e["kind"] == "set_profile" for e in cp.events)


@pytest.mark.asyncio
async def test_set_current_rejected_not_cached():
    cp = _make_cp()
    cp.call = AsyncMock(return_value=_resp("Rejected"))
    # retries=0 keeps the test fast (no backoff sleep)
    assert await cp.set_current(7, retries=0) is False
    # A rejected write must NOT be cached as applied, so the re-assert retries.
    assert cp.last_commanded_amps is None
    assert cp.last_set_profile_status == "Rejected"


@pytest.mark.asyncio
async def test_set_current_dedupe_and_force():
    cp = _make_cp()
    cp.call = AsyncMock(return_value=_resp("Accepted"))
    assert await cp.set_current(6) is True
    cp.call.reset_mock()
    # Same amps, no force → skipped without an OCPP write.
    assert await cp.set_current(6) is True
    cp.call.assert_not_called()
    # force=True re-asserts even when unchanged.
    assert await cp.set_current(6, force=True) is True
    cp.call.assert_called()


@pytest.mark.asyncio
async def test_on_boot_resets_command_and_session_state():
    cp = _make_cp()
    cp.last_commanded_amps = 10
    cp.session_active = True
    await cp.on_boot(charge_point_vendor="Vendor", charge_point_model="Model")
    # A fresh boot has no profile and no transaction.
    assert cp.last_commanded_amps is None
    assert cp.session_active is False


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["Preparing", "Available"])
async def test_on_status_clears_stale_session(status):
    cp = _make_cp()
    cp.session_active = True
    await cp.on_status(status=status)
    assert cp.session_active is False
    assert cp.status == status


@pytest.mark.asyncio
async def test_on_status_charging_keeps_session():
    cp = _make_cp()
    cp.session_active = True
    await cp.on_status(status="Charging")
    # Charging must NOT clear an active session.
    assert cp.session_active is True


def test_event_log_capped_at_50():
    cp = _make_cp()
    for i in range(60):
        cp._log_event("test", str(i))
    assert len(cp.events) == 50
    assert cp.events[-1]["detail"] == "59"
    assert cp.events[0]["detail"] == "10"
