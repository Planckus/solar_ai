"""Fetch hourly DSO/Energinet tariff schedules from Energi Data Service DatahubPricelist."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

_DATAHUB_URL = "https://api.energidataservice.dk/dataset/DatahubPricelist"
_TIMEOUT = aiohttp.ClientTimeout(total=15)

# Historical lookback start date.  Covers all seasonal/annual tariff records
# (Energinet updates once a year, most DSOs update 1–4 times per year).
_TARIFF_LOOKBACK_START = "2022-01-01"

# Limit for the historical lookback query.  Energinet has ~5 records/year,
# most DSOs have ~4 records/year — so 500 covers decades of history for
# any DSO that doesn't do daily updates.
_LOOKBACK_LIMIT = 500

# Limit for the start-from-today query.  DSOs that publish one record per
# day (e.g. Dinel) have ValidFrom=today for today's record.  Since the API
# returns records in ascending ValidFrom order, today's record appears at
# position 0 of this query, so a small limit is sufficient.
_DAILY_LIMIT = 100


async def _fetch_raw_records(
    session: aiohttp.ClientSession,
    gln: str,
    start: str,
    limit: int,
    end: str | None = None,
) -> list[dict]:
    """Fetch raw D03 records from DatahubPricelist for *gln* starting at *start*.

    *end* (optional) adds ``&end=<date>`` to the query.  Setting ``end=tomorrow``
    excludes future pre-published records from the result set, which is critical
    for DSOs (e.g. Dinel) that pre-publish hundreds of daily records months in
    advance — without this filter those records dominate the response and push
    today's record beyond the fetch limit.
    """
    url = (
        f"{_DATAHUB_URL}"
        f'?filter={{"GLN_Number":"{gln}","ChargeType":"D03"}}'
        f"&start={start}"
        f"&limit={limit}"
    )
    if end:
        url += f"&end={end}"
    try:
        async with session.get(url, timeout=_TIMEOUT) as resp:
            resp.raise_for_status()
            data: dict[str, Any] = await resp.json(content_type=None)
            return data.get("records", [])
    except Exception as err:
        _LOGGER.warning(
            "DatahubPricelist fetch failed for GLN %s (start=%s): %s", gln, start, err
        )
        return []


async def fetch_tariff_schedule(
    session: aiohttp.ClientSession,
    gln: str,
    reference_dt: datetime,
    *,
    require_all_prices: bool = False,
    require_varying_prices: bool = False,
    allowed_codes: frozenset[str] | None = None,
) -> list[float]:
    """Return a 24-entry hourly tariff schedule (DKK/kWh) for *gln*.

    Issues **two parallel API queries** to cover both DSO publishing patterns:

    1. ``start=today`` — catches daily-updated DSOs (e.g. Dinel/Radius) where
       each day's tariff record has ``ValidFrom=today`` and ``ValidTo=tomorrow``.
       Because the API returns records in ascending ``ValidFrom`` order, today's
       record sits at position 0 of this query regardless of how many historical
       daily records exist — so the small ``_DAILY_LIMIT`` is always sufficient.

    2. ``start=2022-01-01`` — catches seasonal/annual DSOs and Energinet where a
       single record covers months or years.  Such records have ``ValidFrom`` in
       the past and are therefore missed by query 1; query 2 captures them within
       ``_LOOKBACK_LIMIT`` entries because there are very few records per year.

    Records from both queries are merged and deduplicated by
    ``(ChargeTypeCode, ValidFrom)`` before filtering.

    Args:
        require_all_prices:
            When True, skip any record that does not have all 24 hourly price
            fields populated.  Use this for DSO queries to exclude
            capacity/power charges (Effektbetaling) that only populate Price1.
        require_varying_prices:
            When True, skip records where all 24 prices are identical (flat-rate
            secondary tariffs such as "Nettarif A høj samplaceret").  Use
            alongside ``require_all_prices`` to select only the genuine
            time-of-use nettarif C time record.
        allowed_codes:
            When provided, only records whose ``ChargeTypeCode`` is in this set
            are included.  Use for the Energinet GLN to select only the
            Transmissions nettarif (code ``"40000"``) and exclude the
            Indfødningstarif produktion (``"40010"``), HV tariffs, etc.

    Flat-rate records (only Price1 populated) are treated as a constant
    applied to all 24 hours — this handles the Energinet transmission tariff
    which is the same price every hour.

    Returns a list of 24 zeros on complete API failure (graceful degradation —
    the coordinator keeps the previous cached schedule).
    """
    today_str = reference_dt.strftime("%Y-%m-%d")
    tomorrow_str = (reference_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    # Run both queries in parallel, both capped at end=tomorrow.
    #
    # The end parameter is essential: many DSOs (e.g. Dinel) pre-publish
    # hundreds of future daily records.  Without the cap those records fill
    # the response and push today's nettarif C time record beyond the fetch
    # limit, so it is never seen.  With end=tomorrow:
    #
    # • Query 1 (start=today)       — returns ONLY records whose ValidFrom is
    #   today, i.e. today's daily DSO records.  For Dinel this is 7 records,
    #   including the TCL<100_02 nettarif C time.
    #
    # • Query 2 (start=2022-01-01)  — returns all records from 2022 to today.
    #   Energinet annual records (ValidFrom = Jan 1) and seasonal DSO records
    #   are found here.  Daily DSO records are also present but today's record
    #   is already captured by query 1.
    records_today, records_past = await asyncio.gather(
        _fetch_raw_records(session, gln, today_str, _DAILY_LIMIT, end=tomorrow_str),
        _fetch_raw_records(session, gln, _TARIFF_LOOKBACK_START, _LOOKBACK_LIMIT, end=tomorrow_str),
    )

    # Merge and deduplicate by (ChargeTypeCode, ValidFrom).
    # Prefer records from the today query (they appear first) so that if a
    # daily-updated record is also captured by the historical query it is not
    # double-counted.
    seen: set[tuple[str | None, str | None]] = set()
    all_records: list[dict] = []
    for record in records_today + records_past:
        key = (record.get("ChargeTypeCode"), record.get("ValidFrom"))
        if key not in seen:
            seen.add(key)
            all_records.append(record)

    schedule = [0.0] * 24

    if not all_records:
        _LOGGER.debug("DatahubPricelist: no D03 records for GLN %s", gln)
        return schedule

    now = reference_dt
    included = 0

    # Track 24-hour price profiles already summed into the schedule.
    # DSOs publish the same nettarif C time as both a <100 kWh/h tier and a
    # >100 kWh/h tier with identical prices.  If we sum both we double-count
    # the tariff.  Deduplication by profile prevents this.
    seen_profiles: set[tuple[float, ...]] = set()

    for record in all_records:
        # ── Charge-type code allow-list ──────────────────────────────────────
        if allowed_codes is not None and record.get("ChargeTypeCode") not in allowed_codes:
            continue

        # ── Validity window ──────────────────────────────────────────────────
        valid_from_str: str = record.get("ValidFrom") or ""
        valid_to_str: str = record.get("ValidTo") or ""

        try:
            vf = datetime.fromisoformat(valid_from_str)
            if vf.tzinfo is None:
                vf = vf.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue

        if now < vf:
            continue  # record not yet active

        if valid_to_str:
            try:
                vt = datetime.fromisoformat(valid_to_str)
                if vt.tzinfo is None:
                    vt = vt.replace(tzinfo=timezone.utc)
                if now >= vt:
                    continue  # record has expired
            except (ValueError, TypeError):
                pass  # unparseable ValidTo — treat as open-ended

        # ── Hourly price extraction ──────────────────────────────────────────
        all_prices = [record.get(f"Price{i + 1}") for i in range(24)]
        prices_set = [p for p in all_prices if p is not None]

        if not prices_set:
            continue  # no price data

        if require_all_prices and len(prices_set) < 24:
            # DSO mode: skip records without a complete 24-hour profile.
            # This filters out capacity/power charges (Effektbetaling) which
            # only populate Price1 and leave Price2–Price24 as None.
            continue

        if require_varying_prices and len(prices_set) >= 2:
            # Skip records where every hour has the same price.
            # These are flat-rate secondary/band tariffs (e.g. "Nettarif A høj
            # samplaceret") that may not apply to all customers; only the
            # genuinely time-varying nettarif C time record is included.
            unique_vals = len(
                set(round(float(p), 6) for p in prices_set if p is not None)
            )
            if unique_vals == 1:
                continue

        # ── Duplicate-profile guard ──────────────────────────────────────────
        # DSOs often publish the same nettarif C time under multiple codes
        # (e.g. TCL<100_02 for residential and TCL>100_02 for large users)
        # with identical 24-hour price profiles.  Only the consumer's own tier
        # applies — summing both would double the tariff.  Skip any record
        # whose resolved 24-hour profile has already been added to the schedule.
        if len(prices_set) == 1:
            profile_key: tuple[float, ...] = (round(float(prices_set[0]), 6),)
        else:
            profile_key = tuple(
                round(float(all_prices[i]), 6) if all_prices[i] is not None else 0.0
                for i in range(24)
            )
        if profile_key in seen_profiles:
            continue
        seen_profiles.add(profile_key)

        if len(prices_set) == 1:
            # Flat-rate tariff (e.g. Energinet transmissions nettarif):
            # Price1 is the same rate for every hour — apply it to all slots.
            flat = float(prices_set[0])
            for i in range(24):
                schedule[i] = round(schedule[i] + flat, 6)
        else:
            # Time-of-use tariff: use each price for its respective hour.
            for i in range(24):
                raw = all_prices[i]
                if raw is not None:
                    schedule[i] = round(schedule[i] + float(raw), 6)

        included += 1

    daily_avg = sum(schedule) / 24
    _LOGGER.debug(
        "DatahubPricelist: GLN %s — today query: %d records, historical query: %d records, "
        "%d included after dedup+filter, daily avg %.4f DKK/kWh "
        "(hour 0: %.4f, hour 12: %.4f, hour 17: %.4f)",
        gln,
        len(records_today),
        len(records_past),
        included,
        daily_avg,
        schedule[0],
        schedule[12],
        schedule[17],
    )
    return [round(v, 4) for v in schedule]
