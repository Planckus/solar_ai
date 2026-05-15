"""Sensor platform for Battery Arbitrage."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CURRENCY, DEFAULT_CURRENCY, DOMAIN, TEMP_BUCKETS
from .coordinator import BatteryArbitrageCoordinator


@dataclass(frozen=True, kw_only=True)
class BatteryArbitrageSensorDescription(SensorEntityDescription):
    """Sensor description with a value extractor."""

    value_fn: Callable[[dict[str, Any]], Any] = lambda _: None
    # If set, overrides native_unit_of_measurement with the currency substituted in.
    # Use "{}/kWh" for price-per-energy sensors or "{}" for plain currency sensors.
    currency_unit_template: str | None = None
    # If set, the sensor exposes these extra state attributes.
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None


SENSORS: tuple[BatteryArbitrageSensorDescription, ...] = (
    BatteryArbitrageSensorDescription(
        key="mode",
        translation_key="mode",
        icon="mdi:sine-wave",
        value_fn=lambda d: d.get("mode"),
    ),
    BatteryArbitrageSensorDescription(
        key="mode_reason",
        translation_key="mode_reason",
        icon="mdi:information-outline",
        value_fn=lambda d: d.get("reason"),
    ),
    BatteryArbitrageSensorDescription(
        key="export_price",
        translation_key="export_price",
        currency_unit_template="{}/kWh",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:currency-usd",
        value_fn=lambda d: round(d.get("export_price", 0.0), 4),
    ),
    BatteryArbitrageSensorDescription(
        key="grid_spread",
        translation_key="grid_spread",
        currency_unit_template="{}/kWh",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-bar",
        value_fn=lambda d: round(d.get("grid_arbitrage_spread", 0.0), 4),
    ),
    BatteryArbitrageSensorDescription(
        key="price_min",
        translation_key="price_min",
        currency_unit_template="{}/kWh",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:arrow-down-bold",
        value_fn=lambda d: round(d.get("price_min", 0.0), 4),
    ),
    BatteryArbitrageSensorDescription(
        key="price_max",
        translation_key="price_max",
        currency_unit_template="{}/kWh",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:arrow-up-bold",
        value_fn=lambda d: round(d.get("price_max", 0.0), 4),
    ),
    BatteryArbitrageSensorDescription(
        key="price_mean",
        translation_key="price_mean",
        currency_unit_template="{}/kWh",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:approximately-equal",
        value_fn=lambda d: round(d.get("price_mean", 0.0), 4),
    ),
    BatteryArbitrageSensorDescription(
        key="price_p25",
        translation_key="price_p25",
        currency_unit_template="{}/kWh",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:percent",
        value_fn=lambda d: round(d.get("price_p25", 0.0), 4),
    ),
    BatteryArbitrageSensorDescription(
        key="price_p75",
        translation_key="price_p75",
        currency_unit_template="{}/kWh",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:percent",
        value_fn=lambda d: round(d.get("price_p75", 0.0), 4),
    ),
    BatteryArbitrageSensorDescription(
        key="price_next_slot",
        translation_key="price_next_slot",
        currency_unit_template="{}/kWh",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:clock-outline",
        value_fn=lambda d: round(d.get("price_next_slot", 0.0), 4),
    ),
    BatteryArbitrageSensorDescription(
        key="solar_forecast_24h",
        translation_key="solar_forecast_24h",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-power",
        value_fn=lambda d: round(d.get("solar_kwh_24h", 0.0), 2),
    ),
    BatteryArbitrageSensorDescription(
        key="solar_forecast_6h",
        translation_key="solar_forecast_6h",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-power-variant",
        value_fn=lambda d: round(d.get("solar_kwh_6h", 0.0), 2),
    ),
    BatteryArbitrageSensorDescription(
        key="predicted_load_24h",
        translation_key="predicted_load_24h",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:home-lightning-bolt",
        value_fn=lambda d: round(d.get("predicted_house_load_24h_kwh", 0.0), 2),
    ),
    BatteryArbitrageSensorDescription(
        key="exportable_kwh",
        translation_key="exportable_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-arrow-up",
        value_fn=lambda d: round(d.get("exportable_kwh", 0.0), 2),
    ),
    BatteryArbitrageSensorDescription(
        key="importable_kwh",
        translation_key="importable_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-arrow-down",
        value_fn=lambda d: round(d.get("importable_kwh", 0.0), 2),
    ),
    BatteryArbitrageSensorDescription(
        key="load_2h_avg",
        translation_key="load_2h_avg",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:home-lightning-bolt-outline",
        value_fn=lambda d: round(d.get("load_2h_avg_kw", 0.0), 3),
    ),
    BatteryArbitrageSensorDescription(
        key="load_28d_avg",
        translation_key="load_28d_avg",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-timeline-variant",
        value_fn=lambda d: round(d.get("load_28d_avg_kw", 0.0), 3),
    ),
    BatteryArbitrageSensorDescription(
        key="learned_charge_rate",
        translation_key="learned_charge_rate",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-charging",
        value_fn=lambda d: round(d.get("learned_charge_rate", 0.0), 3),
    ),
    BatteryArbitrageSensorDescription(
        key="time_to_charge",
        translation_key="time_to_charge",
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-outline",
        value_fn=lambda d: round(min(d.get("time_to_charge_h", 999.0), 999.0), 1),
    ),
    BatteryArbitrageSensorDescription(
        key="cell_temp_low",
        translation_key="cell_temp_low",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        value_fn=lambda d: d.get("cell_temp_low"),
    ),
    BatteryArbitrageSensorDescription(
        key="evcc_battery_mode",
        translation_key="evcc_battery_mode",
        icon="mdi:battery-sync",
        value_fn=lambda d: d.get("evcc_battery_mode", "normal"),
    ),
    BatteryArbitrageSensorDescription(
        key="solar_accuracy_factor",
        translation_key="solar_accuracy_factor",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-bell-curve-cumulative",
        value_fn=lambda d: round(d.get("solar_accuracy_factor", 1.0) * 100, 1),
    ),
    BatteryArbitrageSensorDescription(
        key="net_solar_for_battery",
        translation_key="net_solar_for_battery",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-power-variant-outline",
        value_fn=lambda d: round(d.get("net_solar_for_battery", 0.0), 2),
    ),
    BatteryArbitrageSensorDescription(
        key="solar_forecast_24h_adjusted",
        translation_key="solar_forecast_24h_adjusted",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-power",
        value_fn=lambda d: round(d.get("solar_kwh_24h_adjusted", 0.0), 2),
    ),
    BatteryArbitrageSensorDescription(
        key="solar_forecast_6h_adjusted",
        translation_key="solar_forecast_6h_adjusted",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-power-variant",
        value_fn=lambda d: round(d.get("solar_kwh_6h_adjusted", 0.0), 2),
    ),
    # ── Seasonal & EV learning ────────────────────────────────────────────
    BatteryArbitrageSensorDescription(
        key="season_mode",
        translation_key="season_mode",
        icon="mdi:weather-sunny-off",
        value_fn=lambda d: "summer" if d.get("is_summer_mode") else "winter",
    ),
    BatteryArbitrageSensorDescription(
        key="solar_28d_avg",
        translation_key="solar_28d_avg",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-month",
        value_fn=lambda d: round(d.get("solar_28d_avg", 0.0), 2),
    ),
    BatteryArbitrageSensorDescription(
        key="ev_charge_probability",
        translation_key="ev_charge_probability",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:car-electric",
        value_fn=lambda d: round(d.get("ev_block_prob", 0.0) * 100, 1),
    ),
    # ── Savings tracking ──────────────────────────────────────────────────
    BatteryArbitrageSensorDescription(
        key="savings_actual_today",
        translation_key="savings_actual_today",
        currency_unit_template="{}",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cash-plus",
        value_fn=lambda d: d.get("savings_actual_today", 0.0),
    ),
    BatteryArbitrageSensorDescription(
        key="savings_missed_today",
        translation_key="savings_missed_today",
        currency_unit_template="{}",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cash-remove",
        value_fn=lambda d: d.get("savings_missed_today", 0.0),
    ),
    BatteryArbitrageSensorDescription(
        key="savings_actual_week",
        translation_key="savings_actual_week",
        currency_unit_template="{}",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cash-plus",
        value_fn=lambda d: d.get("savings_actual_week", 0.0),
    ),
    BatteryArbitrageSensorDescription(
        key="savings_missed_week",
        translation_key="savings_missed_week",
        currency_unit_template="{}",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cash-remove",
        value_fn=lambda d: d.get("savings_missed_week", 0.0),
    ),
    BatteryArbitrageSensorDescription(
        key="savings_actual_month",
        translation_key="savings_actual_month",
        currency_unit_template="{}",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cash-plus",
        value_fn=lambda d: d.get("savings_actual_month", 0.0),
    ),
    BatteryArbitrageSensorDescription(
        key="savings_missed_month",
        translation_key="savings_missed_month",
        currency_unit_template="{}",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cash-remove",
        value_fn=lambda d: d.get("savings_missed_month", 0.0),
    ),
    # ── Auto-detected battery parameters ─────────────────────────────────
    BatteryArbitrageSensorDescription(
        key="learned_capacity",
        translation_key="learned_capacity",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-heart-variant",
        value_fn=lambda d: round(d["learned_capacity"], 2) if d.get("learned_capacity") is not None else None,
    ),
    BatteryArbitrageSensorDescription(
        key="auto_efficiency",
        translation_key="auto_efficiency",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-sync-outline",
        value_fn=lambda d: round(d["auto_efficiency"] * 100, 1) if d.get("auto_efficiency") is not None else None,
    ),
    BatteryArbitrageSensorDescription(
        key="capacity_sample_count",
        translation_key="capacity_sample_count",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:counter",
        value_fn=lambda d: d.get("capacity_sample_count", 0),
    ),
    # ── Grid overcurrent protection ───────────────────────────────────────
    BatteryArbitrageSensorDescription(
        key="grid_power",
        translation_key="grid_power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:transmission-tower-import",
        value_fn=lambda d: round(d.get("grid_power_kw", 0.0), 3),
    ),
    BatteryArbitrageSensorDescription(
        key="grid_headroom",
        translation_key="grid_headroom",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:transmission-tower-export",
        value_fn=lambda d: round(d.get("grid_headroom_kw", 0.0), 3),
    ),
    # ── Live solar production ─────────────────────────────────────────────
    BatteryArbitrageSensorDescription(
        key="pv_power",
        translation_key="pv_power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-power",
        value_fn=lambda d: round(d.get("pv_power_kw", 0.0), 3),
    ),
    # ── DSO tariff ───────────────────────────────────────────────────────
    BatteryArbitrageSensorDescription(
        key="tariff_this_hour",
        translation_key="tariff_this_hour",
        currency_unit_template="{}/kWh",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:transmission-tower",
        value_fn=lambda d: round(d.get("tariff_this_hour", 0.0), 4),
    ),
    # ── 24h price chart ──────────────────────────────────────────────────
    BatteryArbitrageSensorDescription(
        key="price_chart",
        translation_key="price_chart",
        icon="mdi:chart-line",
        # State = number of slots in the chart (useful for availability checks)
        value_fn=lambda d: len(d.get("price_chart_slots", [])),
        attrs_fn=lambda d: {
            "slots": d.get("price_chart_slots", []),
        },
    ),
    # ── Tonight's plan ───────────────────────────────────────────────────
    BatteryArbitrageSensorDescription(
        key="todays_plan",
        translation_key="todays_plan",
        icon="mdi:calendar-clock",
        value_fn=lambda d: d.get("plan_text", "No data"),
        attrs_fn=lambda d: {
            "charge_hours": d.get("plan_charge_hours", []),
            "export_hours": d.get("plan_export_hours", []),
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Battery Arbitrage sensors from config entry."""
    coordinator: BatteryArbitrageCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = [
        BatteryArbitrageSensor(coordinator, entry, desc) for desc in SENSORS
    ]

    # One sensor per temperature bucket for the learned charge rates
    for bucket_key, _, _, _ in TEMP_BUCKETS:
        entities.append(
            BatteryArbitrageLearnedRateSensor(coordinator, entry, bucket_key)
        )

    async_add_entities(entities)


class BatteryArbitrageSensor(CoordinatorEntity[BatteryArbitrageCoordinator], SensorEntity):
    """A single Battery Arbitrage sensor derived from coordinator data."""

    entity_description: BatteryArbitrageSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
        description: BatteryArbitrageSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_unit_of_measurement(self) -> str | None:
        template = self.entity_description.currency_unit_template
        if template:
            currency = self.coordinator.config.get(CONF_CURRENCY, DEFAULT_CURRENCY)
            return template.format(currency)
        return self.entity_description.native_unit_of_measurement

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fn = self.entity_description.attrs_fn
        if fn is None or self.coordinator.data is None:
            return None
        return fn(self.coordinator.data)


class BatteryArbitrageLearnedRateSensor(
    CoordinatorEntity[BatteryArbitrageCoordinator], SensorEntity
):
    """Sensor showing the learned charge rate for one temperature bucket."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery-charging-outline"

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
        bucket_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._bucket_key = bucket_key
        self._attr_unique_id = f"{entry.entry_id}_learned_rate_{bucket_key}"
        self._attr_translation_key = f"learned_rate_{bucket_key}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> float:
        return round(self.coordinator.get_learned_rate(self._bucket_key), 3)


def _device_info(entry: ConfigEntry) -> dict:
    return {
        "identifiers": {(DOMAIN, entry.entry_id)},
        "name": "Solar AI",
        "manufacturer": "Community",
        "model": "Solar AI v0.1",
        "entry_type": "service",
    }
