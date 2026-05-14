"""Number platform for Battery Arbitrage — exposes learned charge rates as editable numbers."""
from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEFAULT_BATTERY_FLOOR_SOC,
    DEFAULT_BATTERY_MAX_SOC,
    DEFAULT_ELAFGIFT_DKK_KWH,
    DEFAULT_EXPORT_FEE,
    DEFAULT_MIN_SPREAD_ARBITRAGE,
    DEFAULT_VAT_PCT,
    DOMAIN,
    GRID_MAX_KW,
    TEMP_BUCKETS,
)
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
        BatteryArbitrageConfigNumber(
            coordinator, entry,
            storage_key="battery_floor_soc",
            translation_key="floor_soc",
            default=DEFAULT_BATTERY_FLOOR_SOC,
            icon="mdi:battery-arrow-down-outline",
            unit=PERCENTAGE,
            min_val=10,
            max_val=100,
            step=1,
        ),
        BatteryArbitrageConfigNumber(
            coordinator, entry,
            storage_key="battery_max_soc",
            translation_key="max_soc",
            default=DEFAULT_BATTERY_MAX_SOC,
            icon="mdi:battery-arrow-up-outline",
            unit=PERCENTAGE,
            min_val=10,
            max_val=100,
            step=1,
        ),
        BatteryArbitrageConfigNumber(
            coordinator, entry,
            storage_key="min_spread_arbitrage",
            translation_key="min_spread_arbitrage",
            default=DEFAULT_MIN_SPREAD_ARBITRAGE,
            icon="mdi:chart-bar",
            unit="DKK/kWh",
            min_val=0.10,
            max_val=3.00,
            step=0.05,
        ),
        BatteryArbitrageConfigNumber(
            coordinator, entry,
            storage_key="grid_max_kw",
            translation_key="grid_max_kw",
            default=GRID_MAX_KW,
            icon="mdi:transmission-tower",
            unit=UnitOfPower.KILO_WATT,
            min_val=5.0,
            max_val=63.0,
            step=0.5,
            mode=NumberMode.BOX,
        ),
        BatteryArbitrageConfigNumber(
            coordinator, entry,
            storage_key="vat_pct",
            translation_key="vat_pct",
            default=DEFAULT_VAT_PCT,
            icon="mdi:percent",
            unit=PERCENTAGE,
            min_val=0.0,
            max_val=50.0,
            step=0.5,
            mode=NumberMode.BOX,
        ),
        BatteryArbitrageConfigNumber(
            coordinator, entry,
            storage_key="export_fee",
            translation_key="export_fee",
            default=DEFAULT_EXPORT_FEE,
            icon="mdi:cash-minus",
            unit="DKK/kWh",
            min_val=0.0,
            max_val=0.50,
            step=0.005,
        ),
        BatteryArbitrageConfigNumber(
            coordinator, entry,
            storage_key="elafgift",
            translation_key="elafgift",
            default=DEFAULT_ELAFGIFT_DKK_KWH,
            icon="mdi:bank-outline",
            unit="DKK/kWh",
            min_val=0.0,
            max_val=3.0,
            step=0.001,
            mode=NumberMode.BOX,
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


class BatteryArbitrageConfigNumber(
    CoordinatorEntity[BatteryArbitrageCoordinator], NumberEntity
):
    """Generic live-adjustable config number for Battery Arbitrage settings.

    Values are persisted in storage and take effect on the next coordinator
    tick without requiring an HA restart.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
        storage_key: str,
        translation_key: str,
        default: float,
        icon: str,
        unit: str,
        min_val: float,
        max_val: float,
        step: float,
        mode: NumberMode = NumberMode.SLIDER,
    ) -> None:
        super().__init__(coordinator)
        self._storage_key = storage_key
        self._default = default
        self._attr_unique_id = f"{entry.entry_id}_{storage_key}"
        self._attr_translation_key = translation_key
        self._attr_icon = icon
        self._attr_mode = mode
        self._attr_native_unit_of_measurement = unit
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_native_step = step
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> float:
        return self.coordinator._stored.get(self._storage_key, self._default)

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator._stored[self._storage_key] = round(value, 3)
        await self.coordinator._store.async_save(self.coordinator._stored)
        self.async_write_ha_state()
