"""Strømligning retailer pricing integration (v0.29.0).

Strømligning (https://stromligning.dk) aggregates Danish electricity retailer
pricing into a single API that returns per-15-minute price breakdowns. Each
breakdown carries the spot price, the retailer's surcharge, the DSO's
distribution tariff for the current hour, Energinet's system and transmission
tariffs, elafgift, and VAT — all as separate components.

This module provides:
- `fetch_prices(...)` for daily price data, returning a per-slot dict keyed by
  ISO timestamp with the full breakdown.
- `fetch_suppliers(...)` and `fetch_companies(...)` for the live DSO and
  retailer catalogues used by the config flow.
- `load_bundled_suppliers()` / `load_bundled_companies()` for the offline
  snapshots shipped inside the integration package — used when the API is
  unreachable during initial setup.

The module is transport-only: it returns Python dicts in the shape Strømligning
publishes, with no integration-specific logic. Coordinator code is responsible
for caching, fallback to manual stack, and override composition.
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
    STROMLIGNING_API_BASE,
    STROMLIGNING_PRICES_TIMEOUT_SEC,
)

_LOGGER = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent / "data"
_BUNDLED_SUPPLIERS = _DATA_DIR / "stromligning_suppliers.json"
_BUNDLED_COMPANIES = _DATA_DIR / "stromligning_companies.json"


# ─────────────────────────────────────────────────────────────────────────────
# Live API
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_suppliers(session: aiohttp.ClientSession) -> list[dict[str, Any]]:
    """Return the list of DSOs from Strømligning. ~35 entries.

    Falls back to the bundled snapshot if the API is unreachable. Each entry
    has `id`, `name`, `companyName`, `priceArea`, and `customerGroups`.
    """
    try:
        async with session.get(
            f"{STROMLIGNING_API_BASE}/suppliers",
            timeout=aiohttp.ClientTimeout(total=STROMLIGNING_PRICES_TIMEOUT_SEC),
        ) as r:
            r.raise_for_status()
            return await r.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        _LOGGER.warning(
            "Strømligning /suppliers fetch failed (%s); using bundled snapshot",
            e,
        )
        return load_bundled_suppliers()


async def fetch_companies(session: aiohttp.ClientSession) -> list[dict[str, Any]]:
    """Return the list of electricity retailers. ~91 entries, each with one
    or more products.

    Falls back to the bundled snapshot if the API is unreachable.
    """
    try:
        async with session.get(
            f"{STROMLIGNING_API_BASE}/companies",
            timeout=aiohttp.ClientTimeout(total=STROMLIGNING_PRICES_TIMEOUT_SEC),
        ) as r:
            r.raise_for_status()
            return await r.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        _LOGGER.warning(
            "Strømligning /companies fetch failed (%s); using bundled snapshot",
            e,
        )
        return load_bundled_companies()


async def fetch_prices(
    session: aiohttp.ClientSession,
    *,
    product_id: str,
    supplier_id: str,
    customer_group_id: str,
    price_area: str,
    from_dt: datetime,
    to_dt: datetime,
) -> dict[str, dict[str, Any]] | None:
    """Fetch per-15-min price breakdowns for a time range.

    Returns a dict keyed by the slot's UTC ISO timestamp (e.g.
    "2026-05-20T07:00:00+00:00") → breakdown dict in Strømligning's native
    shape. Returns None on transport failure so the caller can fall back.
    """
    if from_dt.tzinfo is None:
        from_dt = from_dt.replace(tzinfo=timezone.utc)
    if to_dt.tzinfo is None:
        to_dt = to_dt.replace(tzinfo=timezone.utc)

    params = {
        "productId": product_id,
        "supplierId": supplier_id,
        "customerGroupId": customer_group_id,
        "priceArea": price_area,
        "from": from_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "to":   to_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    }
    try:
        async with session.get(
            f"{STROMLIGNING_API_BASE}/prices",
            params=params,
            timeout=aiohttp.ClientTimeout(total=STROMLIGNING_PRICES_TIMEOUT_SEC),
        ) as r:
            if r.status != 200:
                body = await r.text()
                _LOGGER.warning(
                    "Strømligning /prices returned HTTP %d (params=%s): %s",
                    r.status, params, body[:200],
                )
                return None
            data = await r.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        _LOGGER.warning("Strømligning /prices fetch failed: %s", e)
        return None

    out: dict[str, dict[str, Any]] = {}
    for entry in data.get("prices", []):
        ts_raw = entry.get("date")
        if not ts_raw:
            continue
        # Canonical slot key — must match the format and resolution used by
        # every lookup site (coordinator `_compute_buy_price`, sensor
        # `_current_stromligning_entry`). Two invariants:
        #
        #   1. Trailing format is `.000Z`. Strømligning's `date` field comes
        #      back in either "...+00:00" or "....000Z" depending on API
        #      revision; v0.39.1 unified that — without normalisation,
        #      lookups silently missed every slot and the breakdown sensor
        #      read all-zero attributes.
        #
        #   2. Minute resolution is 15-min aligned, NOT hour aligned.
        #      Strømligning publishes 15-min slots (the entry carries
        #      `resolution: "15m"`); the optimizer iterates at 15-min
        #      native resolution since v0.36.0. v0.39.1 mistakenly used
        #      `minute=0` which collapsed all 4 quarters into the same
        #      hour key — last-write-wins meant only the :45 quarter
        #      survived, and every intra-hour lookup got that single
        #      value. Fixed in v0.39.6 by aligning to the 15-min
        #      boundary. If the API ever returns hourly slots
        #      (resolution `"1h"`), the entry will already sit at
        #      minute=0 here and the lookup sites fall back to an
        #      hour-aligned key on miss.
        try:
            dt = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
            dt_utc = dt.astimezone(timezone.utc)
            slot_minute = (dt_utc.minute // 15) * 15
            canonical = dt_utc.replace(
                minute=slot_minute, second=0, microsecond=0,
            ).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        except (ValueError, AttributeError) as err:
            _LOGGER.debug(
                "Strømligning entry has unparseable date '%s' (%s) — skipping",
                ts_raw, err,
            )
            continue
        out[canonical] = entry
    # v0.39.4 diagnostic — one-line confirmation that the cache has been
    # populated and the keys are in the format the lookups expect. Helps
    # nail down why the buy-price breakdown sensor was showing all-0.0
    # attributes. Remove or downgrade to DEBUG once verified.
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Bundled snapshot loaders
# ─────────────────────────────────────────────────────────────────────────────

def load_bundled_suppliers() -> list[dict[str, Any]]:
    """Read the offline supplier snapshot shipped inside the integration
    package. Refreshed on each release."""
    try:
        with open(_BUNDLED_SUPPLIERS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        _LOGGER.error("Bundled Strømligning supplier snapshot unreadable: %s", e)
        return []


def load_bundled_companies() -> list[dict[str, Any]]:
    """Read the offline retailer snapshot shipped inside the integration
    package. Refreshed on each release."""
    try:
        with open(_BUNDLED_COMPANIES, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        _LOGGER.error("Bundled Strømligning company snapshot unreadable: %s", e)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Breakdown access helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_price_details(entry: dict[str, Any]) -> dict[str, float]:
    """Flatten a Strømligning price entry into the components Solar AI uses.

    Returns a dict with all values in DKK/kWh, ex-VAT:
        spot           — electricity (Nord Pool spot)
        surcharge      — retailer markup
        net_tariff     — Energinet transmission tariff
        system_tariff  — Energinet system tariff
        distribution   — DSO distribution tariff (time-of-day variable)
        elafgift       — Electricity duty
        vat_pct        — Effective VAT percentage (derived from value vs total)
        total_inc_vat  — All-in price for direct use
    """
    # v0.39.5 — Strømligning API entry shape:
    #   {
    #     "date": "...",
    #     "price":   {"value": <ex-VAT>, "total": <inc-VAT>, ...},
    #     "details": {"electricity": {...}, "surcharge": {...},
    #                 "transmission": {"netTariff": {...}, "systemTariff": {...}},
    #                 "electricityTax": {...}, "distribution": {...}}
    #   }
    # Older code assumed an extra level of nesting (entry["price"]["price"]
    # and entry["price"]["details"]). That has not matched the live API for
    # some time — the lookups silently returned zeros via KeyError-swallowing
    # try/except, and every buy-price calculation fell back to the manual
    # stack. Confirmed against the live API on 2026-05-25.
    price = entry.get("price", {}) or {}
    details = entry.get("details", {}) or {}
    elec = (details.get("electricity") or {}).get("value", 0.0)
    surc = (details.get("surcharge") or {}).get("value", 0.0)
    elaf = (details.get("electricityTax") or {}).get("value", 0.0)
    dist = (details.get("distribution") or {}).get("value", 0.0)
    transmission = details.get("transmission") or {}
    net  = (transmission.get("netTariff") or {}).get("value", 0.0)
    syst = (transmission.get("systemTariff") or {}).get("value", 0.0)
    total = price.get("total", 0.0)
    ex_vat = price.get("value", 0.0)
    vat_pct = 0.0
    if ex_vat > 0:
        vat_pct = round((total / ex_vat - 1.0) * 100, 2)
    return {
        "spot":          float(elec),
        "surcharge":     float(surc),
        "net_tariff":    float(net),
        "system_tariff": float(syst),
        "distribution":  float(dist),
        "elafgift":      float(elaf),
        "vat_pct":       vat_pct,
        "total_inc_vat": float(total),
    }
