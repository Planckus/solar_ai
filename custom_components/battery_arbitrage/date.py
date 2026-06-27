"""Date platform — the savings date-range pickers (v0.67.0).

Two dashboard date entities (start / end) that bound the *Actual savings in
range* sensor. Backed by `coordinator._stored`; default to the last 30 days.
"""
from __future__ import annotations

from datetime import date, timedelta

from homeassistant.components.date import DateEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BatteryArbitrageCoordinator
from .sensor import _device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the savings date-range pickers."""
    coordinator: BatteryArbitrageCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        BatteryArbitrageSavingsDate(coordinator, entry, "savings_range_start", 30),
        BatteryArbitrageSavingsDate(coordinator, entry, "savings_range_end", 0),
    ])


class BatteryArbitrageSavingsDate(
    CoordinatorEntity[BatteryArbitrageCoordinator], DateEntity
):
    """A savings-range date picker, backed by coordinator storage."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:calendar"

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
        storage_key: str,
        default_days_ago: int,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._storage_key = storage_key
        self._default_days_ago = default_days_ago
        self._attr_translation_key = storage_key
        self._attr_unique_id = f"{entry.entry_id}_{storage_key}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> date | None:
        raw = self.coordinator._stored.get(self._storage_key)
        if raw:
            try:
                return date.fromisoformat(raw)
            except ValueError:
                pass
        return date.today() - timedelta(days=self._default_days_ago)

    async def async_set_value(self, value: date) -> None:
        self.coordinator._stored[self._storage_key] = value.isoformat()
        if self.coordinator.hass:
            await self.coordinator._store.async_save(self.coordinator._stored)
            await self.coordinator.async_request_refresh()
        self.async_write_ha_state()
