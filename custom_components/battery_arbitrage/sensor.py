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
from homeassistant.const import (
    EntityCategory,
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfInformation,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
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
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-power",
        value_fn=lambda d: round(d.get("solar_kwh_24h", 0.0), 2),
    ),
    BatteryArbitrageSensorDescription(
        key="solar_forecast_6h",
        translation_key="solar_forecast_6h",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-power-variant",
        value_fn=lambda d: round(d.get("solar_kwh_6h", 0.0), 2),
    ),
    BatteryArbitrageSensorDescription(
        key="predicted_load_24h",
        translation_key="predicted_load_24h",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:home-lightning-bolt",
        value_fn=lambda d: round(d.get("predicted_house_load_24h_kwh", 0.0), 2),
    ),
    BatteryArbitrageSensorDescription(
        key="exportable_kwh",
        translation_key="exportable_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-arrow-up",
        value_fn=lambda d: round(d.get("exportable_kwh", 0.0), 2),
    ),
    BatteryArbitrageSensorDescription(
        key="importable_kwh",
        translation_key="importable_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
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
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-power-variant-outline",
        value_fn=lambda d: round(d.get("net_solar_for_battery", 0.0), 2),
    ),
    BatteryArbitrageSensorDescription(
        key="solar_forecast_24h_adjusted",
        translation_key="solar_forecast_24h_adjusted",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-power",
        value_fn=lambda d: round(d.get("solar_kwh_24h_adjusted", 0.0), 2),
    ),
    BatteryArbitrageSensorDescription(
        key="solar_forecast_6h_adjusted",
        translation_key="solar_forecast_6h_adjusted",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
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
    BatteryArbitrageSensorDescription(
        key="house_load_this_hour",
        translation_key="house_load_this_hour",
        native_unit_of_measurement="kW",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:home-clock",
        # State = learned load for the current hour; full daily profile in attributes
        value_fn=lambda d: round(
            (d.get("house_load_hourly") or [0.0] * 24)[
                __import__("datetime").datetime.now().hour
            ],
            3,
        ),
        attrs_fn=lambda d: {
            "profile_kw": d.get("house_load_hourly", [0.0] * 24),
        },
    ),
    BatteryArbitrageSensorDescription(
        key="ev_max_charge_rate",
        translation_key="ev_max_charge_rate",
        native_unit_of_measurement="kW",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:car-electric",
        value_fn=lambda d: round(d.get("ev_max_kw", 0.0), 2),
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
    BatteryArbitrageSensorDescription(
        key="feed_in_tariff",
        translation_key="feed_in_tariff",
        native_unit_of_measurement="DKK/kWh",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:transmission-tower-export",
        suggested_display_precision=4,
        value_fn=lambda d: round(d.get("feed_in_tariff_total", 0.0), 4),
    ),
    # Mirror sensor for min_export_price — sensors get the "dp" field in the
    # compact entity registry display entry, so suggested_display_precision
    # actually forces two decimal places in Lovelace (unlike NumberEntity).
    BatteryArbitrageSensorDescription(
        key="min_export_price_display",
        translation_key="min_export_price_display",
        native_unit_of_measurement="DKK/kWh",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:currency-eur-off",
        suggested_display_precision=2,
        value_fn=lambda d: round(float(d.get("min_export_price", 0.0)), 2),
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
    # v0.48.1 — hourly, timestamped buy/sell price forecast over the full
    # horizon (today + tomorrow once published). Feeds the "price matrix" card.
    # State = next-hour buy price; attrs hold the full forecast.
    BatteryArbitrageSensorDescription(
        key="price_forecast",
        translation_key="price_forecast",
        icon="mdi:table-clock",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="DKK/kWh",
        value_fn=lambda d: (d.get("buy_price_forecast") or [{}])[0].get("buy", 0.0),
        attrs_fn=lambda d: {
            "slots": d.get("buy_price_forecast", []),
        },
    ),
    # ── 48h solar forecast chart (v0.28.2) ────────────────────────────────
    # State = number of slots available (handy for dashboard "no data" guards).
    # `slots` attribute holds the per-slot forecast points consumed by the
    # ApexCharts card on the EV / OCPP tab. Each entry has:
    #   start    — ISO timestamp of the slot start
    #   raw_kw   — raw Solcast / Forecast.Solar value
    #   adj_kw   — scaled by the per-hour accuracy factor (solcelleprognose)
    #   factor   — the accuracy factor itself (debug / tooltip use)
    BatteryArbitrageSensorDescription(
        key="solar_forecast_48h_chart",
        translation_key="solar_forecast_48h_chart",
        icon="mdi:weather-sunny",
        value_fn=lambda d: len(d.get("solar_chart_slots", [])),
        attrs_fn=lambda d: {
            "slots": d.get("solar_chart_slots", []),
            # v0.28.3: daily totals (adjusted via solcelleprognose factor)
            "today_remaining_kwh":     d.get("solar_today_remaining_adj_kwh", 0.0),
            "today_remaining_raw_kwh": d.get("solar_today_remaining_raw_kwh", 0.0),
            "tomorrow_kwh":            d.get("solar_tomorrow_adj_kwh", 0.0),
            "tomorrow_raw_kwh":        d.get("solar_tomorrow_raw_kwh", 0.0),
        },
    ),
    # ── Short-term solar correction (v0.28.6) ─────────────────────────────
    # State = current intra-hour residual as a percentage deviation from
    # Solcast for the most recent closed 15-min slot, rounded.
    #   factor > 1 → actual > forecast (sun better than predicted)
    #   factor < 1 → actual < forecast (cloudier than predicted)
    BatteryArbitrageSensorDescription(
        key="solar_forecast_error_now",
        translation_key="solar_forecast_error_now",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-bell-curve",
        value_fn=lambda d: round((d.get("solar_short_term_factor", 1.0) - 1.0) * 100.0, 1),
        attrs_fn=lambda d: {
            "factor": d.get("solar_short_term_factor", 1.0),
            "samples": d.get("solar_short_term_samples", 0),
            "recent": d.get("solar_short_term_recent", []),
            "decay_hours": d.get("solar_short_term_decay_h", 2.0),
        },
    ),
    # ── Daily kWh forecast totals (v0.28.3, adjusted) ─────────────────────
    BatteryArbitrageSensorDescription(
        key="solar_today_remaining_kwh",
        translation_key="solar_today_remaining_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-sunset-down",
        value_fn=lambda d: round(d.get("solar_today_remaining_adj_kwh", 0.0), 2),
    ),
    BatteryArbitrageSensorDescription(
        key="solar_tomorrow_kwh",
        translation_key="solar_tomorrow_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-sunny",
        value_fn=lambda d: round(d.get("solar_tomorrow_adj_kwh", 0.0), 2),
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
    # ── Action log (export / charge session history) ──────────────────────
    BatteryArbitrageSensorDescription(
        key="action_log",
        translation_key="action_log",
        icon="mdi:history",
        # State = total number of logged sessions
        value_fn=lambda d: d.get("action_log_count", 0),
        attrs_fn=lambda d: {
            "sessions": d.get("action_log", []),
        },
    ),
    # ── Disk-space monitor (v0.49.0) ──────────────────────────────────────
    # State = free space (GB) on the partition HA runs on. Attributes give the
    # % free, total/used, the probe path, and the configured alarm threshold.
    BatteryArbitrageSensorDescription(
        key="disk_free",
        translation_key="disk_free",
        icon="mdi:harddisk",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("disk_free_gb"),
        attrs_fn=lambda d: {
            "pct_free": d.get("disk_pct_free"),
            "total_gb": d.get("disk_total_gb"),
            "used_gb": d.get("disk_used_gb"),
            "path": d.get("disk_path"),
            "alarm_threshold_pct": d.get("disk_alarm_threshold_pct"),
        },
    ),
    # v0.42.0 — cumulative income from exported energy (DKK). TOTAL_INCREASING
    # + MONETARY so HA records long-term statistics (use the Energy dashboard
    # for arbitrary from/to sums); attributes give at-a-glance period totals
    # and the daily series for the in-dashboard chart.
    BatteryArbitrageSensorDescription(
        key="export_income",
        translation_key="export_income",
        icon="mdi:cash-plus",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="DKK",
        value_fn=lambda d: d.get("export_income_total", 0.0),
        attrs_fn=lambda d: {
            "today": d.get("export_income_today", 0.0),
            "last_7_days": d.get("export_income_7d", 0.0),
            "last_30_days": d.get("export_income_30d", 0.0),
            "this_month": d.get("export_income_month", 0.0),
            "this_year": d.get("export_income_year", 0.0),
            "daily": d.get("export_income_daily", []),
        },
    ),
    # v0.48.0 — cumulative cost of ALL grid import (house + battery charging).
    BatteryArbitrageSensorDescription(
        key="import_cost",
        translation_key="import_cost",
        icon="mdi:cash-minus",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="DKK",
        value_fn=lambda d: d.get("import_cost_total", 0.0),
        attrs_fn=lambda d: {
            "today": d.get("import_cost_today", 0.0),
            "last_7_days": d.get("import_cost_7d", 0.0),
            "last_30_days": d.get("import_cost_30d", 0.0),
            "this_month": d.get("import_cost_month", 0.0),
            "this_year": d.get("import_cost_year", 0.0),
            "daily": d.get("import_cost_daily", []),
        },
    ),
    # v0.48.0 — NET grid balance = export income − import cost. Can be negative
    # (net buyer). MEASUREMENT, not total_increasing, since it moves both ways.
    BatteryArbitrageSensorDescription(
        key="net_grid_balance",
        translation_key="net_grid_balance",
        icon="mdi:scale-balance",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="DKK",
        value_fn=lambda d: d.get("net_grid_total", 0.0),
        attrs_fn=lambda d: {
            "today": d.get("net_grid_today", 0.0),
            "last_7_days": d.get("net_grid_7d", 0.0),
            "last_30_days": d.get("net_grid_30d", 0.0),
            "this_month": d.get("net_grid_month", 0.0),
            "this_year": d.get("net_grid_year", 0.0),
            "export_today": d.get("export_income_today", 0.0),
            "import_today": d.get("import_cost_today", 0.0),
            "daily": d.get("net_grid_daily", []),
        },
    ),
    # ── EV charge controller (Phase B1) ──────────────────────────────────
    BatteryArbitrageSensorDescription(
        key="ev_target_kw",
        translation_key="ev_target_kw",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:car-electric",
        value_fn=lambda d: round(d.get("ev_target_kw", 0.0), 2),
        # v0.45.0 — E1: the EV demand the optimiser is reserving for the near
        # term (0 = no live forced session; the learned hourly model is used).
        attrs_fn=lambda d: {
            "dp_session_demand_kw": d.get("ev_dp_session_kw", 0.0),
        },
    ),
    BatteryArbitrageSensorDescription(
        key="ev_target_amps",
        translation_key="ev_target_amps",
        native_unit_of_measurement="A",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:current-ac",
        value_fn=lambda d: int(d.get("ev_target_amps", 0)),
    ),
    BatteryArbitrageSensorDescription(
        key="ev_surplus_kw",
        translation_key="ev_surplus_kw",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-power-variant",
        value_fn=lambda d: round(d.get("ev_surplus_kw", 0.0), 2),
    ),
    BatteryArbitrageSensorDescription(
        key="ev_active_mode",
        translation_key="ev_active_mode",
        icon="mdi:car-electric-outline",
        value_fn=lambda d: d.get("ev_active_mode", "locked"),
    ),
    BatteryArbitrageSensorDescription(
        key="ev_reason",
        translation_key="ev_reason",
        icon="mdi:information-outline",
        value_fn=lambda d: d.get("ev_reason", "EV controller inactive"),
    ),
    # ── EV status (state machine + countdown, v0.26.1) ─────────────────────
    # State: IDLE / ARMING / CHARGING / COOLING (see _apply_ev_time_window).
    # Attrs expose the seconds remaining on the start- and stop-windows so the
    # dashboard can render "Starter om 23 sek" / "Stopper om 142 sek" — telling
    # the user *why* the controller is being patient during cloud-flicker.
    BatteryArbitrageSensorDescription(
        key="ev_status",
        translation_key="ev_status",
        icon="mdi:ev-station",
        value_fn=lambda d: d.get("ev_state", "IDLE"),
        attrs_fn=lambda d: {
            "arming_seconds_left": d.get("ev_arming_seconds_left", 0),
            "cooling_seconds_left": d.get("ev_cooling_seconds_left", 0),
            # v0.28.1: ISO timestamps for live per-second countdown
            "arming_until": d.get("ev_arming_until"),
            "cooling_until": d.get("ev_cooling_until"),
            "active_mode": d.get("ev_active_mode", "locked"),
            "target_kw": d.get("ev_target_kw", 0.0),
            "target_amps": d.get("ev_target_amps", 0),
            "surplus_kw": d.get("ev_surplus_kw", 0.0),
            "last_commanded_amps": d.get("ev_last_commanded_amps", 0),
            "reason": d.get("ev_reason", ""),
            "enabled": d.get("ev_enabled", False),
            "battery_locked": d.get("ev_battery_locked", False),
        },
    ),
    # ── Solar floor log (block/resume events due to price floor) ─────────
    BatteryArbitrageSensorDescription(
        key="solar_floor_log",
        translation_key="solar_floor_log",
        icon="mdi:solar-power-variant-outline",
        # State = total number of recorded floor-block events
        value_fn=lambda d: d.get("solar_floor_log_count", 0),
        attrs_fn=lambda d: {
            "events": d.get("solar_floor_log", []),
        },
    ),
    # ── Solar hourly learning diagnostic (Phase B1 — adaptive accuracy) ────
    BatteryArbitrageSensorDescription(
        key="solar_hourly_accuracy",
        translation_key="solar_hourly_accuracy",
        icon="mdi:chart-bell-curve",
        # State = number of hours (0–24) whose bucket has enough samples to
        # have learned a per-hour factor. The rest still use the global
        # fallback. A simple warm-up progress indicator.
        value_fn=lambda d: sum(
            1 for c in d.get("solar_hourly_samples", []) if c >= 8
        ),
        attrs_fn=lambda d: {
            "hourly_factors": {
                str(h): round(f, 3)
                for h, f in enumerate(d.get("solar_hourly_factors", []))
            },
            "hourly_samples": {
                str(h): c
                for h, c in enumerate(d.get("solar_hourly_samples", []))
            },
            "global_factor": round(d.get("solar_accuracy_factor", 1.0), 3),
            "total_samples": sum(d.get("solar_hourly_samples", [])),
            "warmup_complete": all(
                c >= 8 for c in d.get("solar_hourly_samples", [])
            ) if d.get("solar_hourly_samples") else False,
            # v0.43.0 — S1 groundwork: forecast-ratio spread per hour (P10/P50/
            # P90). Shows how reliable each hour's forecast is. None where cold.
            "hourly_p10": {
                str(h): v for h, v in enumerate(d.get("solar_hourly_p10", []))
                if v is not None
            },
            "hourly_p50": {
                str(h): v for h, v in enumerate(d.get("solar_hourly_p50", []))
                if v is not None
            },
            "hourly_p90": {
                str(h): v for h, v in enumerate(d.get("solar_hourly_p90", []))
                if v is not None
            },
            # v0.44.0 — S1: the percentile the optimiser currently plans
            # against (50 = median = neutral; lower = more conservative solar).
            "confidence_pct": d.get("solar_confidence_pct", 50),
        },
    ),
    # ── Prediction scorecard (v0.43.0 — M1) ───────────────────────────────
    # State = rolling 7-day SoC mean-absolute-error (% points): how far the
    # optimiser's predicted battery trajectory landed from reality. Lower is
    # better. Observability only — the baseline against which any future
    # precision change (probabilistic solar, EV session-awareness, …) is judged.
    BatteryArbitrageSensorDescription(
        key="prediction_accuracy",
        translation_key="prediction_accuracy",
        icon="mdi:target",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("prediction_soc_mae_7d", 0.0),
        attrs_fn=lambda d: {
            "soc_mae_7d": d.get("prediction_soc_mae_7d", 0.0),
            "soc_mae_30d": d.get("prediction_soc_mae_30d", 0.0),
            "solar_mape_pct": d.get("prediction_solar_mape", 0.0),
            "samples": d.get("prediction_samples", 0),
            "action_mix": d.get("prediction_action_mix", {}),
            "recent": d.get("prediction_log", []),
        },
    ),
    # ── Dynamic discharge floor (v0.47.0 — C) ─────────────────────────────
    # State = the export floor actually in effect (% SoC). When the dynamic
    # feature is on this is the bridge-to-refill reserve; when off it's the
    # static slider value. Attributes show whether the dynamic floor is active,
    # its computed value, and the self-learned safety margin.
    BatteryArbitrageSensorDescription(
        key="effective_floor",
        translation_key="effective_floor",
        icon="mdi:battery-arrow-down-outline",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("effective_floor_soc", 0),
        attrs_fn=lambda d: {
            "dynamic_active": d.get("dynamic_floor_active", False),
            "dynamic_floor_soc": d.get("dynamic_floor_soc"),
            "reserve_margin": d.get("discharge_reserve_margin", 1.0),
        },
    ),
    # ─────────────────────────────────────────────────────────────────────
    # Embedded OCPP charger sensors (v0.27.0)
    # Replace what `lbbrhzn/ocpp` integration used to expose. State is read
    # directly from Solar AI's embedded OCPP server via the coordinator's
    # `get_charger_telemetry()` (merged into the result dict each tick).
    # ─────────────────────────────────────────────────────────────────────
    BatteryArbitrageSensorDescription(
        key="charger_status",
        translation_key="charger_status",
        icon="mdi:ev-station",
        value_fn=lambda d: d.get("charger_status", "Unavailable"),
        attrs_fn=lambda d: {
            "seconds_since_seen": d.get("charger_seconds_since_seen"),
            "protocol_errors": d.get("charger_protocol_errors", 0),
            "last_protocol_error": d.get("charger_last_protocol_error", ""),
        },
    ),
    BatteryArbitrageSensorDescription(
        key="ocpp_diagnostics",
        translation_key="ocpp_diagnostics",
        icon="mdi:cable-data",
        # v0.40.4 — surfaces the OCPP server internals so command/telemetry
        # desyncs are visible without a file log. State = charger status;
        # attributes carry the command outcomes + freshness ages.
        value_fn=lambda d: d.get("charger_status", "Unavailable"),
        attrs_fn=lambda d: {
            "session_active": d.get("charger_session_active", False),
            "transaction_id": d.get("charger_transaction_id"),
            "commanded_amps": d.get("charger_commanded_amps"),
            "last_set_profile_status": d.get("charger_last_set_profile_status"),
            "last_set_profile_age_s": d.get("charger_last_set_profile_age_s"),
            "last_remote_start_status": d.get("charger_last_remote_start_status"),
            "last_remote_start_age_s": d.get("charger_last_remote_start_age_s"),
            "metervalues_age_s": d.get("charger_metervalues_age_s"),
            "seconds_since_seen": d.get("charger_seconds_since_seen"),
            "protocol_errors": d.get("charger_protocol_errors", 0),
            "last_protocol_error": d.get("charger_last_protocol_error", ""),
            "stuck_seconds": d.get("charger_stuck_seconds", 0.0),
            "last_recovery_action": d.get("charger_last_recovery_action"),
            "last_recovery_age_s": d.get("charger_last_recovery_age_s"),
            "recent_events": d.get("charger_events", []),
        },
    ),
    BatteryArbitrageSensorDescription(
        key="charger_power",
        translation_key="charger_power",
        icon="mdi:lightning-bolt",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=lambda d: d.get("charger_power_kw", 0.0),
        attrs_fn=lambda d: {
            "voltage_v": d.get("charger_voltage_v"),
        },
    ),
    BatteryArbitrageSensorDescription(
        key="charger_session_energy",
        translation_key="charger_session_energy",
        icon="mdi:battery-charging-100",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda d: d.get("charger_session_energy_kwh", 0.0),
        attrs_fn=lambda d: {
            "session_active": d.get("charger_session_active", False),
            "session_duration_min": d.get("charger_session_duration_min", 0.0),
        },
    ),
    BatteryArbitrageSensorDescription(
        key="charger_session_duration",
        translation_key="charger_session_duration",
        icon="mdi:timer-outline",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda d: d.get("charger_session_duration_min", 0.0),
    ),
    BatteryArbitrageSensorDescription(
        key="charger_lifetime_energy",
        translation_key="charger_lifetime_energy",
        icon="mdi:counter",
        # TOTAL_INCREASING + ENERGY makes this eligible for the HA Energy
        # dashboard's "individual devices" section.
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda d: d.get("charger_lifetime_energy_kwh", 0.0),
    ),
    BatteryArbitrageSensorDescription(
        key="charger_info",
        translation_key="charger_info",
        icon="mdi:information-outline",
        # State = serial (or vendor if serial blank). Attrs expose the rest.
        value_fn=lambda d: (
            d.get("charger_serial") or d.get("charger_vendor") or "Unknown"
        ),
        attrs_fn=lambda d: {
            "vendor": d.get("charger_vendor", ""),
            "model": d.get("charger_model", ""),
            "firmware": d.get("charger_firmware", ""),
            "serial": d.get("charger_serial", ""),
            "seconds_since_seen": d.get("charger_seconds_since_seen"),
        },
    ),
    BatteryArbitrageSensorDescription(
        key="charger_session_log",
        translation_key="charger_session_log",
        icon="mdi:history",
        # State = total number of completed sessions
        value_fn=lambda d: d.get("charger_session_count", 0),
        # v0.28.4: expose the full last-20 session list (newest first) so the
        # Logs tab can render a proper history table with grid/solar split.
        attrs_fn=lambda d: {
            "last_session": d.get("charger_last_session"),
            "sessions": d.get("charger_session_log_list", []),
            "live_solar_kwh": d.get("charger_session_solar_kwh", 0.0),
            "live_grid_kwh": d.get("charger_session_grid_kwh", 0.0),
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

    # v0.37.1 — buy-price breakdown sensor. Exposes the current slot's
    # per-component buy price via attributes so the dashboard's
    # "Prissammensætning" card can branch on the active buy_price_mode
    # and show the authoritative breakdown (Strømligning's own component
    # values when in stromligning mode; the user's manual sliders in
    # manual mode; Octopus's value_inc_vat in octopus mode).
    entities.append(BatteryArbitrageBuyPriceBreakdownSensor(coordinator, entry))

    # v0.38.0 — one slot-summary sensor per EV schedule slot (1..MAX).
    # State = active/idle/disabled/empty; attributes carry days, times,
    # mode, name. The dashboard slot cards read everything from these.
    from .const import EV_SCHEDULES_MAX as _SCHED_MAX
    for idx in range(1, _SCHED_MAX + 1):
        entities.append(BatteryArbitrageEvScheduleSlotSensor(coordinator, entry, idx))

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


class BatteryArbitrageBuyPriceBreakdownSensor(
    CoordinatorEntity[BatteryArbitrageCoordinator], SensorEntity
):
    """Per-component breakdown of the current slot's buy price (v0.37.1).

    State: the current slot's all-in buy price (DKK/kWh by default; the
    integration's currency setting applies).

    Attributes: a `mode` field telling the dashboard which line stack to
    render (`manual`, `stromligning`, `octopus`), plus the components for
    that mode. For Strømligning mode the components come from Strømligning's
    own API response — that's the canonical source, and using it eliminates
    the "card shows my slider values, but the optimiser uses something
    else" confusion noted in v0.37.0.

    The dashboard's "Prissammensætning" markdown card reads these attributes
    and renders the right breakdown. The user's VAT slider is intentionally
    NOT used in stromligning/octopus modes — see `_vat_slider_available`
    in number.py.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "buy_price_breakdown"
    _attr_icon = "mdi:receipt-text-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.MONETARY

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_buy_price_breakdown"
        self._attr_device_info = _device_info(entry)

    @property
    def native_unit_of_measurement(self) -> str | None:
        currency = self.coordinator.config.get(CONF_CURRENCY, DEFAULT_CURRENCY)
        return f"{currency}/kWh"

    def _current_mode(self) -> str:
        from .const import (  # noqa: PLC0415
            BUY_PRICE_MODE_STROMLIGNING,
            BUY_PRICE_MODE_OCTOPUS,
            CONF_BUY_PRICE_MODE,
            DEFAULT_BUY_PRICE_MODE,
        )
        mode = self.coordinator.config.get(CONF_BUY_PRICE_MODE, DEFAULT_BUY_PRICE_MODE)
        if mode == BUY_PRICE_MODE_STROMLIGNING:
            return "stromligning"
        if mode == BUY_PRICE_MODE_OCTOPUS:
            return "octopus"
        return "manual"

    def _current_stromligning_entry(self) -> dict | None:
        """Look up the cached Strømligning slot for the current 15-min slot.

        v0.39.6 — lookup at 15-min resolution, matching the cache key built
        by `stromligning.fetch_prices`. Falls back to an hour-aligned key
        when the 15-min lookup misses (for products/dates where Strømligning
        returns hourly slots).
        """
        from datetime import datetime, timezone   # noqa: PLC0415
        cache = getattr(self.coordinator, "_cached_stromligning_prices", {}) or {}
        if not cache:
            return None
        now_utc = datetime.now(timezone.utc)
        slot_minute = (now_utc.minute // 15) * 15
        key = (now_utc.replace(minute=slot_minute, second=0, microsecond=0)
               .strftime("%Y-%m-%dT%H:%M:%S.000Z"))
        entry = cache.get(key)
        if entry is None and slot_minute != 0:
            key_h = (now_utc.replace(minute=0, second=0, microsecond=0)
                     .strftime("%Y-%m-%dT%H:%M:%S.000Z"))
            entry = cache.get(key_h)
        return entry

    def _current_octopus_entry(self) -> dict | None:
        """Look up the cached Octopus rate for the current 30-min slot."""
        from datetime import datetime, timezone   # noqa: PLC0415
        cache = getattr(self.coordinator, "_cached_octopus_prices", {}) or {}
        if not cache:
            return None
        now = datetime.now(timezone.utc)
        key_30 = (now.replace(minute=(now.minute // 30) * 30,
                              second=0, microsecond=0)
                  .strftime("%Y-%m-%dT%H:%M:%SZ"))
        entry = cache.get(key_30)
        if entry is None:
            key_h = (now.replace(minute=0, second=0, microsecond=0)
                     .strftime("%Y-%m-%dT%H:%M:%SZ"))
            entry = cache.get(key_h)
        return entry

    @property
    def native_value(self) -> float | None:
        mode = self._current_mode()
        if mode == "stromligning":
            entry = self._current_stromligning_entry()
            if entry:
                try:
                    # v0.39.5: was entry["price"]["price"]["total"] (wrong
                    # nesting). API has just `entry.price.total`.
                    return round(float(entry["price"]["total"]), 4)
                except (KeyError, TypeError, ValueError):
                    pass
        elif mode == "octopus":
            entry = self._current_octopus_entry()
            if entry:
                try:
                    # Octopus: pence/kWh → currency-units/kWh
                    return round(float(entry["value_inc_vat"]) / 100.0, 4)
                except (KeyError, TypeError, ValueError):
                    pass
        # Manual mode (or stromligning/octopus cache miss) — pull the live
        # buy price the coordinator has computed. `buy_price_next_slot` is
        # what the optimiser actually used for its decision in the most
        # recent tick (covers the half-hour boundary cleanly for chargers
        # that switch every 30 min like Octopus).
        data = self.coordinator.data or {}
        for k in ("buy_price_next_slot", "current_buy_price", "buy_price"):
            v = data.get(k)
            if v is not None:
                try:
                    return round(float(v), 4)
                except (TypeError, ValueError):
                    pass
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        mode = self._current_mode()
        attrs: dict[str, Any] = {"mode": mode}
        if mode == "stromligning":
            entry = self._current_stromligning_entry()
            if entry:
                try:
                    from . import stromligning as sl   # noqa: PLC0415
                    d = sl.get_price_details(entry)
                    attrs.update({
                        "spot":          d["spot"],
                        "surcharge":     d["surcharge"],
                        "net_tariff":    d["net_tariff"],
                        "system_tariff": d["system_tariff"],
                        "distribution":  d["distribution"],
                        "elafgift":      d["elafgift"],
                        "vat_pct":       d["vat_pct"],
                        "total_inc_vat": d["total_inc_vat"],
                        "subtotal_ex_vat": round(
                            d["spot"] + d["surcharge"] + d["net_tariff"]
                            + d["system_tariff"] + d["distribution"]
                            + d["elafgift"], 4,
                        ),
                        "vat_amount": round(
                            d["total_inc_vat"] - (
                                d["spot"] + d["surcharge"] + d["net_tariff"]
                                + d["system_tariff"] + d["distribution"]
                                + d["elafgift"]
                            ), 4,
                        ),
                    })
                except Exception:  # noqa: BLE001
                    pass
        elif mode == "octopus":
            entry = self._current_octopus_entry()
            if entry:
                try:
                    inc_vat = float(entry["value_inc_vat"]) / 100.0
                    ex_vat = float(entry["value_exc_vat"]) / 100.0
                    attrs.update({
                        "value_inc_vat": round(inc_vat, 4),
                        "value_exc_vat": round(ex_vat, 4),
                        "vat_amount":    round(inc_vat - ex_vat, 4),
                        "vat_pct":       round((inc_vat / ex_vat - 1) * 100, 2)
                                         if ex_vat > 0 else 0.0,
                        "valid_from":    entry.get("valid_from"),
                        "valid_to":      entry.get("valid_to"),
                    })
                except (KeyError, TypeError, ValueError):
                    pass
        # Manual mode has no extra attributes — the dashboard already has
        # all the inputs as separate `number.*` entities.
        return attrs



class BatteryArbitrageEvScheduleSlotSensor(
    CoordinatorEntity[BatteryArbitrageCoordinator], SensorEntity
):
    """Per-slot summary sensor for native EV schedules (v0.38.0).

    Four of these are always created — one per `slot in 1..EV_SCHEDULES_MAX`.
    The dashboard reads everything for a slot card from this single sensor:
    state tells whether the slot is currently active / idle / disabled / empty;
    attributes carry the per-day flags and the human-readable summary used
    in the card header and the day-chip buttons.

    `_stored["ev_schedules"]` is the source. The dashboard service buttons
    (e.g. toggle_schedule_day, add_schedule_slot) mutate that list and
    fire a dispatcher signal that this sensor listens for.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
        slot_idx: int,
    ) -> None:
        super().__init__(coordinator)
        self._slot_idx = slot_idx
        self._attr_translation_key = f"ev_schedule_slot_{slot_idx}_summary"
        self._attr_unique_id = f"{entry.entry_id}_ev_schedule_slot_{slot_idx}_summary"
        self._attr_device_info = _device_info(entry)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        from homeassistant.helpers.dispatcher import async_dispatcher_connect   # noqa: PLC0415
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, f"{DOMAIN}_schedules_changed",
                self.async_write_ha_state,
            )
        )

    def _slot(self) -> dict | None:
        return self.coordinator.get_schedule_slot(self._slot_idx)

    @property
    def native_value(self) -> str:
        slot = self._slot()
        if slot is None:
            return "empty"
        if not slot.get("enabled"):
            return "disabled"
        if not slot.get("days"):
            return "disabled"
        # Active-now is determined by walking the same logic as
        # _resolve_effective_ev_mode but locally so we can attribute it.
        from datetime import time as _time, datetime as _dt        # noqa: PLC0415
        from .const import EV_SCHEDULE_DAYS                         # noqa: PLC0415
        try:
            from homeassistant.util import dt as _dt_util           # noqa: PLC0415
            now_local = _dt_util.now()
        except Exception:                                           # noqa: BLE001
            now_local = _dt.now()
        cur_t = now_local.time()
        weekday_today = EV_SCHEDULE_DAYS[now_local.weekday()]
        weekday_yesterday = EV_SCHEDULE_DAYS[(now_local.weekday() - 1) % 7]
        def _parse(s):
            try:
                p = (s or "").split(":")
                return _time(int(p[0]), int(p[1]) if len(p) > 1 else 0)
            except (ValueError, IndexError):
                return None
        st = _parse(slot.get("start"))
        en = _parse(slot.get("end"))
        days = slot.get("days") or []
        if st is None or en is None:
            return "idle"
        if st < en:
            if weekday_today in days and st <= cur_t < en:
                return "active"
        elif st > en:
            if weekday_today in days and cur_t >= st:
                return "active"
            if weekday_yesterday in days and cur_t < en:
                return "active"
        return "idle"

    @property
    def extra_state_attributes(self) -> dict:
        from .const import EV_SCHEDULE_DAYS                         # noqa: PLC0415
        slot = self._slot()
        if slot is None:
            return {"slot": self._slot_idx, "empty": True}
        days = slot.get("days") or []
        start_s = (slot.get("start") or "??")[:5]
        end_s = (slot.get("end") or "??")[:5]
        return {
            "slot":     self._slot_idx,
            "enabled":  bool(slot.get("enabled")),
            "mode":     slot.get("mode"),
            "name":     slot.get("name") or f"Skema {self._slot_idx}",
            "start":    slot.get("start"),
            "end":      slot.get("end"),
            "days":     days,
            # Per-day boolean flags so dashboard chips can colour individually
            # without parsing the list. Order matches EV_SCHEDULE_DAYS.
            **{f"day_{d}": (d in days) for d in EV_SCHEDULE_DAYS},
            "summary":  f"{start_s}–{end_s}" if days else "Ingen dage valgt",
        }

