"""Time platform for Battery Arbitrage — start/end times for each EV schedule slot (v0.38.0).

Four pairs of time entities (one start + one end per slot, 1..EV_SCHEDULES_MAX).
The entities read and write directly to `coordinator._stored["ev_schedules"]`,
which is the canonical source for native EV scheduling. The dashboard's
schedule cards bind to these entities for inline time editing using HA's
native time picker.

Empty slots fall back to the global default start/end so the picker
shows something sensible before the user has touched it.
"""
from __future__ import annotations

from datetime import time as _time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    EV_SCHEDULES_MAX,
    EV_SCHEDULE_DEFAULT_START,
    EV_SCHEDULE_DEFAULT_END,
)
from .coordinator import BatteryArbitrageCoordinator
from .sensor import _device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one start + one end time entity per maximum slot index."""
    coordinator: BatteryArbitrageCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[TimeEntity] = []
    for idx in range(1, EV_SCHEDULES_MAX + 1):
        entities.append(BatteryArbitrageScheduleTime(coordinator, entry, idx, which="start"))
        entities.append(BatteryArbitrageScheduleTime(coordinator, entry, idx, which="end"))
    async_add_entities(entities)


def _parse_hhmm(s: str | None) -> _time:
    """Parse 'HH:MM' (or 'HH:MM:SS') into a time. Returns 00:00 on failure."""
    try:
        parts = (s or "").split(":")
        h = int(parts[0]); m = int(parts[1]) if len(parts) > 1 else 0
        return _time(max(0, min(23, h)), max(0, min(59, m)))
    except (ValueError, IndexError):
        return _time(0, 0)


class BatteryArbitrageScheduleTime(
    CoordinatorEntity[BatteryArbitrageCoordinator], TimeEntity
):
    """Per-slot start/end time picker, backed by `_stored["ev_schedules"]`.

    Setting a value via the HA time picker (or service call) calls the
    coordinator's `set_schedule_slot_time(slot, which, "HH:MM")`, which
    persists and notifies listeners. For unconfigured slots this also
    creates the slot with defaults so the new time isn't lost.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
        slot_idx: int,
        which: str,            # "start" or "end"
    ) -> None:
        super().__init__(coordinator)
        self._slot_idx = slot_idx
        self._which = which
        # Translation key — provides Danish + English labels per slot/end.
        self._attr_translation_key = f"ev_schedule_slot_{slot_idx}_{which}"
        self._attr_unique_id = f"{entry.entry_id}_ev_schedule_slot_{slot_idx}_{which}"
        self._attr_icon = "mdi:clock-start" if which == "start" else "mdi:clock-end"
        self._attr_device_info = _device_info(entry)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Re-render whenever any service mutator nudges the dispatcher.
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, f"{DOMAIN}_schedules_changed",
                self.async_write_ha_state,
            )
        )

    @property
    def native_value(self) -> _time | None:
        slot = self.coordinator.get_schedule_slot(self._slot_idx)
        if slot is None:
            return _parse_hhmm(
                EV_SCHEDULE_DEFAULT_START if self._which == "start"
                else EV_SCHEDULE_DEFAULT_END,
            )
        return _parse_hhmm(slot.get(self._which))

    async def async_set_value(self, value: _time) -> None:
        # HA passes a datetime.time; serialise to HH:MM for storage.
        hhmm = f"{value.hour:02d}:{value.minute:02d}"
        self.coordinator.set_schedule_slot_time(self._slot_idx, self._which, hhmm)
        self.async_write_ha_state()
