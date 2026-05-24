"""v0.37.0 — Programmatic schedule.* helper management.

Backs the new `battery_arbitrage.add_schedule_slot` /
`remove_schedule_slot` services that the dashboard's "Opret skema"
buttons call. The implementation writes directly to HA's storage
file `/config/.storage/schedule` and then triggers a reload via the
public `schedule.reload` service.

Why direct storage writes rather than the internal `StorageCollection`
API: on installs where the user has never created a schedule helper,
the `schedule` integration is dormant — its storage collection isn't
on `hass.data`. The WS commands work because their handlers initialise
the storage lazily on first call, but no equivalent path exists for an
integration calling from inside HA. Editing the storage file + calling
`schedule.reload` is the same behaviour HA's auto-import scripts use
and survives the schedule integration being unloaded.

Storage format (HA 2024.x):
    {
      "version": 1, "minor_version": 1, "key": "schedule",
      "data": {"items": [{"id": <slug>, "name": "...", "icon": "...",
                          "monday": [], ..., "sunday": []}]}
    }
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

_SCHEDULE_DOMAIN = "schedule"
_STORAGE_KEY = "schedule"
_STORAGE_VERSION = 1
_STORAGE_VERSION_MINOR = 1


def _slugify_solar_ai_skema(slot_num: int) -> str:
    """Stable schedule id for slot N — `solar_ai_skema_<N>`."""
    return f"solar_ai_skema_{slot_num}"


def _empty_week() -> dict[str, list]:
    """Return a 7-day blank schedule (helper is 'off' until user edits)."""
    return {
        "monday": [], "tuesday": [], "wednesday": [], "thursday": [],
        "friday": [], "saturday": [], "sunday": [],
    }


def _empty_storage() -> dict:
    return {
        "version": _STORAGE_VERSION,
        "minor_version": _STORAGE_VERSION_MINOR,
        "key": _STORAGE_KEY,
        "data": {"items": []},
    }


async def _load_storage(hass: HomeAssistant) -> dict:
    """Read the schedule storage file via HA's `Store` (handles locking)."""
    store = Store(hass, _STORAGE_VERSION, _STORAGE_KEY,
                  minor_version=_STORAGE_VERSION_MINOR)
    raw = await store.async_load()
    if not raw:
        return {"items": []}
    if isinstance(raw, dict) and "items" in raw:
        return raw
    return {"items": []}


async def _save_storage(hass: HomeAssistant, data: dict) -> None:
    """Write the schedule storage file via HA's `Store`."""
    store = Store(hass, _STORAGE_VERSION, _STORAGE_KEY,
                  minor_version=_STORAGE_VERSION_MINOR)
    await store.async_save(data)


async def _reload_schedule_integration(hass: HomeAssistant) -> None:
    """Reload the schedule integration so the new helper appears as an entity."""
    if hass.services.has_service(_SCHEDULE_DOMAIN, "reload"):
        await hass.services.async_call(
            _SCHEDULE_DOMAIN, "reload", {}, blocking=True,
        )
    else:
        # Fallback: trigger setup so storage is registered. The schedule
        # component's async_setup is idempotent.
        from homeassistant.setup import async_setup_component  # noqa: PLC0415
        await async_setup_component(hass, _SCHEDULE_DOMAIN, {})


async def create_solar_ai_schedule(hass: HomeAssistant, slot_num: int) -> str:
    """Create `schedule.solar_ai_skema_<N>` and return its entity_id.

    The new helper starts with all weekday lists empty — state = off, no
    effect on the EV controller — until the user opens it in the
    more-info popup and draws time ranges in the native HA grid editor.
    """
    # DEBUG: Inspect where the schedule integration actually stores its
    # collection. Different HA versions / install types put it under
    # different hass.data keys; the diagnostic helps identify which we're
    # on if the file-based fallback doesn't pick the helper up.
    sched_keys = [str(k) for k in hass.data.keys() if "sched" in str(k).lower()]
    _LOGGER.info(
        "create_solar_ai_schedule: hass.data keys containing 'sched': %s; "
        "type of hass.data.get('schedule'): %s",
        sched_keys, type(hass.data.get("schedule")).__name__,
    )

    # If the schedule integration's storage collection IS accessible, use
    # it directly (path the WS handlers use) — that's the only way to get
    # the new helper to appear as an entity without an HA restart.
    coll = None
    raw = hass.data.get(_SCHEDULE_DOMAIN)
    if raw is not None and hasattr(raw, "async_create_item"):
        coll = raw
    elif isinstance(raw, dict):
        sub = raw.get("storage_collection")
        if sub is not None and hasattr(sub, "async_create_item"):
            coll = sub

    schedule_id = _slugify_solar_ai_skema(slot_num)
    if coll is not None:
        _LOGGER.info("Using StorageCollection.async_create_item (live path)")
        cfg = {"name": f"Solar AI Skema {slot_num}",
               "icon": "mdi:calendar-clock", **_empty_week()}
        # Some HA versions require the id to be passed; others auto-generate.
        try:
            item = await coll.async_create_item({**cfg, "id": schedule_id})
        except Exception:  # noqa: BLE001
            # Older signature — let HA pick the id from the name slug
            item = await coll.async_create_item(cfg)
        sid = item.get("id") if isinstance(item, dict) else getattr(item, "id", schedule_id)
        return f"{_SCHEDULE_DOMAIN}.{sid}"

    # Fallback path — write to storage file + reload integration. Works on
    # installs where the storage collection isn't yet on hass.data, but
    # only takes effect after the next HA restart for the entity to appear.
    _LOGGER.warning(
        "schedule storage collection not on hass.data — writing to "
        ".storage/schedule directly. The helper appears as an entity after "
        "the next HA restart (or after the user creates any helper via the UI)."
    )
    data = await _load_storage(hass)
    items = data.setdefault("items", [])
    # Idempotent: do nothing if the id is already present (covers retries
    # after a partially-failed previous attempt).
    if any(isinstance(it, dict) and it.get("id") == schedule_id for it in items):
        _LOGGER.info("Schedule helper %s already exists — leaving as-is", schedule_id)
        await _reload_schedule_integration(hass)
        return f"{_SCHEDULE_DOMAIN}.{schedule_id}"

    new_item = {
        "id": schedule_id,
        "name": f"Solar AI Skema {slot_num}",
        "icon": "mdi:calendar-clock",
        **_empty_week(),
    }
    items.append(new_item)
    await _save_storage(hass, data)
    await _reload_schedule_integration(hass)
    entity_id = f"{_SCHEDULE_DOMAIN}.{schedule_id}"
    _LOGGER.info("Created schedule helper %s (slot %d)", entity_id, slot_num)
    return entity_id


async def delete_schedule_by_entity_id(hass: HomeAssistant, entity_id: str) -> None:
    """Delete the schedule helper that backs `entity_id`."""
    if not entity_id.startswith(f"{_SCHEDULE_DOMAIN}."):
        raise ValueError(f"Not a schedule entity: {entity_id}")
    schedule_id = entity_id.split(".", 1)[1]
    data = await _load_storage(hass)
    items = data.get("items", [])
    before = len(items)
    data["items"] = [it for it in items
                     if not (isinstance(it, dict) and it.get("id") == schedule_id)]
    if len(data["items"]) == before:
        _LOGGER.info("delete_schedule_by_entity_id: %s not in storage — nothing to delete", entity_id)
        return
    await _save_storage(hass, data)
    await _reload_schedule_integration(hass)
    # Remove any lingering registry entry (the reload usually does this on
    # its own, but be explicit so we don't leave orphan rows).
    registry = er.async_get(hass)
    if registry.async_get(entity_id) is not None:
        registry.async_remove(entity_id)
    _LOGGER.info("Deleted schedule helper %s", entity_id)
