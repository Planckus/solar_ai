"""Octopus Energy retailer pricing integration (v0.30.0).

Octopus exposes a free public REST API that returns per-half-hour electricity
prices for every product they sell, in every UK GSP (DNO) region. Each rate
entry carries explicit `value_inc_vat` and `value_exc_vat` values, so the
caller gets the full VAT breakdown for free.

This module is transport-only. The coordinator is responsible for caching,
falling back to the manual stack on transport failure, and integrating the
prices into the optimiser's per-slot buy-price computation.

Module surface:
- `fetch_prices(...)` — half-hourly rates for a product+region+time-range.
- `fetch_products(...)` — Octopus catalogue (used by config flow dropdowns).
- `load_bundled_products()` — offline snapshot shipped inside the package.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiohttp

from .const import (
    OCTOPUS_API_BASE,
    OCTOPUS_PRICES_TIMEOUT_SEC,
    OCTOPUS_TARIFF_CODE_TEMPLATE,
)

_LOGGER = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent / "data"
_BUNDLED_PRODUCTS = _DATA_DIR / "octopus_products.json"


# ─────────────────────────────────────────────────────────────────────────────
# Live API
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_products(session: aiohttp.ClientSession) -> list[dict[str, Any]]:
    """Return the Octopus product catalogue. ~32 entries: Agile, Tracker,
    Cosy, Go, Fixed, Variable, plus Outgoing (export) products. Falls back
    to the bundled snapshot if the API is unreachable.
    """
    try:
        out: list[dict[str, Any]] = []
        url: str | None = f"{OCTOPUS_API_BASE}/products/?page_size=100"
        while url:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=OCTOPUS_PRICES_TIMEOUT_SEC),
            ) as r:
                r.raise_for_status()
                data = await r.json()
                out.extend(data.get("results", []))
                url = data.get("next")
        return out
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        _LOGGER.warning(
            "Octopus /products fetch failed (%s); using bundled snapshot",
            e,
        )
        return load_bundled_products()


async def fetch_prices(
    session: aiohttp.ClientSession,
    *,
    product_code: str,
    region: str,
    from_dt: datetime,
    to_dt: datetime,
) -> dict[str, dict[str, Any]] | None:
    """Fetch per-half-hour electricity unit rates for a time range.

    Returns a dict keyed by the slot's UTC ISO timestamp (matching the
    `valid_from` field returned by Octopus, e.g. "2026-05-20T07:00:00Z")
    → the raw Octopus rate dict (which has `value_inc_vat`, `value_exc_vat`,
    `valid_from`, `valid_to`, etc., all in pence/kWh).

    Returns None on transport failure so the caller can fall back to the
    manual stack.
    """
    if from_dt.tzinfo is None:
        from_dt = from_dt.replace(tzinfo=timezone.utc)
    if to_dt.tzinfo is None:
        to_dt = to_dt.replace(tzinfo=timezone.utc)

    tariff_code = OCTOPUS_TARIFF_CODE_TEMPLATE.format(
        product_code=product_code,
        region=region,
    )
    params = {
        "period_from": from_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "period_to":   to_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "page_size":   "100",
    }
    url = (
        f"{OCTOPUS_API_BASE}/products/{product_code}"
        f"/electricity-tariffs/{tariff_code}/standard-unit-rates/"
    )
    out: dict[str, dict[str, Any]] = {}
    try:
        next_url: str | None = url
        first_call = True
        while next_url:
            kwargs = {"params": params} if first_call else {}
            first_call = False
            async with session.get(
                next_url,
                timeout=aiohttp.ClientTimeout(total=OCTOPUS_PRICES_TIMEOUT_SEC),
                **kwargs,
            ) as r:
                if r.status != 200:
                    body = await r.text()
                    _LOGGER.warning(
                        "Octopus /standard-unit-rates returned HTTP %d for "
                        "%s (region=%s): %s",
                        r.status, product_code, region, body[:200],
                    )
                    return None
                data = await r.json()
            for entry in data.get("results", []):
                ts = entry.get("valid_from")
                if ts:
                    out[ts] = entry
            next_url = data.get("next")
            # Safety brake: stop paginating once we have enough data for
            # the asked-for window (Octopus returns descending order,
            # newest first, but we're really only after recent + future
            # rates so a few pages is plenty).
            if len(out) > 500:
                break
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        _LOGGER.warning("Octopus /standard-unit-rates fetch failed: %s", e)
        return None
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Bundled snapshot loader
# ─────────────────────────────────────────────────────────────────────────────

def load_bundled_products() -> list[dict[str, Any]]:
    """Read the offline product-catalogue snapshot shipped inside the
    integration package. Refreshed on each release.
    """
    try:
        with open(_BUNDLED_PRODUCTS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        _LOGGER.error("Bundled Octopus product snapshot unreadable: %s", e)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Rate accessor
# ─────────────────────────────────────────────────────────────────────────────

def get_rate_pence_per_kwh(entry: dict[str, Any]) -> tuple[float, float]:
    """Return (ex_vat, inc_vat) unit rate from an Octopus rate entry,
    both in DKK/kWh-equivalent units i.e. value × 0.01 (pence → pounds).

    Caller is responsible for currency conversion if the integration is
    set to anything other than GBP. Most UK users will just keep currency
    in GBP and the values come out directly comparable to Octopus's web UI.
    """
    ex_vat_p = float(entry.get("value_exc_vat") or 0.0)
    inc_vat_p = float(entry.get("value_inc_vat") or 0.0)
    return (ex_vat_p / 100.0, inc_vat_p / 100.0)
