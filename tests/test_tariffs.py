"""DataHub tariff schedule fetch (v1.22.1)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from custom_components.battery_arbitrage import tariffs

NOW = datetime(2026, 10, 2, 9, 0, tzinfo=timezone.utc)


def _flat(code, price, vf="2026-01-01T00:00:00", vt="2027-01-01T00:00:00"):
    return {"ChargeTypeCode": code, "Note": code, "ValidFrom": vf, "ValidTo": vt,
            "Price1": price}


def _run(monkeypatch, records, **kwargs):
    calls = []

    async def fake_fetch(session, gln, start, limit, end=None, sort=None, codes=None):
        calls.append({"start": start, "sort": sort, "codes": codes})
        return [r for r in records if codes is None or r["ChargeTypeCode"] in codes]

    monkeypatch.setattr(tariffs, "_fetch_raw_records", fake_fetch)
    out = asyncio.run(tariffs.fetch_tariff_schedule(None, "gln", NOW, **kwargs))
    return out, calls


class TestTariffSchedule:
    def test_energinet_codes_requested_and_summed(self, monkeypatch):
        records = [_flat("40021", 0.02), _flat("40000", 0.043), _flat("41000", 0.072)]
        out, calls = _run(monkeypatch, records,
                          allowed_codes=frozenset({"40000", "41000"}))
        assert out == [0.115] * 24
        assert all(c["codes"] == frozenset({"40000", "41000"}) for c in calls)

    def test_equal_rates_of_distinct_codes_both_count(self, monkeypatch):
        records = [_flat("40000", 0.05), _flat("41000", 0.05)]
        out, _ = _run(monkeypatch, records,
                      allowed_codes=frozenset({"40000", "41000"}))
        assert out == [0.1] * 24

    def test_history_query_reads_newest_first(self, monkeypatch):
        _, calls = _run(monkeypatch, [])
        past = [c for c in calls if c["start"] == tariffs._TARIFF_LOOKBACK_START]
        assert past and past[0]["sort"] == "ValidFrom desc"
