"""Fetch hourly DSO/Energinet tariff schedules from Energi Data Service DatahubPricelist."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

_DATAHUB_URL = "https://api.energidataservice.dk/dataset/DatahubPricelist"
_TIMEOUT = aiohttp.ClientTimeout(total=15)


async def fetch_tariff_schedule(
    session: aiohttp.ClientSession,
    gln: str,
    reference_dt: datetime,
) -> list[float]:
    """Return a 24-entry hourly tariff schedule (DKK/kWh) for *gln*.

    Queries DatahubPricelist for all currently-valid charge-type records for the
    given GLN number, sums all valid records, and returns one value per local hour
    of day (index 0 = midnight–01:00 local, index 23 = 23:00–midnight local).

    The DatahubPricelist field Price1 maps to local hour 0, Price24 to hour 23.

    Returns a list of 24 zeros if the API is unavailable or returns no relevant data.
    """
    date_str = reference_dt.strftime("%Y-%m-%d")
    url = (
        f'{_DATAHUB_URL}'
        f'?filter={{"GLN_Number":"{gln}"}}'
        f"&start={date_str}"
        f"&limit=100"
    )
    schedule = [0.0] * 24

    try:
        async with session.get(url, timeout=_TIMEOUT) as resp:
            resp.raise_for_status()
            data: dict[str, Any] = await resp.json(content_type=None)
    except Exception as err:
        _LOGGER.warning("DatahubPricelist fetch failed for GLN %s: %s", gln, err)
        return schedule

    records: list[dict] = data.get("records", [])
    if not records:
        _LOGGER.debug("DatahubPricelist: no records for GLN %s on %s", gln, date_str)
        return schedule

    now = reference_dt
    for record in records:
        # ── Validity window check ────────────────────────────────────────────
        valid_from_str: str = record.get("ValidFrom") or ""
        valid_to_str: str = record.get("ValidTo") or ""

        try:
            vf = datetime.fromisoformat(valid_from_str)
            if vf.tzinfo is None:
                vf = vf.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue  # unparseable ValidFrom → skip this record

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
                pass  # unparseable ValidTo → treat as open-ended

        # ── Sum Price1..Price24 into the hourly schedule ─────────────────────
        # Price1 = hour 0 (00:00–01:00 local), Price24 = hour 23 (23:00–00:00 local)
        for i in range(24):
            raw = record.get(f"Price{i + 1}")
            if raw is not None:
                try:
                    schedule[i] = round(schedule[i] + float(raw), 6)
                except (ValueError, TypeError):
                    pass

    total = sum(schedule)
    _LOGGER.debug(
        "DatahubPricelist: GLN %s — fetched %d records, total daily avg %.4f DKK/kWh",
        gln, len(records), total / 24 if total else 0,
    )
    return [round(v, 4) for v in schedule]
