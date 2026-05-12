"""Battery Arbitrage integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN
from .coordinator import BatteryArbitrageCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SWITCH,
]


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
