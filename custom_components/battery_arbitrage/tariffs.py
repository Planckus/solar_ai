"""Fetch hourly DSO/Energinet tariff schedules from Energi Data Service DatahubPricelist."""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

_DATAHUB_URL = "https://api.energidataservice.dk/dataset/DatahubPricelist"
_TIMEOUT = aiohttp.ClientTimeout(total=15)

# v0.49.1 — Energi Data Service rate-limits bursts of requests (HTTP 429).
# The tariff refresh fires several D03 queries near-simultaneously, so retry
# 429s and transient 5xx/network errors with a short, jittered backoff before
# giving up. Jitter de-synchronises concurrent retries so they don't re-burst
# together.
_FETCH_RETRIES = 4
_RETRY_BACKOFF_SECONDS = [1.5, 2.5, 4.0]   # waits between attempts (last value reused)

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
    sort: str | None = None,
) -> list[dict]:
    """Fetch raw D03 records from DatahubPricelist for *gln* starting at *start*.

    *end* (optional) adds ``&end=<date>`` to the query.  Setting ``end=tomorrow``
    excludes future pre-published records from the result set, which is critical
    for DSOs (e.g. Dinel) that pre-publish hundreds of daily records months in
    advance — without this filter those records dominate the response and push
    today's record beyond the fetch limit.

    *sort* (optional) overrides the default sort order.  Use ``"ValidFrom desc"``
    to get the most-recent records first — important for feed-in tariff queries
    where the target record may be beyond the limit in ascending order due to
    the large number of daily DSO records.
    """
    url = (
        f"{_DATAHUB_URL}"
        f'?filter={{"GLN_Number":"{gln}","ChargeType":"D03"}}'
        f"&start={start}"
        f"&limit={limit}"
    )
    if end:
        url += f"&end={end}"
    if sort:
        url += f"&sort={sort}"
    last_err: Any = None
    for attempt in range(_FETCH_RETRIES):
        try:
            async with session.get(url, timeout=_TIMEOUT) as resp:
                if resp.status == 429 or resp.status >= 500:
                    last_err = f"HTTP {resp.status}"
                else:
                    resp.raise_for_status()
                    data: dict[str, Any] = await resp.json(content_type=None)
                    return data.get("records", [])
        except Exception as err:  # noqa: BLE001 — network/JSON/timeout all retryable
            last_err = err
        # Back off (with jitter) before the next attempt, except after the last.
        if attempt < _FETCH_RETRIES - 1:
            base = _RETRY_BACKOFF_SECONDS[min(attempt, len(_RETRY_BACKOFF_SECONDS) - 1)]
            await asyncio.sleep(base + random.uniform(0, 1.0))
    _LOGGER.warning(
        "DatahubPricelist fetch failed for GLN %s (start=%s) after %d attempts: %s",
        gln, start, _FETCH_RETRIES, last_err,
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
    note_substring: str | None = None,
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
        note_substring:
            When provided, only records whose ``Note`` field contains this
            substring (case-insensitive) are included.  v0.39.8 — use this
            for DSO queries to restrict to a single customer tier (e.g.
            ``"Nettarif C"`` for residential customers on the C-time band).
            Without this filter, DSOs that publish multiple parallel tier
            tariffs (Dinel publishes 7: A_high/low, B_spreed/high/low, C
            <100/>100) all pass the all-prices+varying-prices filters and
            get summed into a single schedule, overstating the per-kWh
            tariff several-fold.  ``Nettarif C`` is the standard Danish
            term for the residential time-of-use band and is used
            consistently across the 7 supported DSOs.

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

    note_substring_lc = note_substring.lower() if note_substring else None

    for record in all_records:
        # ── Charge-type code allow-list ──────────────────────────────────────
        if allowed_codes is not None and record.get("ChargeTypeCode") not in allowed_codes:
            continue

        # ── Note substring filter (v0.39.8) ──────────────────────────────────
        # Restrict to records matching a customer-tier description. See
        # docstring for rationale.
        if note_substring_lc is not None:
            note_text = (record.get("Note") or "").lower()
            if note_substring_lc not in note_text:
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


async def fetch_feed_in_tariff(
    session: aiohttp.ClientSession,
    dso_gln: str,
    energinet_gln: str,
    reference_dt: datetime,
) -> tuple[float | None, float | None]:
    """Return ``(dso_feed_in, energinet_feed_in)`` flat rates in DKK/kWh.

    Fetches two flat-rate tariffs that are deducted from the gross export price:

    * **DSO indfødningstariffen** — the local grid operator's per-kWh fee for
      accepting injected power.  Selected by looking for a D03 record whose
      ``Note`` contains ``"indfødning c"`` (case-insensitive), i.e. the C-tariff
      residential feed-in rate.  For DINEL this is code ``TC_IND_03``.

    * **Energinet indfødningstarif produktion** — the TSO's production injection
      fee.  Selected by charge type code ``"40010"``.

    Both tariffs are flat-rate (only ``Price1`` populated) and change at most a
    few times per year, so the same two-query strategy as :func:`fetch_tariff_schedule`
    is used for reliability.

    Each element is ``None`` when its lookup failed or no valid record was
    found (e.g. an EDS 429) — the coordinator then keeps the previous cached
    value rather than zeroing the export price. A real DK feed-in tariff is
    always > 0, so a genuine zero is not expected.
    """
    today_str = reference_dt.strftime("%Y-%m-%d")
    tomorrow_str = (reference_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    # Use descending sort so the most-recent records appear first.
    # DINEL publishes hundreds of daily records; ascending order would push the
    # indfødningstariffen (ValidFrom 2026-05-01) beyond the 500-record limit.
    dso_records, en_records = await asyncio.gather(
        _fetch_raw_records(session, dso_gln, _TARIFF_LOOKBACK_START, _LOOKBACK_LIMIT,
                           end=tomorrow_str, sort="ValidFrom desc"),
        _fetch_raw_records(session, energinet_gln, _TARIFF_LOOKBACK_START, _LOOKBACK_LIMIT,
                           end=tomorrow_str, sort="ValidFrom desc"),
    )

    now = reference_dt

    def _first_valid_flat(records_a: list[dict], records_b: list[dict], filter_fn) -> float | None:
        seen: set[tuple] = set()
        for r in records_a + records_b:
            key = (r.get("ChargeTypeCode"), r.get("ValidFrom"))
            if key in seen:
                continue
            seen.add(key)

            if not filter_fn(r):
                continue

            vf_str = r.get("ValidFrom") or ""
            vt_str = r.get("ValidTo") or ""
            try:
                vf = datetime.fromisoformat(vf_str)
                if vf.tzinfo is None:
                    vf = vf.replace(tzinfo=timezone.utc)
                if now < vf:
                    continue
            except (ValueError, TypeError):
                continue

            if vt_str:
                try:
                    vt = datetime.fromisoformat(vt_str)
                    if vt.tzinfo is None:
                        vt = vt.replace(tzinfo=timezone.utc)
                    if now >= vt:
                        continue
                except (ValueError, TypeError):
                    pass

            price1 = r.get("Price1")
            if price1 is not None:
                return round(float(price1), 6)
        # v0.49.1 — None (not 0.0) signals "no valid record found / fetch
        # failed", so the coordinator keeps the last good cached value instead
        # of zeroing the export price.
        return None

    def _is_dso_feed_in(r: dict) -> bool:
        note = (r.get("Note") or "").lower()
        return "indfødning c" in note

    def _is_energinet_feed_in(r: dict) -> bool:
        return r.get("ChargeTypeCode") == "40010"

    dso_rate = _first_valid_flat(dso_records, [], _is_dso_feed_in)
    energinet_rate = _first_valid_flat(en_records, [], _is_energinet_feed_in)

    _LOGGER.debug(
        "Feed-in tariff: DSO (GLN %s) %s + Energinet %s DKK/kWh (None = lookup failed, cache kept)",
        dso_gln, dso_rate, energinet_rate,
    )
    return dso_rate, energinet_rate
