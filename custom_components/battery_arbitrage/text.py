"""Text platform — free-text structural settings exposed as live entities.

Currently just the FoxESS Modbus charger host (v0.57.0), so the charger IP can
be set from the dashboard Advanced pane rather than only the Configure dialog.
Backed by `coordinator._stored[key]`; the coordinator reads it per cycle via
`_setting()` and rebuilds the Modbus connection when it changes — no reload.
"""
from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_FOXESS_CHARGER_HOST
from .coordinator import BatteryArbitrageCoordinator
from .sensor import _device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up text entities."""
    coordinator: BatteryArbitrageCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        BatteryArbitrageChargerHostText(coordinator, entry),
        BatteryArbitrageBlockedSellHoursText(coordinator, entry),
    ])


class BatteryArbitrageBlockedSellHoursText(
    CoordinatorEntity[BatteryArbitrageCoordinator], TextEntity
):
    """Comma-separated hours-of-day in which the battery must NOT be sold
    (v0.66.0), e.g. "20,21". Empty = no restriction."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "blocked_sell_hours"
    _attr_icon = "mdi:cancel"
    _attr_mode = TextMode.TEXT
    _attr_native_max = 64
    _attr_pattern = r"[0-9, ;]*"

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_blocked_sell_hours"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> str:
        return self.coordinator._stored.get("blocked_sell_hours", "")

    async def async_set_value(self, value: str) -> None:
        # Normalise to a clean, sorted, de-duplicated hour list.
        self.coordinator._stored["blocked_sell_hours"] = value.strip()
        hours = sorted(self.coordinator._blocked_sell_hours())
        self.coordinator._stored["blocked_sell_hours"] = ",".join(str(h) for h in hours)
        if self.coordinator.hass:
            await self.coordinator._store.async_save(self.coordinator._stored)
            await self.coordinator.async_request_refresh()
        self.async_write_ha_state()


class BatteryArbitrageChargerHostText(
    CoordinatorEntity[BatteryArbitrageCoordinator], TextEntity
):
    """FoxESS Modbus charger host (IP or hostname), settable from the dashboard."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "foxess_charger_host"
    _attr_icon = "mdi:ip-network"
    _attr_mode = TextMode.TEXT
    _attr_native_max = 64
    # Allow IPv4/hostnames; empty string clears it (disables the Modbus backend).
    _attr_pattern = r"[A-Za-z0-9_.\-]*"

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{CONF_FOXESS_CHARGER_HOST}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> str:
        return self.coordinator._stored.get(
            CONF_FOXESS_CHARGER_HOST,
            self._entry.data.get(CONF_FOXESS_CHARGER_HOST, ""),
        )

    async def async_set_value(self, value: str) -> None:
        self.coordinator._stored[CONF_FOXESS_CHARGER_HOST] = value.strip()
        if self.coordinator.hass:
            await self.coordinator._store.async_save(self.coordinator._stored)
            await self.coordinator.async_request_refresh()
        self.async_write_ha_state()
