"""Tests for Pstryk pricing (Poland): parsing, unpublished days, transport and
the coordinator's use of the prices."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from custom_components.battery_arbitrage import const as C
from custom_components.battery_arbitrage import pstryk
from custom_components.battery_arbitrage.coordinator import BatteryArbitrageCoordinator

WAW = ZoneInfo("Europe/Warsaw")
# 10:00 local in Warsaw (UTC+1 in November) = 09:00 UTC
NOW = datetime(2026, 11, 24, 9, 0, tzinfo=timezone.utc)


def _frames(day_start_utc: datetime, hours: int, buy_fn, sell_fn, nested=True):
    out = []
    for h in range(hours):
        start = day_start_utc + timedelta(hours=h)
        prices = {"price_gross": buy_fn(h), "price_prosumer_gross": sell_fn(h)}
        frame = {
            "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": (start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if nested:
            frame["metrics"] = {"pricing": prices}
        else:
            frame.update(prices)
        out.append(frame)
    return out


TODAY_UTC = datetime(2026, 11, 23, 23, 0, tzinfo=timezone.utc)      # 00:00 Warsaw
TOMORROW_UTC = TODAY_UTC + timedelta(days=1)


class TestParseFrames:
    def test_nested_and_flat_prices(self):
        frames = _frames(TODAY_UTC, 2, lambda h: 1.0 + h, lambda h: 0.4 + h)
        frames += _frames(TODAY_UTC + timedelta(hours=2), 1, lambda h: 3.0, lambda h: 2.4,
                          nested=False)
        slots = pstryk.parse_frames(frames)
        assert [s["buy"] for s in slots] == [1.0, 2.0, 3.0]
        assert [s["sell"] for s in slots] == [0.4, 1.4, 2.4]
        assert slots[0]["start"] == "2026-11-23T23:00:00+00:00"

    def test_comma_decimals_and_incomplete_frames(self):
        frames = [
            {"start": "2026-11-24T10:00:00Z",
             "metrics": {"pricing": {"price_gross": "1,25", "price_prosumer_gross": "0,5"}}},
            {"start": "2026-11-24T11:00:00Z",
             "metrics": {"pricing": {"price_gross": 1.3}}},           # no sell price
            {"metrics": {"pricing": {"price_gross": 1, "price_prosumer_gross": 1}}},  # no start
        ]
        slots = pstryk.parse_frames(frames)
        assert slots == [{"start": "2026-11-24T10:00:00+00:00", "buy": 1.25, "sell": 0.5}]

    def test_sorted_by_start(self):
        frames = _frames(TODAY_UTC, 3, lambda h: h, lambda h: h)[::-1]
        starts = [s["start"] for s in pstryk.parse_frames(frames)]
        assert starts == sorted(starts)


class TestUnpublishedDays:
    def _slots(self, tomorrow_frames):
        today = _frames(TODAY_UTC, 24, lambda h: 1.0 + h / 10, lambda h: 0.5 + h / 10)
        return pstryk.parse_frames(today + tomorrow_frames)

    def test_published_tomorrow_is_kept(self):
        slots = self._slots(_frames(TOMORROW_UTC, 24, lambda h: 2 + h / 10, lambda h: 1 + h / 10))
        assert len(pstryk.drop_unpublished_days(slots, NOW, WAW)) == 48

    def test_placeholder_tomorrow_is_dropped(self):
        slots = self._slots(_frames(TOMORROW_UTC, 24, lambda h: 1.11, lambda h: 0.5 + h / 10))
        kept = pstryk.drop_unpublished_days(slots, NOW, WAW)
        assert len(kept) == 24
        assert kept[-1]["start"] == "2026-11-24T22:00:00+00:00"

    def test_incomplete_tomorrow_is_dropped(self):
        slots = self._slots(_frames(TOMORROW_UTC, 10, lambda h: 2 + h, lambda h: 1 + h))
        assert len(pstryk.drop_unpublished_days(slots, NOW, WAW)) == 24

    def test_incomplete_today_is_kept(self):
        slots = pstryk.parse_frames(_frames(TODAY_UTC, 5, lambda h: 1.0, lambda h: 0.5))
        assert len(pstryk.drop_unpublished_days(slots, NOW, WAW)) == 5


def test_pricing_url_covers_local_today_and_tomorrow():
    url = pstryk.pricing_url(NOW, WAW)
    assert url.startswith("https://api.pstryk.pl/integrations/meter-data/unified-metrics/")
    assert "metrics=pricing" in url and "resolution=hour" in url
    assert "window_start=2026-11-23T23:00:00Z" in url
    assert "window_end=2026-11-25T23:00:00Z" in url


class _Response:
    def __init__(self, status, body=None, headers=None):
        self.status = status
        self._body = body
        self.headers = headers or {}

    async def json(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Session:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers))
        return self.response


class TestFetchPrices:
    async def test_ok_returns_slots_and_sends_key(self):
        body = {"frames": _frames(TODAY_UTC, 24, lambda h: 1 + h / 10, lambda h: 0.5 + h / 10)}
        session = _Session(_Response(200, body))
        slots = await pstryk.fetch_prices(session, "secret-key", NOW, WAW)
        assert len(slots) == 24
        assert session.calls[0][1]["Authorization"] == "secret-key"

    async def test_rejected_key_raises(self):
        with pytest.raises(pstryk.PstrykAuthError):
            await pstryk.fetch_prices(_Session(_Response(401)), "bad", NOW, WAW)

    async def test_rate_limit_uses_retry_after(self):
        with pytest.raises(pstryk.PstrykRateLimited) as err:
            await pstryk.fetch_prices(
                _Session(_Response(429, headers={"Retry-After": "120"})), "k", NOW, WAW)
        assert err.value.retry_after == 120

    async def test_rate_limit_without_header_uses_default(self):
        with pytest.raises(pstryk.PstrykRateLimited) as err:
            await pstryk.fetch_prices(_Session(_Response(429)), "k", NOW, WAW)
        assert err.value.retry_after == C.PSTRYK_RATE_LIMIT_DEFAULT_SECONDS

    async def test_server_error_returns_none(self):
        assert await pstryk.fetch_prices(_Session(_Response(500)), "k", NOW, WAW) is None

    async def test_empty_frames_return_none(self):
        assert await pstryk.fetch_prices(_Session(_Response(200, {"frames": []})), "k", NOW, WAW) is None


def _coord(api_key="secret-key"):
    c = object.__new__(BatteryArbitrageCoordinator)
    c._stored = {C.CONF_BUY_PRICE_MODE: C.BUY_PRICE_MODE_PSTRYK}
    c.config = {C.CONF_PSTRYK_API_KEY: api_key}
    c._cached_pstryk_buy = {}
    c._pstryk_not_before = None
    c._cached_grid_rates = {"rates": [{"start": "2026-11-24T09:00:00+00:00", "value": 0.9}]}
    return c


SLOTS = [
    {"start": "2026-11-24T09:00:00+00:00", "buy": 1.10, "sell": 0.45},
    {"start": "2026-11-24T10:00:00+00:00", "buy": 1.35, "sell": 0.60},
]


class TestCoordinatorRefresh:
    async def test_success_sets_sell_curve_and_buy_cache(self):
        c = _coord()
        with patch.object(pstryk, "fetch_prices", AsyncMock(return_value=SLOTS)):
            assert await c._refresh_pstryk_prices(None, NOW) is True
        assert c._cached_grid_rates == {"rates": [
            {"start": "2026-11-24T09:00:00+00:00", "value": 0.45},
            {"start": "2026-11-24T10:00:00+00:00", "value": 0.60},
        ]}
        assert c._cached_pstryk_buy == {
            "2026-11-24T09:00:00+00:00": 1.10, "2026-11-24T10:00:00+00:00": 1.35}

    async def test_no_key_never_keeps_another_markets_prices(self):
        c = _coord(api_key="")
        fetch = AsyncMock()
        with patch.object(pstryk, "fetch_prices", fetch):
            assert await c._refresh_pstryk_prices(None, NOW) is False
        fetch.assert_not_awaited()
        assert c._cached_grid_rates == {"rates": []}

    async def test_failure_keeps_last_good_prices(self):
        c = _coord()
        with patch.object(pstryk, "fetch_prices", AsyncMock(return_value=SLOTS)):
            await c._refresh_pstryk_prices(None, NOW)
        good = c._cached_grid_rates
        with patch.object(pstryk, "fetch_prices", AsyncMock(return_value=None)):
            assert await c._refresh_pstryk_prices(None, NOW + timedelta(hours=1)) is False
        assert c._cached_grid_rates == good
        assert c._cached_pstryk_buy

    async def test_rejected_key_waits_an_hour(self):
        c = _coord()
        fetch = AsyncMock(side_effect=pstryk.PstrykAuthError("HTTP 401"))
        with patch.object(pstryk, "fetch_prices", fetch):
            await c._refresh_pstryk_prices(None, NOW)
            await c._refresh_pstryk_prices(None, NOW + timedelta(minutes=5))
            assert fetch.await_count == 1
            await c._refresh_pstryk_prices(None, NOW + timedelta(hours=1))
            assert fetch.await_count == 2

    async def test_rate_limit_waits_retry_after(self):
        c = _coord()
        fetch = AsyncMock(side_effect=pstryk.PstrykRateLimited(600))
        with patch.object(pstryk, "fetch_prices", fetch):
            await c._refresh_pstryk_prices(None, NOW)
            await c._refresh_pstryk_prices(None, NOW + timedelta(minutes=9))
            assert fetch.await_count == 1
        assert c._pstryk_not_before == NOW + timedelta(seconds=600)


class TestBuyPrice:
    def _buy(self, c, slot_start):
        # Danish components are passed but must not be applied in Pstryk mode.
        return c._compute_buy_price(
            spot=0.45, hour=10, slot_start_dt=slot_start,
            spot_markup=0.1, tariff_this_hour_dso=0.7, elafgift=0.9, vat_factor=1.25)

    def test_slot_price_from_cache(self):
        c = _coord()
        c._cached_pstryk_buy = {s["start"]: s["buy"] for s in SLOTS}
        assert self._buy(c, datetime(2026, 11, 24, 9, 0, tzinfo=timezone.utc)) == 1.10

    def test_mid_hour_and_local_time_map_to_the_hour(self):
        c = _coord()
        c._cached_pstryk_buy = {s["start"]: s["buy"] for s in SLOTS}
        # 11:30 Warsaw = 10:30 UTC -> the 10:00 UTC hour
        assert self._buy(c, datetime(2026, 11, 24, 11, 30, tzinfo=WAW)) == 1.35

    def test_unknown_slot_gets_highest_known_price(self):
        c = _coord()
        c._cached_pstryk_buy = {s["start"]: s["buy"] for s in SLOTS}
        assert self._buy(c, datetime(2026, 11, 25, 9, 0, tzinfo=timezone.utc)) == 1.35
