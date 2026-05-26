"""Cache-key shape tests for `stromligning.fetch_prices`.

Locks in the v0.39.6 invariant: the cache must store 15-min-resolution
entries under distinct keys (one per quarter-hour), and the canonical
key format must be the `.000Z` ISO variant that every lookup site uses.

Why this test exists: v0.39.1 introduced a one-line bug that collapsed
all 4 quarters of every hour into a single key (last-write-wins), so
the optimizer and the breakdown sensor read the `:45` quarter's price
for every intra-hour slot. The bug was silent — the cache was populated,
the lookups returned an entry, just the wrong one. This regression
test makes that failure mode loud.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.battery_arbitrage import stromligning as sl


# Realistic Strømligning response shape, captured from the live API on
# 2026-05-26 for product=enkel_energi-enkel_stroem_forbrugsafregnet,
# supplier=dinel_c, area=DK1, customerGroup=c.  Four quarter-hour slots
# across one hour, with strongly varying prices (the case where the
# v0.39.1 collapse bug was visible).
SAMPLE_API_RESPONSE = {
    "priceArea": "DK1",
    "prices": [
        {
            "date": "2026-05-26T07:00:00.000Z",
            "localDate": "2026-05-26T09:00:00",
            "price": {"value": 1.255488, "total": 1.56936, "unit": "kr/kWh"},
            "details": {
                "electricity": {"value": 1.024188, "total": 1.280235},
                "surcharge": {"value": 0.016, "total": 0.02},
                "transmission": {
                    "systemTariff": {"value": 0.072, "total": 0.09},
                    "netTariff": {"value": 0.043, "total": 0.05375},
                },
                "electricityTax": {"value": 0.008, "total": 0.01},
                "distribution": {"value": 0.0923, "total": 0.115375},
            },
            "resolution": "15m",
        },
        {
            "date": "2026-05-26T07:15:00.000Z",
            "localDate": "2026-05-26T09:15:00",
            "price": {"value": 0.923384, "total": 1.15423, "unit": "kr/kWh"},
            "details": {
                "electricity": {"value": 0.692084, "total": 0.865105},
                "surcharge": {"value": 0.016, "total": 0.02},
                "transmission": {
                    "systemTariff": {"value": 0.072, "total": 0.09},
                    "netTariff": {"value": 0.043, "total": 0.05375},
                },
                "electricityTax": {"value": 0.008, "total": 0.01},
                "distribution": {"value": 0.0923, "total": 0.115375},
            },
            "resolution": "15m",
        },
        {
            "date": "2026-05-26T07:30:00.000Z",
            "localDate": "2026-05-26T09:30:00",
            "price": {"value": 0.754492, "total": 0.943115, "unit": "kr/kWh"},
            "details": {
                "electricity": {"value": 0.523192, "total": 0.65399},
                "surcharge": {"value": 0.016, "total": 0.02},
                "transmission": {
                    "systemTariff": {"value": 0.072, "total": 0.09},
                    "netTariff": {"value": 0.043, "total": 0.05375},
                },
                "electricityTax": {"value": 0.008, "total": 0.01},
                "distribution": {"value": 0.0923, "total": 0.115375},
            },
            "resolution": "15m",
        },
        {
            "date": "2026-05-26T07:45:00.000Z",
            "localDate": "2026-05-26T09:45:00",
            "price": {"value": 0.347357, "total": 0.434196, "unit": "kr/kWh"},
            "details": {
                "electricity": {"value": 0.116057, "total": 0.145071},
                "surcharge": {"value": 0.016, "total": 0.02},
                "transmission": {
                    "systemTariff": {"value": 0.072, "total": 0.09},
                    "netTariff": {"value": 0.043, "total": 0.05375},
                },
                "electricityTax": {"value": 0.008, "total": 0.01},
                "distribution": {"value": 0.0923, "total": 0.115375},
            },
            "resolution": "15m",
        },
    ],
}


def _mock_session(payload: dict) -> AsyncMock:
    """Build an aiohttp session mock that returns `payload` from any GET."""
    response = MagicMock()
    response.status = 200
    response.raise_for_status = MagicMock()
    response.json = AsyncMock(return_value=payload)
    response.text = AsyncMock(return_value="")

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=response)
    ctx.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.get = MagicMock(return_value=ctx)
    return session


@pytest.mark.asyncio
async def test_fetch_prices_preserves_15min_resolution() -> None:
    """All four 15-min slots in an hour must be cached under distinct keys.

    The v0.39.1 bug collapsed them to a single hour-aligned key. The
    last-written entry (`:45` quarter) was the only one that survived,
    and every lookup — at any minute — returned that single value.
    """
    from datetime import datetime, timezone

    session = _mock_session(SAMPLE_API_RESPONSE)
    cache = await sl.fetch_prices(
        session,
        product_id="enkel_energi-enkel_stroem_forbrugsafregnet",
        supplier_id="dinel_c",
        customer_group_id="c",
        price_area="DK1",
        from_dt=datetime(2026, 5, 26, 7, 0, tzinfo=timezone.utc),
        to_dt=datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc),
    )
    assert cache is not None

    expected_keys = {
        "2026-05-26T07:00:00.000Z",
        "2026-05-26T07:15:00.000Z",
        "2026-05-26T07:30:00.000Z",
        "2026-05-26T07:45:00.000Z",
    }
    assert set(cache.keys()) == expected_keys, (
        f"Cache must hold 4 distinct 15-min keys; got {sorted(cache.keys())}"
    )


@pytest.mark.asyncio
async def test_fetch_prices_each_slot_carries_its_own_components() -> None:
    """The entry at each key must be the entry the API published for
    that quarter — not the next quarter's, and not the hour-aggregate."""
    from datetime import datetime, timezone

    session = _mock_session(SAMPLE_API_RESPONSE)
    cache = await sl.fetch_prices(
        session,
        product_id="enkel_energi-enkel_stroem_forbrugsafregnet",
        supplier_id="dinel_c",
        customer_group_id="c",
        price_area="DK1",
        from_dt=datetime(2026, 5, 26, 7, 0, tzinfo=timezone.utc),
        to_dt=datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc),
    )

    assert cache["2026-05-26T07:00:00.000Z"]["price"]["total"] == pytest.approx(1.56936)
    assert cache["2026-05-26T07:15:00.000Z"]["price"]["total"] == pytest.approx(1.15423)
    assert cache["2026-05-26T07:30:00.000Z"]["price"]["total"] == pytest.approx(0.943115)
    assert cache["2026-05-26T07:45:00.000Z"]["price"]["total"] == pytest.approx(0.434196)


@pytest.mark.asyncio
async def test_fetch_prices_handles_plus_zero_iso_format() -> None:
    """Strømligning may publish `date` in either `+00:00` or `.000Z`
    form. The cache key must always be `.000Z` so it matches the
    lookup keys built at the call sites.
    """
    from datetime import datetime, timezone

    payload = {
        "prices": [
            {
                "date": "2026-05-26T07:00:00+00:00",
                "price": {"value": 1.0, "total": 1.25, "unit": "kr/kWh"},
                "details": {},
                "resolution": "15m",
            },
        ],
    }
    session = _mock_session(payload)
    cache = await sl.fetch_prices(
        session,
        product_id="p", supplier_id="s", customer_group_id="c",
        price_area="DK1",
        from_dt=datetime(2026, 5, 26, 7, 0, tzinfo=timezone.utc),
        to_dt=datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc),
    )
    assert list(cache.keys()) == ["2026-05-26T07:00:00.000Z"]
