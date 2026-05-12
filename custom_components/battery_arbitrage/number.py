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

from .const import DOMAIN, TEMP_BUCKETS
from .coordinator import BatteryArbitrageCoordinator
from .sensor import _device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up learned charge rate number entities."""
    coordinator: BatteryArbitrageCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        BatteryArbitrageLearnedRateNumber(coordinator, entry, key, default)
        for key, _, _, default in TEMP_BUCKETS
    )


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
