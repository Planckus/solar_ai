"""Number platform for Battery Arbitrage — exposes learned charge rates as editable numbers."""
from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from homeassistant.const import PERCENTAGE

from .const import DEFAULT_BATTERY_FLOOR_SOC, DEFAULT_BATTERY_MAX_SOC, DOMAIN, TEMP_BUCKETS
from .coordinator import BatteryArbitrageCoordinator
from .sensor import _device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up learned charge rate and SOC threshold number entities."""
    coordinator: BatteryArbitrageCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[NumberEntity] = [
        BatteryArbitrageLearnedRateNumber(coordinator, entry, key, default)
        for key, _, _, default in TEMP_BUCKETS
    ]
    entities += [
        BatteryArbitrageSOCNumber(
            coordinator, entry,
            storage_key="battery_floor_soc",
            translation_key="floor_soc",
            default=DEFAULT_BATTERY_FLOOR_SOC,
            icon="mdi:battery-arrow-down-outline",
        ),
        BatteryArbitrageSOCNumber(
            coordinator, entry,
            storage_key="battery_max_soc",
            translation_key="max_soc",
            default=DEFAULT_BATTERY_MAX_SOC,
            icon="mdi:battery-arrow-up-outline",
        ),
    ]
    async_add_entities(entities)


class BatteryArbitrageLearnedRateNumber(
    CoordinatorEntity[BatteryArbitrageCoordinator], NumberEntity
):
    """Editable number entity for a learned charge rate bucket.

    The learned rate is updated automatically by calibration, but the user can
    manually override it here (e.g. after a battery upgrade).
    """

    _attr_has_entity_name = True
    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0.1
    _attr_native_max_value = 10.0
    _attr_native_step = 0.1
    _attr_icon = "mdi:battery-charging-outline"

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
        bucket_key: str,
        default_kw: float,
    ) -> None:
        super().__init__(coordinator)
        self._bucket_key = bucket_key
        self._default_kw = default_kw
        self._attr_unique_id = f"{entry.entry_id}_charge_rate_{bucket_key}"
        self._attr_translation_key = f"charge_rate_{bucket_key}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> float:
        return self.coordinator.get_learned_rate(self._bucket_key)

    async def async_set_native_value(self, value: float) -> None:
        """Allow the user to manually override the learned rate."""
        rates = self.coordinator._stored.setdefault("charge_rates", {})
        rates[self._bucket_key] = round(value, 3)
        # Also clear the samples so manual override takes precedence
        samples = self.coordinator._stored.setdefault("charge_samples", {})
        samples[self._bucket_key] = []
        await self.coordinator._store.async_save(self.coordinator._stored)
        self.async_write_ha_state()


class BatteryArbitrageSOCNumber(
    CoordinatorEntity[BatteryArbitrageCoordinator], NumberEntity
):
    """Slider for battery floor or max SoC threshold.

    Adjusting this takes effect on the next 5-minute coordinator tick
    without requiring a restart.
    """

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 10
    _attr_native_max_value = 100
    _attr_native_step = 1

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
        storage_key: str,
        translation_key: str,
        default: int,
        icon: str,
    ) -> None:
        super().__init__(coordinator)
        self._storage_key = storage_key
        self._default = default
        self._attr_unique_id = f"{entry.entry_id}_{storage_key}"
        self._attr_translation_key = translation_key
        self._attr_icon = icon
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> int:
        return int(self.coordinator._stored.get(self._storage_key, self._default))

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator._stored[self._storage_key] = int(value)
        await self.coordinator._store.async_save(self.coordinator._stored)
        self.async_write_ha_state()
