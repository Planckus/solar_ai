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
    """Set up Battery Arbitrage switches."""
    coordinator: BatteryArbitrageCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        BatteryArbitrageSwitch(coordinator, entry),
        BatteryArbitrageNotificationsSwitch(coordinator, entry),
        BatteryArbitragePriceResolutionSwitch(coordinator, entry),
    ])


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
        # Re-disable the legacy automation when arbitrage is re-enabled
        await self.coordinator.async_disable_legacy_automation()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        self.coordinator.enabled = False
        # Restore the legacy automation and inverter/EVCC to normal
        await self.coordinator.async_restore_legacy_automation()
        await self.coordinator.async_restore_normal()
        self.async_write_ha_state()


class BatteryArbitrageNotificationsSwitch(
    CoordinatorEntity[BatteryArbitrageCoordinator], SwitchEntity
):
    """Toggle for HA persistent notifications on mode changes.

    When on, Solar AI fires a persistent notification whenever it transitions
    between Self-use / Exporting / Grid charging.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "notifications_enabled"
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:bell-outline"

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_notifications_enabled"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator._stored.get("notifications_enabled", False))

    async def async_turn_on(self, **kwargs: object) -> None:
        self.coordinator._stored["notifications_enabled"] = True
        await self.coordinator._store.async_save(self.coordinator._stored)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        self.coordinator._stored["notifications_enabled"] = False
        await self.coordinator._store.async_save(self.coordinator._stored)
        self.async_write_ha_state()


class BatteryArbitragePriceResolutionSwitch(
    CoordinatorEntity[BatteryArbitrageCoordinator], SwitchEntity
):
    """Toggle between 15-minute and 1-hour price chart resolution.

    When on, the 24h price chart sensor emits one row per native DSO slot
    (typically 15 minutes).  When off (default) it emits one row per hour.
    The arbitrage model always uses native resolution internally regardless
    of this setting.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "price_resolution_15min"
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:clock-time-four-outline"

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_price_resolution_15min"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator._stored.get("price_resolution_15min", False))

    async def async_turn_on(self, **kwargs: object) -> None:
        self.coordinator._stored["price_resolution_15min"] = True
        await self.coordinator._store.async_save(self.coordinator._stored)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        self.coordinator._stored["price_resolution_15min"] = False
        await self.coordinator._store.async_save(self.coordinator._stored)
        self.async_write_ha_state()
