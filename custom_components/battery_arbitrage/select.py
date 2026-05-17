"""Select platform — EV charge controller mode picker (Phase B1)."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    EV_MODE_LOCKED,
    EV_MODE_PV,
    EV_MODE_PV_BATTERY,
    EV_MODE_FULL,
)
from .coordinator import BatteryArbitrageCoordinator
from .sensor import _device_info


EV_MODES = [EV_MODE_LOCKED, EV_MODE_PV, EV_MODE_PV_BATTERY, EV_MODE_FULL]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the EV mode select entity."""
    coordinator: BatteryArbitrageCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BatteryArbitrageEvModeSelect(coordinator, entry)])


class BatteryArbitrageEvModeSelect(
    CoordinatorEntity[BatteryArbitrageCoordinator], SelectEntity
):
    """Live EV mode picker — drives Solar AI's 4-mode EV charge controller.

    The four options are:
      - locked        → no charging
      - pv            → solar surplus only; stops if surplus < min
      - pv_battery    → solar first; battery covers gap to reach min; no grid
      - full          → max charge rate regardless of source mix
    """

    _attr_has_entity_name = True
    _attr_translation_key = "ev_mode"
    _attr_icon = "mdi:car-electric"
    _attr_options = EV_MODES

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_ev_mode"
        self._attr_device_info = _device_info(entry)

    @property
    def current_option(self) -> str | None:
        return self.coordinator._ev_active_mode

    async def async_select_option(self, option: str) -> None:
        if option not in EV_MODES:
            return
        self.coordinator.set_ev_mode(option)
        self.async_write_ha_state()
