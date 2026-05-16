"""Battery Arbitrage integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    CONF_BATTERY_CHARGE_ENTITY,
    CONF_BATTERY_CHARGE_TOTAL_ENTITY,
    CONF_BATTERY_DISCHARGE_ENTITY,
    CONF_BATTERY_DISCHARGE_TOTAL_ENTITY,
    CONF_BATTERY_SOC_ENTITY,
    CONF_CELL_TEMP_ENTITY,
    CONF_CURRENCY,
    CONF_DSO_GLN,
    CONF_FAST_POLL_INTERVAL,
    CONF_SOLAR_FORECAST_SOURCE,
    CONF_LIVE_DATA_SOURCE,
    CONF_SPOT_MARKUP,
    CONF_SPOT_PRICE_ENTITY,
    CONF_STROMLIGNING_ENTITY,
    DOMAIN,
    CONF_BATTERY_CAPACITY,
    CONF_BATTERY_FLOOR_SOC,
    CONF_BATTERY_MAX_SOC,
    CONF_FORECAST_HOURS,
    CONF_MIN_SPREAD_ARBITRAGE,
    CONF_ROUND_TRIP_EFFICIENCY,
    DEFAULT_BATTERY_CAPACITY,
    DEFAULT_BATTERY_FLOOR_SOC,
    DEFAULT_BATTERY_MAX_SOC,
    DEFAULT_CURRENCY,
    DEFAULT_DSO_GLN,
    DEFAULT_FAST_POLL_SECONDS,
    DEFAULT_FORECAST_HOURS,
    DEFAULT_MIN_SPREAD_ARBITRAGE,
    DEFAULT_ROUND_TRIP_EFFICIENCY,
    DEFAULT_SOLAR_FORECAST_SOURCE,
    DEFAULT_LIVE_DATA_SOURCE,
    DEFAULT_SPOT_MARKUP,
    FOXESS_BATTERY_CHARGE_POWER,
    FOXESS_BATTERY_CHARGE_TOTAL,
    FOXESS_BATTERY_DISCHARGE_POWER,
    FOXESS_BATTERY_DISCHARGE_TOTAL,
    FOXESS_BATTERY_SOC,
    FOXESS_CELL_TEMP_LOW,
    STROMLIGNING_SPOTPRICE_EX_VAT,
)
from .coordinator import BatteryArbitrageCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SWITCH,
]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry to the current schema version.

    Called automatically by HA whenever entry.version < ConfigFlow.VERSION.
    Each version block migrates one step and falls through to the next, so
    upgrading multiple versions in a single restart works correctly.

    To add a new migration in future:
      1. Bump VERSION in config_flow.py (e.g. 2 → 3)
      2. Add an `if entry.version < 3:` block below that fills in / renames fields
    """
    _LOGGER.info("Battery Arbitrage: migrating config entry v%s → v%s",
                 entry.version, entry.domain)

    new_data = dict(entry.data)

    if entry.version < 2:
        # v1 → v2: establish a clean baseline with all known fields present.
        # Users who installed at v0.1.0 already had all of these, but any
        # edge-case partial install will be made whole here.
        new_data.setdefault(CONF_BATTERY_CAPACITY,       DEFAULT_BATTERY_CAPACITY)
        new_data.setdefault(CONF_BATTERY_FLOOR_SOC,      DEFAULT_BATTERY_FLOOR_SOC)
        new_data.setdefault(CONF_BATTERY_MAX_SOC,         DEFAULT_BATTERY_MAX_SOC)
        new_data.setdefault(CONF_ROUND_TRIP_EFFICIENCY,   DEFAULT_ROUND_TRIP_EFFICIENCY)
        new_data.setdefault(CONF_MIN_SPREAD_ARBITRAGE,    DEFAULT_MIN_SPREAD_ARBITRAGE)
        new_data.setdefault(CONF_FORECAST_HOURS,          DEFAULT_FORECAST_HOURS)

        hass.config_entries.async_update_entry(entry, data=new_data, version=2)
        _LOGGER.info("Battery Arbitrage: migrated config entry to v2")

    if entry.version < 3:
        # v2 → v3: add currency selector (defaults to DKK for existing installs)
        new_data.setdefault(CONF_CURRENCY, DEFAULT_CURRENCY)
        hass.config_entries.async_update_entry(entry, data=new_data, version=3)
        _LOGGER.info("Battery Arbitrage: migrated config entry to v3")

    if entry.version < 4:
        # v3 → v4: add configurable fast poll interval (defaults to 30 s)
        new_data.setdefault(CONF_FAST_POLL_INTERVAL, DEFAULT_FAST_POLL_SECONDS)
        hass.config_entries.async_update_entry(entry, data=new_data, version=4)
        _LOGGER.info("Battery Arbitrage: migrated config entry to v4")

    if entry.version < 5:
        # v4 → v5: add DSO GLN for tariff schedule fetching (defaults to Dinel)
        new_data.setdefault(CONF_DSO_GLN, DEFAULT_DSO_GLN)
        hass.config_entries.async_update_entry(entry, data=new_data, version=5)
        _LOGGER.info("Battery Arbitrage: migrated config entry to v5")

    if entry.version < 6:
        # v5 → v6: fix old Dinel capacity-charges GLN → correct nettarif C time GLN;
        # also seed the new spot_markup field (retailer's per-kWh margin).
        _OLD_DINEL_CAPACITY_GLN = "5790000610976"
        if new_data.get(CONF_DSO_GLN) == _OLD_DINEL_CAPACITY_GLN:
            new_data[CONF_DSO_GLN] = DEFAULT_DSO_GLN
            _LOGGER.info(
                "Battery Arbitrage: corrected Dinel DSO GLN from %s to %s",
                _OLD_DINEL_CAPACITY_GLN, DEFAULT_DSO_GLN,
            )
        new_data.setdefault(CONF_SPOT_MARKUP, DEFAULT_SPOT_MARKUP)
        hass.config_entries.async_update_entry(entry, data=new_data, version=6)
        _LOGGER.info("Battery Arbitrage: migrated config entry to v6")

    if entry.version < 7:
        # v6 → v7: rename stromligning_entity → spot_price_entity for generic price source
        # support.  Preserves the user's existing entity selection verbatim.
        old_entity = new_data.pop(CONF_STROMLIGNING_ENTITY, None)
        if old_entity:
            new_data[CONF_SPOT_PRICE_ENTITY] = old_entity
            _LOGGER.info(
                "Battery Arbitrage: migrated spot price entity key (%s)", old_entity
            )
        else:
            # Seed with the well-known Strømligning default so existing installs don't break
            new_data.setdefault(CONF_SPOT_PRICE_ENTITY, STROMLIGNING_SPOTPRICE_EX_VAT)
        hass.config_entries.async_update_entry(entry, data=new_data, version=7)
        _LOGGER.info("Battery Arbitrage: migrated config entry to v7")

    if entry.version < 8:
        # v7 → v8: add configurable battery sensor entity IDs.
        # Existing installs get the FoxESS Modbus defaults — zero behaviour change.
        new_data.setdefault(CONF_BATTERY_SOC_ENTITY,             FOXESS_BATTERY_SOC)
        new_data.setdefault(CONF_CELL_TEMP_ENTITY,               FOXESS_CELL_TEMP_LOW)
        new_data.setdefault(CONF_BATTERY_CHARGE_ENTITY,          FOXESS_BATTERY_CHARGE_POWER)
        new_data.setdefault(CONF_BATTERY_DISCHARGE_ENTITY,       FOXESS_BATTERY_DISCHARGE_POWER)
        new_data.setdefault(CONF_BATTERY_CHARGE_TOTAL_ENTITY,    FOXESS_BATTERY_CHARGE_TOTAL)
        new_data.setdefault(CONF_BATTERY_DISCHARGE_TOTAL_ENTITY, FOXESS_BATTERY_DISCHARGE_TOTAL)
        hass.config_entries.async_update_entry(entry, data=new_data, version=8)
        _LOGGER.info("Battery Arbitrage: migrated config entry to v8")

    if entry.version < 9:
        # v8 → v9: add solar forecast source picker. Existing installs keep
        # EVCC as the source so behaviour is unchanged.
        new_data.setdefault(CONF_SOLAR_FORECAST_SOURCE, DEFAULT_SOLAR_FORECAST_SOURCE)
        hass.config_entries.async_update_entry(entry, data=new_data, version=9)
        _LOGGER.info("Battery Arbitrage: migrated config entry to v9")

    if entry.version < 10:
        # v9 → v10: add live data source picker (EVCC / Hybrid / FoxESS).
        # Existing installs keep EVCC as the source so behaviour is unchanged.
        new_data.setdefault(CONF_LIVE_DATA_SOURCE, DEFAULT_LIVE_DATA_SOURCE)
        hass.config_entries.async_update_entry(entry, data=new_data, version=10)
        _LOGGER.info("Battery Arbitrage: migrated config entry to v10")

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Battery Arbitrage from a config entry."""
    coordinator = BatteryArbitrageCoordinator(hass, dict(entry.data))
    await coordinator.async_load_storage()
    await coordinator.async_config_entry_first_refresh()

    # Disable the legacy export-limit automation so it can't fight us over register 46616
    await coordinator.async_disable_legacy_automation()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Register integration services (only once, even with multiple entries)
    _register_services(hass)

    return True


def _register_services(hass: HomeAssistant) -> None:
    """Register Battery Arbitrage services (idempotent)."""
    if hass.services.has_service(DOMAIN, "force_export"):
        return  # already registered

    def _get_coordinator(call: ServiceCall) -> BatteryArbitrageCoordinator | None:
        coordinators = list(hass.data.get(DOMAIN, {}).values())
        return coordinators[0] if coordinators else None

    async def handle_force_export(call: ServiceCall) -> None:
        coordinator = _get_coordinator(call)
        if coordinator:
            await coordinator._transition_to("exporting")
            coordinator._current_mode = "exporting"
            coordinator._mode_reason = "Manually forced via service"

    async def handle_force_grid_charge(call: ServiceCall) -> None:
        coordinator = _get_coordinator(call)
        if coordinator:
            await coordinator._transition_to("grid_charging")
            coordinator._current_mode = "grid_charging"
            coordinator._mode_reason = "Manually forced via service"

    async def handle_restore_normal(call: ServiceCall) -> None:
        coordinator = _get_coordinator(call)
        if coordinator:
            await coordinator.async_restore_normal()

    async def handle_reset_learning(call: ServiceCall) -> None:
        coordinator = _get_coordinator(call)
        if coordinator:
            coordinator.reset_learned_rates()

    hass.services.async_register(DOMAIN, "force_export", handle_force_export)
    hass.services.async_register(DOMAIN, "force_grid_charge", handle_force_grid_charge)
    hass.services.async_register(DOMAIN, "restore_normal", handle_restore_normal)
    hass.services.async_register(DOMAIN, "reset_learning", handle_reset_learning)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Battery Arbitrage config entry — restore HA to normal state."""
    coordinator: BatteryArbitrageCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Restore the legacy automation and inverter/EVCC before unloading
    await coordinator.async_restore_legacy_automation()
    await coordinator.async_restore_normal()

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove stored data when integration is deleted."""
    from homeassistant.helpers.storage import Store
    from .const import STORAGE_KEY, STORAGE_VERSION

    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    await store.async_remove()
    _LOGGER.info("Battery Arbitrage: storage cleaned up")


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle config entry option updates."""
    await hass.config_entries.async_reload(entry.entry_id)
