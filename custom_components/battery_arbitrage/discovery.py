"""Device-registry-aware entity discovery for FoxESS Modbus installs.

The HA entity registry tags every entity with a stable `unique_id` set by
the integration that owns it. For FoxESS Modbus the format is:

    foxess_modbus_<inverter_name>_<register_name>

(e.g. `foxess_modbus_FoxessModbus_battery_soc_1`)

Matching by the trailing `<register_name>` is far more robust than
hard-coding entity IDs:

  - Survives user-driven entity renames (which only change entity_id, not unique_id)
  - Works with multi-inverter installs (matches the first one; can be extended later)
  - Works with non-English HA language packs
  - Survives integration upgrades that re-prefix entity IDs

The discovery functions fall back to None when nothing is found — the
calling config_flow then either uses a stored value, prompts the user, or
shows an EntitySelector dropdown.
"""
from __future__ import annotations

from typing import Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er


# ─────────────────────────────────────────────────────────────────────────
# Core helpers
# ─────────────────────────────────────────────────────────────────────────

def _foxess_entities(hass: HomeAssistant) -> list:
    """Return all entity registry entries owned by the foxess_modbus platform."""
    return [
        e for e in er.async_get(hass).entities.values()
        if e.platform == "foxess_modbus"
    ]


def has_foxess_modbus(hass: HomeAssistant) -> bool:
    """True if the FoxESS Modbus integration is installed and has registered
    entities. This is Solar AI's hard prerequisite — without a FoxESS inverter
    to read and control there is nothing to configure. The config flow uses
    this to abort early with a clear message instead of dropping the user into
    blank entity-picker screens.
    """
    return bool(_foxess_entities(hass))


def _by_uid_suffix(hass: HomeAssistant, *suffixes: str) -> Optional[str]:
    """Find the first foxess_modbus entity whose `unique_id` ends with any of
    the provided suffixes (tried in order, so the most-preferred match wins).

    Returns the entity_id, or None if nothing matched.
    """
    entities = _foxess_entities(hass)
    for suffix in suffixes:
        for e in entities:
            if e.unique_id and e.unique_id.endswith(suffix):
                return e.entity_id
    return None


def _any_by_name(hass: HomeAssistant, *fragments: str) -> Optional[str]:
    """Find any sensor (across all platforms) whose entity_id contains any of
    the provided fragments. Used as a last-resort fallback for entities not
    owned by foxess_modbus itself (e.g. derived/template sensors).
    """
    for fragment in fragments:
        for entity_id in hass.states.async_entity_ids("sensor"):
            if fragment in entity_id:
                return entity_id
    return None


# ─────────────────────────────────────────────────────────────────────────
# Per-purpose discovery
# ─────────────────────────────────────────────────────────────────────────

def discover_battery_soc(hass: HomeAssistant) -> Optional[str]:
    """Primary battery SoC sensor."""
    return _by_uid_suffix(hass, "_battery_soc_1", "_battery_soc")


def discover_bms_kwh_remaining(hass: HomeAssistant) -> list[str]:
    """All per-module BMS 'kWh remaining' sensors, in module order.

    FoxESS exposes one per installed battery module
    (`..._bms_kwh_remaining_1`, `..._bms_kwh_remaining_2`, …). Used to
    auto-detect usable pack capacity. Returns an empty list if none found
    (caller falls back to the well-known IDs in const.FOXESS_BMS_KWH_REMAINING).
    """
    found: list[tuple[int, str]] = []
    for e in _foxess_entities(hass):
        uid = e.unique_id or ""
        marker = "_bms_kwh_remaining_"
        idx = uid.rfind(marker)
        if idx == -1:
            continue
        suffix = uid[idx + len(marker):]
        if suffix.isdigit():
            found.append((int(suffix), e.entity_id))
    return [entity_id for _, entity_id in sorted(found)]


def discover_cell_temp_low(hass: HomeAssistant) -> Optional[str]:
    """Lowest BMS cell temperature sensor (for temperature-adaptive charging)."""
    return _by_uid_suffix(
        hass, "_bms_cell_temp_low_1", "_bms_cell_temp_low", "_battery_temp_1",
    )


def discover_battery_charge_power(hass: HomeAssistant) -> Optional[str]:
    """Live battery charge power (kW). Prefer the combined sensor, fall back to PV1's BMS."""
    return _by_uid_suffix(hass, "_battery_charge", "_battery_charge_1")


def discover_battery_discharge_power(hass: HomeAssistant) -> Optional[str]:
    """Live battery discharge power (kW)."""
    return _by_uid_suffix(hass, "_battery_discharge", "_battery_discharge_1")


def discover_battery_charge_total(hass: HomeAssistant) -> Optional[str]:
    """Lifetime charge total (kWh), used to auto-detect round-trip efficiency."""
    return _by_uid_suffix(hass, "_battery_charge_total")


def discover_battery_discharge_total(hass: HomeAssistant) -> Optional[str]:
    """Lifetime discharge total (kWh)."""
    return _by_uid_suffix(hass, "_battery_discharge_total")


def discover_grid_import(hass: HomeAssistant) -> Optional[str]:
    """Grid import (consumption) power (kW). Always positive when importing.
    Used in FoxESS-only and Hybrid live-data modes."""
    return _by_uid_suffix(hass, "_grid_consumption")


def discover_grid_export(hass: HomeAssistant) -> Optional[str]:
    """Grid export (feed-in) power (kW). Always positive when exporting."""
    return _by_uid_suffix(hass, "_feed_in")


def discover_load_power(hass: HomeAssistant) -> Optional[str]:
    """Live house load power (kW)."""
    return _by_uid_suffix(hass, "_load_power")


def discover_pv_power(hass: HomeAssistant) -> Optional[str]:
    """Live PV power.

    Three strategies in order of preference:
      1. A user-created combined sensor (e.g. `sensor.pv_power_foxessmodbus`)
         that sums PV1 + PV2. Users with multi-MPPT setups often have this.
      2. The integration's own PV1 power sensor (single-MPPT installs).
      3. None — caller falls back to defaults or prompts the user.
    """
    combined = _any_by_name(hass, "pv_power_foxess", "foxess_pv_power_combined")
    if combined:
        return combined
    return _by_uid_suffix(hass, "_pv1_power", "_pv_power")


def discover_work_mode_select(hass: HomeAssistant) -> Optional[str]:
    """Inverter work-mode select entity (Self Use / Feed-in First / Force Charge)."""
    return _by_uid_suffix(hass, "_work_mode")


def discover_force_charge_power(hass: HomeAssistant) -> Optional[str]:
    """Number entity controlling the Force Charge wattage."""
    return _by_uid_suffix(hass, "_force_charge_power")


def discover_force_discharge_power(hass: HomeAssistant) -> Optional[str]:
    """Number entity controlling the Force Discharge wattage (export power cap)."""
    return _by_uid_suffix(hass, "_force_discharge_power")


def discover_inverter_id(hass: HomeAssistant) -> Optional[str]:
    """Infer the inverter ID from a known unique_id pattern.

    FoxESS Modbus stores it as the middle component of the unique_id:
        foxess_modbus_<INVERTER_ID>_<register>
    We extract it from the first matching entity. If no inverter is found,
    return None (caller must prompt).
    """
    for e in _foxess_entities(hass):
        if not e.unique_id:
            continue
        # unique_id format: foxess_modbus_<id>_<register>
        # Split off the prefix and trailing register name
        parts = e.unique_id.split("_")
        if len(parts) >= 4 and parts[0] == "foxess" and parts[1] == "modbus":
            # parts[2] is the inverter ID (e.g. "FoxessModbus" in this install)
            return parts[2]
    return None


# ─────────────────────────────────────────────────────────────────────────
# Bulk discovery
# ─────────────────────────────────────────────────────────────────────────

def discover_all(hass: HomeAssistant) -> dict[str, Optional[str]]:
    """Run every discovery in one call. Returns a dict keyed by CONF_* names.
    Values are entity_ids or None where nothing was found.
    """
    # Local imports to avoid circulars at module load time
    from .const import (
        CONF_BATTERY_SOC_ENTITY,
        CONF_CELL_TEMP_ENTITY,
        CONF_BATTERY_CHARGE_ENTITY,
        CONF_BATTERY_DISCHARGE_ENTITY,
        CONF_BATTERY_CHARGE_TOTAL_ENTITY,
        CONF_BATTERY_DISCHARGE_TOTAL_ENTITY,
        CONF_FOXESS_GRID_IMPORT_ENTITY,
        CONF_FOXESS_GRID_EXPORT_ENTITY,
        CONF_FOXESS_LOAD_POWER_ENTITY,
        CONF_FOXESS_PV_POWER_ENTITY,
        CONF_FOXESS_WORK_MODE_ENTITY,
        CONF_FOXESS_FORCE_CHARGE_ENTITY,
        CONF_FOXESS_FORCE_DISCHARGE_ENTITY,
        CONF_FOXESS_INVERTER_ID,
    )
    return {
        CONF_BATTERY_SOC_ENTITY: discover_battery_soc(hass),
        CONF_CELL_TEMP_ENTITY: discover_cell_temp_low(hass),
        CONF_BATTERY_CHARGE_ENTITY: discover_battery_charge_power(hass),
        CONF_BATTERY_DISCHARGE_ENTITY: discover_battery_discharge_power(hass),
        CONF_BATTERY_CHARGE_TOTAL_ENTITY: discover_battery_charge_total(hass),
        CONF_BATTERY_DISCHARGE_TOTAL_ENTITY: discover_battery_discharge_total(hass),
        CONF_FOXESS_GRID_IMPORT_ENTITY: discover_grid_import(hass),
        CONF_FOXESS_GRID_EXPORT_ENTITY: discover_grid_export(hass),
        CONF_FOXESS_LOAD_POWER_ENTITY: discover_load_power(hass),
        CONF_FOXESS_PV_POWER_ENTITY: discover_pv_power(hass),
        CONF_FOXESS_WORK_MODE_ENTITY: discover_work_mode_select(hass),
        CONF_FOXESS_FORCE_CHARGE_ENTITY: discover_force_charge_power(hass),
        CONF_FOXESS_FORCE_DISCHARGE_ENTITY: discover_force_discharge_power(hass),
        CONF_FOXESS_INVERTER_ID: discover_inverter_id(hass),
    }
