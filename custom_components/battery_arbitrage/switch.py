"""Switch platform for Battery Arbitrage — master enable/disable toggle."""
from __future__ import annotations

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
    """Set up Battery Arbitrage switch."""
    coordinator: BatteryArbitrageCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BatteryArbitrageSwitch(coordinator, entry)])


class BatteryArbitrageSwitch(
    CoordinatorEntity[BatteryArbitrageCoordinator], SwitchEntity
):
    """Master on/off switch for the arbitrage system.

    When turned off the coordinator still polls (so sensors stay fresh) but
    will NOT change work modes or EVCC battery mode.  Turning it off while
    exporting or grid-charging immediately restores normal operation.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "enabled"
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:flash-auto"

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_enabled"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool:
        return self.coordinator.enabled

    async def async_turn_on(self, **kwargs: object) -> None:
        self.coordinator.enabled = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        self.coordinator.enabled = False
        # Immediately restore inverter/EVCC to normal if we were mid-cycle
        await self.coordinator.async_restore_normal()
        self.async_write_ha_state()
