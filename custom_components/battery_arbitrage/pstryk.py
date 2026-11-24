"""Pstryk retailer pricing (Poland, v1.32.0).

Pstryk's API returns hourly all-in prices: `price_gross` is what the customer
pays to buy a kWh, `price_prosumer_gross` is what the customer is paid for an
exported kWh. Prices for tomorrow appear once the day-ahead auction is
published; before that the API can return incomplete or placeholder values
for tomorrow, which `drop_unpublished_days` removes.

This module is transport and parsing only. The coordinator caches the
result, uses the sell prices as the optimiser's price curve and looks up the
buy price per slot.
"""
from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any

import aiohttp

from .const import (
    PSTRYK_API_BASE,
    PSTRYK_MIN_SLOTS_PER_DAY,
    PSTRYK_PLACEHOLDER_SHARE,
    PSTRYK_PRICING_PATH,
    PSTRYK_RATE_LIMIT_DEFAULT_SECONDS,
    PSTRYK_TIMEOUT_SEC,
)

_LOGGER = logging.getLogger(__name__)


class PstrykAuthError(Exception):
    """The API rejected the key (HTTP 401 or 403)."""


class PstrykRateLimited(Exception):
    """The API answered HTTP 429. `retry_after` is in seconds."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(f"rate limited, retry after {retry_after} s")
        self.retry_after = retry_after


def slot_key(start: datetime) -> str:
    """Cache key for a slot: its start in UTC, whole seconds, ISO format."""
    return start.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def _price(frame: dict, key: str) -> float | None:
    """A price may sit on the frame itself or under metrics.pricing."""
    value = frame.get(key)
    if value is None:
        value = (frame.get("metrics") or {}).get("pricing", {}).get(key)
    return _to_float(value)


def parse_frames(frames: list[dict]) -> list[dict[str, Any]]:
    """Turn API frames into slots: {"start": UTC ISO, "buy": float, "sell": float}.

    Frames without a parsable start, buy price or sell price are skipped, so
    every returned slot has both prices. Sorted by start.
    """
    slots: list[dict[str, Any]] = []
    for frame in frames or []:
        try:
            start = datetime.fromisoformat(str(frame["start"]).replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError):
            continue
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        buy = _price(frame, "price_gross")
        sell = _price(frame, "price_prosumer_gross")
        if buy is None or sell is None:
            continue
        slots.append({"start": slot_key(start), "buy": buy, "sell": sell})
    slots.sort(key=lambda s: s["start"])
    return slots


def _looks_unpublished(values: list[float]) -> bool:
    if len(values) < PSTRYK_MIN_SLOTS_PER_DAY:
        return True
    _, most_common = Counter(values).most_common(1)[0]
    return most_common / len(values) > PSTRYK_PLACEHOLDER_SHARE


def drop_unpublished_days(
    slots: list[dict[str, Any]], today: datetime, tz: tzinfo,
) -> list[dict[str, Any]]:
    """Remove days after today whose prices are incomplete or placeholders.

    Today's slots are always kept: an incomplete today is still the best
    data available, and the optimiser only plans over slots that exist.
    """
    today_date = today.astimezone(tz).date()
    by_day: dict[Any, list[dict[str, Any]]] = {}
    for slot in slots:
        day = datetime.fromisoformat(slot["start"]).astimezone(tz).date()
        by_day.setdefault(day, []).append(slot)
    kept: list[dict[str, Any]] = []
    for day in sorted(by_day):
        day_slots = by_day[day]
        if day > today_date and (
            _looks_unpublished([s["buy"] for s in day_slots])
            or _looks_unpublished([s["sell"] for s in day_slots])
        ):
            _LOGGER.debug("Pstryk: prices for %s not published yet, skipped", day)
            continue
        kept.extend(day_slots)
    return kept


def pricing_url(now: datetime, tz: tzinfo) -> str:
    """URL for today's local midnight to two days later."""
    midnight = now.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    start = midnight.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = (midnight + timedelta(days=2)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return PSTRYK_API_BASE + PSTRYK_PRICING_PATH.format(start=start, end=end)


async def fetch_prices(
    session: aiohttp.ClientSession, api_key: str, now: datetime, tz: tzinfo,
) -> list[dict[str, Any]] | None:
    """Fetch today's and (when published) tomorrow's hourly prices.

    Returns the slots, or None on a transient failure (network error, timeout,
    unexpected status or body). Raises PstrykAuthError on 401/403 and
    PstrykRateLimited on 429, so the caller can stop or wait.
    """
    url = pricing_url(now, tz)
    headers = {"Authorization": api_key, "Accept": "application/json"}
    try:
        async with session.get(
            url, headers=headers,
            timeout=aiohttp.ClientTimeout(total=PSTRYK_TIMEOUT_SEC),
        ) as response:
            if response.status in (401, 403):
                raise PstrykAuthError(f"HTTP {response.status}")
            if response.status == 429:
                try:
                    retry_after = int(response.headers.get("Retry-After", ""))
                except ValueError:
                    retry_after = PSTRYK_RATE_LIMIT_DEFAULT_SECONDS
                raise PstrykRateLimited(max(60, retry_after))
            if response.status != 200:
                _LOGGER.warning("Pstryk price fetch: HTTP %d", response.status)
                return None
            data = await response.json()
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
        _LOGGER.warning("Pstryk price fetch failed: %s", err)
        return None
    if not isinstance(data, dict):
        _LOGGER.warning("Pstryk price fetch: unexpected response body")
        return None
    slots = drop_unpublished_days(parse_frames(data.get("frames", [])), now, tz)
    if not slots:
        _LOGGER.warning("Pstryk price fetch: no usable prices in the response")
        return None
    return slots
