"""Number platform for Battery Arbitrage — exposes learned charge rates as editable numbers."""
from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    BUY_PRICE_MODE_OCTOPUS,
    BUY_PRICE_MODE_STROMLIGNING,
    CONF_BUY_PRICE_MODE,
    CONF_STROMLIGNING_USE_MANUAL_OVERRIDES,
    DEFAULT_BATTERY_CAPACITY,
    DYNAMIC_FLOOR_RESERVE_FACTOR,
    DEFAULT_BATTERY_DEGRADATION_COST,
    DEFAULT_BATTERY_FLOOR_SOC,
    DEFAULT_DISK_ALARM_THRESHOLD_PCT,
    DEFAULT_BATTERY_MAX_SOC,
    DEFAULT_BUY_PRICE_MODE,
    DEFAULT_ELAFGIFT_DKK_KWH,
    DEFAULT_EV_MIN_CHARGE_KW,
    DEFAULT_EV_MAX_CHARGE_KW,
    DEFAULT_EV_BATTERY_PRIORITY_SOC,
    CONF_EV_CONTROL_INTERVAL_SECONDS,
    DEFAULT_EV_CONTROL_INTERVAL_SECONDS,
    CONF_EV_CHARGER_BACKEND,
    DEFAULT_EV_CHARGER_BACKEND,
    EV_BACKEND_FOXESS_MODBUS,
    EV_MODBUS_UPSHIFT_KW,
    EV_MODBUS_DOWNSHIFT_KW,
    EV_MODBUS_SUSPEND_INTERVAL_MIN,
    EV_OVERRIDE_RAMP_INTERVAL_SECONDS,
    DEFAULT_EXPORT_FEE,
    DEFAULT_MAX_EXPORT_KW,
    DEFAULT_MIN_EXPORT_PRICE,
    DEFAULT_MIN_SPREAD_ARBITRAGE,
    DEFAULT_SOLAR_CONFIDENCE_PCT,
    DEFAULT_SPOT_MARKUP,
    DEFAULT_STROMLIGNING_USE_MANUAL_OVERRIDES,
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
        # v0.58.0 — EV control-loop interval: how often the controller
        # re-evaluates and writes the charger setpoint (both backends). On the
        # Modbus backend this is the effective write/heartbeat cadence; keep it
        # well under the charger's 180 s setpoint-expiry window.
        BatteryArbitrageConfigNumber(
            coordinator, entry,
            storage_key="ev_control_interval_seconds",
            translation_key="ev_control_interval",
            default=int(entry.data.get(
                CONF_EV_CONTROL_INTERVAL_SECONDS, DEFAULT_EV_CONTROL_INTERVAL_SECONDS)),
            icon="mdi:timer-sync-outline",
            unit=UnitOfTime.SECONDS,
            min_val=5,
            max_val=60,
            step=5,
            mode=NumberMode.BOX,
        ),
        BatteryArbitrageConfigNumber(
            coordinator, entry,
            storage_key="disk_alarm_threshold_pct",
            translation_key="disk_alarm_threshold",
            default=DEFAULT_DISK_ALARM_THRESHOLD_PCT,
            icon="mdi:harddisk",
            unit=PERCENTAGE,
            min_val=1,
            max_val=50,
            step=1,
            mode=NumberMode.BOX,
        ),
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
        # v0.60.0 — usable battery capacity, settable from the dashboard (was
        # setup-wizard only). Authoritative over the BMS auto-learner: the value
        # set here is what the optimiser uses. Defaults to the configured value.
        BatteryArbitrageConfigNumber(
            coordinator, entry,
            storage_key="battery_capacity",
            translation_key="battery_capacity",
            default=float(entry.data.get("battery_capacity", DEFAULT_BATTERY_CAPACITY)),
            icon="mdi:battery",
            unit="kWh",
            min_val=3.0,
            max_val=30.0,
            step=0.1,
            mode=NumberMode.BOX,
            display_precision=1,
        ),
        # v0.66.0 — overnight reserve safety factor (the multiplier on the
        # predicted overnight need). Used until the adaptive p80 learner warms
        # up (7 clean nights), then the data takes over. Lower = sell more into
        # peaks; higher = hold more for the night.
        BatteryArbitrageConfigNumber(
            coordinator, entry,
            storage_key="reserve_factor_manual",
            translation_key="reserve_factor_manual",
            default=DYNAMIC_FLOOR_RESERVE_FACTOR,
            icon="mdi:shield-half-full",
            unit="×",
            min_val=1.0,
            max_val=2.0,
            step=0.05,
            mode=NumberMode.BOX,
            display_precision=2,
        ),
        BatteryArbitrageConfigNumber(
            coordinator, entry,
            storage_key="min_spread_arbitrage",
            translation_key="min_spread_arbitrage",
            default=DEFAULT_MIN_SPREAD_ARBITRAGE,
            icon="mdi:chart-bar",
            unit="DKK/kWh",
            min_val=0.00,
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
            # v0.37.1 — slider is greyed out in Strømligning-no-overrides
            # and Octopus modes, where the API price already includes VAT.
            available_when=_manual_buy_component_available,
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
            # v0.37.2 — also greyed out when the API supplies elafgift directly
            # (Strømligning no-overrides; Octopus value_inc_vat).
            available_when=_manual_buy_component_available,
        ),
        BatteryArbitrageConfigNumber(
            coordinator, entry,
            storage_key="spot_markup",
            translation_key="spot_markup",
            default=DEFAULT_SPOT_MARKUP,
            icon="mdi:tag-plus-outline",
            unit="DKK/kWh",
            min_val=0.0,
            max_val=0.50,
            step=0.005,
            mode=NumberMode.BOX,
            # v0.37.2 — also greyed out when the API supplies retailer markup
            # (Strømligning no-overrides; Octopus value_inc_vat).
            available_when=_manual_buy_component_available,
        ),
        BatteryArbitrageConfigNumber(
            coordinator, entry,
            storage_key="max_export_kw",
            translation_key="max_export_kw",
            default=DEFAULT_MAX_EXPORT_KW,
            icon="mdi:transmission-tower-export",
            unit=UnitOfPower.KILO_WATT,
            min_val=0.0,
            max_val=10.0,
            step=0.5,
            mode=NumberMode.BOX,
        ),
        BatteryArbitrageConfigNumber(
            coordinator, entry,
            storage_key="min_export_price",
            translation_key="min_export_price",
            default=DEFAULT_MIN_EXPORT_PRICE,
            icon="mdi:currency-eur-off",
            unit="DKK/kWh",
            min_val=0.0,
            max_val=2.0,
            step=0.01,
            mode=NumberMode.BOX,
            display_precision=2,
        ),
        BatteryArbitrageConfigNumber(
            coordinator, entry,
            storage_key="battery_degradation_cost",
            translation_key="battery_degradation_cost",
            default=DEFAULT_BATTERY_DEGRADATION_COST,
            icon="mdi:battery-heart-variant",
            unit="DKK/kWh",
            min_val=0.0,
            max_val=1.0,
            step=0.01,
            mode=NumberMode.BOX,
            display_precision=2,
        ),
        # EV charge controller min/max (Phase B1)
        BatteryArbitrageConfigNumber(
            coordinator, entry,
            storage_key="ev_min_charge_kw",
            translation_key="ev_min_charge_kw",
            default=DEFAULT_EV_MIN_CHARGE_KW,
            icon="mdi:battery-charging-low",
            unit=UnitOfPower.KILO_WATT,
            min_val=1.4,
            max_val=11.0,
            step=0.1,
            mode=NumberMode.BOX,
            display_precision=2,
        ),
        BatteryArbitrageConfigNumber(
            coordinator, entry,
            storage_key="ev_max_charge_kw",
            translation_key="ev_max_charge_kw",
            default=DEFAULT_EV_MAX_CHARGE_KW,
            icon="mdi:battery-charging-high",
            unit=UnitOfPower.KILO_WATT,
            min_val=1.4,
            max_val=22.0,
            step=0.1,
            mode=NumberMode.BOX,
            display_precision=2,
        ),
        # Battery-priority SoC threshold (v0.26.4) — EV waits until house
        # battery reaches this SoC before consuming solar surplus.
        BatteryArbitrageConfigNumber(
            coordinator, entry,
            storage_key="ev_battery_priority_soc",
            translation_key="ev_battery_priority_soc",
            default=DEFAULT_EV_BATTERY_PRIORITY_SOC,
            icon="mdi:battery-arrow-up",
            unit="%",
            min_val=50,
            max_val=100,
            step=1,
            mode=NumberMode.SLIDER,
            display_precision=0,
        ),
        # Solar confidence (v0.44.0 — S1). Percentile of the per-hour forecast/
        # actual ratio the optimiser plans against. 50 = median (= prior
        # behaviour). Lower = plan against more conservative solar.
        BatteryArbitrageConfigNumber(
            coordinator, entry,
            storage_key="solar_confidence_pct",
            translation_key="solar_confidence_pct",
            default=DEFAULT_SOLAR_CONFIDENCE_PCT,
            icon="mdi:weather-partly-cloudy",
            unit="%",
            min_val=10,
            max_val=90,
            step=5,
            mode=NumberMode.SLIDER,
            display_precision=0,
        ),
        # Three-phase switch-up threshold (v0.59.8) — FoxESS Modbus backend only.
        # The car goes three-phase once the rolling-average solar surplus clears
        # this. Higher = more margin over the 4.14 kW three-phase floor (commits
        # to 3φ only on strong, steady sun; fewer phase switches). Lower = engage
        # three-phase more eagerly at modest surplus (more switches on choppy
        # days). The slider floor (4.3 kW) keeps it above the fixed downshift
        # threshold so the hysteresis band can't invert. Greyed out unless the
        # FoxESS Modbus backend is selected.
        BatteryArbitrageConfigNumber(
            coordinator, entry,
            storage_key="ev_modbus_upshift_kw",
            translation_key="ev_modbus_upshift_kw",
            default=EV_MODBUS_UPSHIFT_KW,
            icon="mdi:sine-wave",
            unit=UnitOfPower.KILO_WATT,
            min_val=round(EV_MODBUS_DOWNSHIFT_KW + 0.1, 1),
            max_val=8.0,
            step=0.1,
            mode=NumberMode.SLIDER,
            display_precision=1,
            available_when=_foxess_modbus_active,
        ),
        # Phase-switch / suspend interval (v0.59.13) — minutes between phase
        # switches. The L11PMC accepts 1 min (verified). Lower = snappier phase
        # response; higher = calmer. FoxESS Modbus backend only.
        BatteryArbitrageConfigNumber(
            coordinator, entry,
            storage_key="ev_modbus_suspend_interval_min",
            translation_key="ev_modbus_suspend_interval_min",
            default=EV_MODBUS_SUSPEND_INTERVAL_MIN,
            icon="mdi:timer-sync-outline",
            unit="min",
            min_val=1,
            max_val=30,
            step=1,
            mode=NumberMode.SLIDER,
            display_precision=0,
            available_when=_foxess_modbus_active,
        ),
        # Override ramp step interval (v0.59.13) — seconds between current
        # up-steps while the battery-full override harvests curtailed PV. Lower =
        # ramps to the PV ceiling faster (but probes the grid more aggressively).
        BatteryArbitrageConfigNumber(
            coordinator, entry,
            storage_key="ev_override_ramp_interval_s",
            translation_key="ev_override_ramp_interval_s",
            default=EV_OVERRIDE_RAMP_INTERVAL_SECONDS,
            icon="mdi:speedometer",
            unit="s",
            min_val=3,
            max_val=60,
            step=1,
            mode=NumberMode.SLIDER,
            display_precision=0,
            available_when=_foxess_modbus_active,
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
        display_precision: int | None = None,
        available_when: "Callable[[BatteryArbitrageCoordinator], bool] | None" = None,
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
        # v0.37.1 — optional callback that returns False to grey out the slider
        # in contexts where its value is ignored by the coordinator (e.g. the
        # VAT slider when buy_price_mode is `stromligning` with no overrides,
        # because Strømligning's `total` field already includes VAT).
        self._available_when = available_when
        # Note: _attr_suggested_display_precision is intentionally NOT set here.
        # HA's compact display entry (list_for_display) only exposes the "dp" field
        # for domain=="sensor" entities.  For number entities, getNumberFormatOptions
        # in the frontend never receives a display_precision value, so trailing zeros
        # cannot be forced via HA's standard entity API.  This is an HA limitation.

    @property
    def available(self) -> bool:
        base = super().available
        if not base:
            return False
        if self._available_when is None:
            return True
        try:
            return bool(self._available_when(self.coordinator))
        except Exception:  # noqa: BLE001
            return True   # fail-open — never make a slider permanently unreachable on a callback bug

    @property
    def native_value(self) -> float:
        return self.coordinator._stored.get(self._storage_key, self._default)

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator._stored[self._storage_key] = round(value, 3)
        await self.coordinator._store.async_save(self.coordinator._stored)
        self.async_write_ha_state()


def _foxess_modbus_active(coordinator: BatteryArbitrageCoordinator) -> bool:
    """Return whether the FoxESS Modbus charger backend is selected.

    The three-phase switch-up threshold only governs the Modbus phase decision;
    on the OCPP backend it has no effect, so grey it out there.
    """
    return (
        coordinator._setting(CONF_EV_CHARGER_BACKEND, DEFAULT_EV_CHARGER_BACKEND)
        == EV_BACKEND_FOXESS_MODBUS
    )


def _manual_buy_component_available(coordinator: BatteryArbitrageCoordinator) -> bool:
    """Return whether the user's manual buy-side component sliders have an
    effect on the buy price.

    The Moms, Elafgift, and Spotpris-tillæg sliders all feed
    `_compute_buy_price`'s `(spot + markup + tariff + elafgift) × vat_factor`
    formula. They're in play in:
      - `manual` mode (always), or
      - `stromligning` mode WITH `use_manual_overrides=True` — the manual
        markup/elafgift/VAT slide is recombined with Strømligning's
        ex-VAT spot/distribution/transmission components.

    They're ignored in:
      - `stromligning` mode without overrides — Strømligning's
        `entry.price.price.total` is taken verbatim, VAT and tariffs
        and retailer markup all baked in already.
      - `octopus` mode (UK) — `value_inc_vat` is taken verbatim.

    Greying the sliders out in the ignored cases makes the dashboard
    honest about which knobs actually control the buy price.
    """
    mode = coordinator.config.get(CONF_BUY_PRICE_MODE, DEFAULT_BUY_PRICE_MODE)
    if mode == BUY_PRICE_MODE_OCTOPUS:
        return False
    if mode == BUY_PRICE_MODE_STROMLIGNING:
        return bool(coordinator.config.get(
            CONF_STROMLIGNING_USE_MANUAL_OVERRIDES,
            DEFAULT_STROMLIGNING_USE_MANUAL_OVERRIDES,
        ))
    return True   # manual mode


# v0.37.1 compatibility alias — the helper was renamed when it grew from
# only-VAT to all-manual-buy-components. Keep the old name pointing at
# the new function so external dashboards / scripts referencing it via
# import-by-name don't break.
_vat_slider_available = _manual_buy_component_available
