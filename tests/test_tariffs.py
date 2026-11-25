"""DataHub tariff schedule fetch (v1.22.1)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from custom_components.battery_arbitrage import tariffs

NOW = datetime(2026, 10, 2, 9, 0, tzinfo=timezone.utc)


def _flat(code, price, vf="2026-01-01T00:00:00", vt="2027-01-01T00:00:00"):
    return {"ChargeTypeCode": code, "Note": code, "ValidFrom": vf, "ValidTo": vt,
            "Price1": price}


async def _run(monkeypatch, records, **kwargs):
    calls = []

    async def fake_fetch(session, gln, start, limit, end=None, sort=None, codes=None):
        calls.append({"start": start, "sort": sort, "codes": codes})
        return [r for r in records if codes is None or r["ChargeTypeCode"] in codes]

    monkeypatch.setattr(tariffs, "_fetch_raw_records", fake_fetch)
    out = await tariffs.fetch_tariff_schedule(None, "gln", NOW, **kwargs)
    return out, calls


class TestTariffSchedule:
    async def test_energinet_codes_requested_and_summed(self, monkeypatch):
        records = [_flat("40021", 0.02), _flat("40000", 0.043), _flat("41000", 0.072)]
        out, calls = await _run(monkeypatch, records,
                          allowed_codes=frozenset({"40000", "41000"}))
        assert out == [0.115] * 24
        assert all(c["codes"] == frozenset({"40000", "41000"}) for c in calls)

    async def test_equal_rates_of_distinct_codes_both_count(self, monkeypatch):
        records = [_flat("40000", 0.05), _flat("41000", 0.05)]
        out, _ = await _run(monkeypatch, records,
                      allowed_codes=frozenset({"40000", "41000"}))
        assert out == [0.1] * 24

    async def test_history_query_reads_newest_first(self, monkeypatch):
        _, calls = await _run(monkeypatch, [])
        past = [c for c in calls if c["start"] == tariffs._TARIFF_LOOKBACK_START]
        assert past and past[0]["sort"] == "ValidFrom desc"


class _Resp:
    def __init__(self, status, records=None, headers=None):
        self.status = status
        self._records = records or []
        self.headers = headers or {}

    def raise_for_status(self):
        pass

    async def json(self, content_type=None):
        return {"records": self._records}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    def get(self, url, timeout=None):
        self.urls.append(url)
        return self.responses.pop(0)


class TestRequestPacing:
    """v1.32.2 — DatahubPricelist requests are paced, wait out 429, and
    identical queries are answered from a short cache."""

    @pytest.fixture(autouse=True)
    def _clean(self, monkeypatch):
        monkeypatch.setattr(tariffs, "_last_request_at", None)
        monkeypatch.setattr(tariffs, "_response_cache", {})
        self.sleeps = []
        self.clock = [1000.0]

        async def fake_sleep(seconds):
            self.sleeps.append(seconds)
            self.clock[0] += seconds

        monkeypatch.setattr(tariffs.asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(tariffs.time, "monotonic", lambda: self.clock[0])

    async def test_429_waits_for_retry_after(self):
        session = _Session([
            _Resp(429, headers={"Retry-After": "60"}),
            _Resp(200, records=[{"x": 1}]),
        ])
        records = await tariffs._fetch_raw_records(session, "gln", "2022-01-01", 500)
        assert records == [{"x": 1}]
        assert 60 in self.sleeps

    async def test_429_without_header_waits_the_default(self):
        session = _Session([_Resp(429), _Resp(200)])
        await tariffs._fetch_raw_records(session, "gln", "2022-01-01", 500)
        assert tariffs._RETRY_AFTER_DEFAULT_SECONDS in self.sleeps

    async def test_requests_are_spaced(self):
        session = _Session([_Resp(200), _Resp(200)])
        await tariffs._fetch_raw_records(session, "gln-a", "2022-01-01", 500)
        await tariffs._fetch_raw_records(session, "gln-b", "2022-01-01", 500)
        assert len(session.urls) == 2
        assert self.sleeps == [pytest.approx(tariffs._MIN_REQUEST_GAP_SECONDS)]

    async def test_parallel_callers_are_serialised(self):
        import asyncio
        session = _Session([_Resp(200), _Resp(200)])
        await asyncio.gather(
            tariffs._fetch_raw_records(session, "gln-a", "2022-01-01", 500),
            tariffs._fetch_raw_records(session, "gln-b", "2022-01-01", 500),
        )
        assert len(session.urls) == 2
        assert self.sleeps == [pytest.approx(tariffs._MIN_REQUEST_GAP_SECONDS)]

    async def test_identical_query_is_served_from_cache(self):
        session = _Session([_Resp(200, records=[{"x": 1}])])
        first = await tariffs._fetch_raw_records(session, "gln", "2022-01-01", 500, sort="ValidFrom desc")
        second = await tariffs._fetch_raw_records(session, "gln", "2022-01-01", 500, sort="ValidFrom desc")
        assert first == second == [{"x": 1}]
        assert len(session.urls) == 1

    async def test_cache_expires(self):
        session = _Session([_Resp(200), _Resp(200)])
        await tariffs._fetch_raw_records(session, "gln", "2022-01-01", 500)
        self.clock[0] += tariffs._CACHE_SECONDS + 1
        await tariffs._fetch_raw_records(session, "gln", "2022-01-01", 500)
        assert len(session.urls) == 2

    async def test_failure_is_not_cached(self):
        session = _Session([_Resp(500)] * tariffs._FETCH_RETRIES + [_Resp(200, records=[{"x": 1}])])
        assert await tariffs._fetch_raw_records(session, "gln", "2022-01-01", 500) == []
        assert await tariffs._fetch_raw_records(session, "gln", "2022-01-01", 500) == [{"x": 1}]
