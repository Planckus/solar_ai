"""Select platform — EV charge controller mode picker (Phase B1) + amp/default-mode pickers (v0.27.0)."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    EV_MODE_LOCKED,
    EV_MODE_PV,
    EV_MODE_PV_BATTERY,
    EV_MODE_FULL,
    EV_VOLTAGE,
    EV_PHASES,
    EV_OCPP_MIN_AMPS,
    EV_OCPP_MAX_AMPS,
    DEFAULT_EV_MIN_CHARGE_KW,
    DEFAULT_EV_MAX_CHARGE_KW,
    DEFAULT_EV_DEFAULT_MODE,
    CONF_EV_DEFAULT_MODE,
)
from .coordinator import BatteryArbitrageCoordinator
from .sensor import _device_info


EV_MODES = [EV_MODE_LOCKED, EV_MODE_PV, EV_MODE_PV_BATTERY, EV_MODE_FULL]


# Build amp options as raw integer-strings ("6", "7", ..., "16") — translated
# UI labels render with the kW equivalent (e.g. "6 A (4.14 kW)") via the
# translation file. Storing as integer strings keeps the storage format simple.
AMP_OPTIONS = [str(a) for a in range(EV_OCPP_MIN_AMPS, EV_OCPP_MAX_AMPS + 1)]


def _amps_to_kw(amps: int) -> float:
    """3-phase: P = √3 × V_LL × I = V_phase × phases × I = 230 × 3 × A / 1000."""
    return round(amps * EV_VOLTAGE * EV_PHASES / 1000.0, 2)


def _kw_to_amps(kw: float) -> int:
    """Round to the nearest whole amp, clamped to OCPP min/max."""
    amps = round(kw * 1000.0 / (EV_VOLTAGE * EV_PHASES))
    return max(EV_OCPP_MIN_AMPS, min(EV_OCPP_MAX_AMPS, amps))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EV-related select entities."""
    coordinator: BatteryArbitrageCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        BatteryArbitrageEvModeSelect(coordinator, entry),
        BatteryArbitrageEvMinAmpsSelect(coordinator, entry),
        BatteryArbitrageEvMaxAmpsSelect(coordinator, entry),
        BatteryArbitrageEvDefaultModeSelect(coordinator, entry),
    ])


class BatteryArbitrageEvModeSelect(
    CoordinatorEntity[BatteryArbitrageCoordinator], SelectEntity
):
    """Live EV mode picker — drives Solar AI's 4-mode EV charge controller.

    The four options are:
      - locked        → no charging
      - pv            → solar surplus only; stops if surplus < min
      - pv_battery    → solar first; battery covers gap to reach min; no grid
      - full          → max charge rate regardless of source mix
    """

    _attr_has_entity_name = True
    _attr_translation_key = "ev_mode"
    _attr_icon = "mdi:car-electric"
    _attr_options = EV_MODES

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_ev_mode"
        self._attr_device_info = _device_info(entry)

    @property
    def current_option(self) -> str | None:
        return self.coordinator._ev_active_mode

    async def async_select_option(self, option: str) -> None:
        if option not in EV_MODES:
            return
        self.coordinator.set_ev_mode(option)
        self.async_write_ha_state()


class _AmpsSelectBase(
    CoordinatorEntity[BatteryArbitrageCoordinator], SelectEntity
):
    """Common base for the min/max amp dropdowns (v0.27.0).

    Options are whole amps (6 A → 16 A) that map to 3-phase kW via the
    standard Danish wye: P = 230 V × 3 phases × A / 1000. The display
    label includes both A and kW for user clarity.
    """

    _attr_has_entity_name = True
    _attr_options = AMP_OPTIONS

    # Subclasses set:
    #   _storage_key: e.g. "ev_min_charge_kw"
    #   _default_kw:  fallback when nothing in storage
    _storage_key: str = ""
    _default_kw: float = 0.0

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"
        self._attr_device_info = _device_info(entry)

    @property
    def current_option(self) -> str | None:
        kw = float(self.coordinator._stored.get(self._storage_key, self._default_kw))
        return str(_kw_to_amps(kw))

    async def async_select_option(self, option: str) -> None:
        try:
            amps = int(option)
        except ValueError:
            return
        kw = _amps_to_kw(amps)
        # Round to 2 decimals (matches DEFAULT_EV_MIN_CHARGE_KW format)
        self.coordinator._stored[self._storage_key] = kw
        # Persist so it survives HA restart
        if self.coordinator.hass:
            self.coordinator.hass.async_create_task(
                self.coordinator._store.async_save(self.coordinator._stored)
            )
        self.async_write_ha_state()


class BatteryArbitrageEvMinAmpsSelect(_AmpsSelectBase):
    """Minimum charge rate dropdown (whole amps, 6–16 A on 3-phase Danish wye).

    Replaces the slider-based number entity for picking a clean amp value
    (6, 7, 8, ... 16 A) instead of a continuous kW slider that the OCPP
    integration would round to the nearest amp anyway.
    """

    _attr_translation_key = "ev_min_amps"
    _attr_icon = "mdi:battery-charging-low"
    _storage_key = "ev_min_charge_kw"
    _default_kw = DEFAULT_EV_MIN_CHARGE_KW

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry, "ev_min_amps")


class BatteryArbitrageEvMaxAmpsSelect(_AmpsSelectBase):
    """Maximum charge rate dropdown (whole amps, 6–16 A on 3-phase Danish wye)."""

    _attr_translation_key = "ev_max_amps"
    _attr_icon = "mdi:battery-charging-high"
    _storage_key = "ev_max_charge_kw"
    _default_kw = DEFAULT_EV_MAX_CHARGE_KW

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry, "ev_max_amps")


class BatteryArbitrageEvDefaultModeSelect(
    CoordinatorEntity[BatteryArbitrageCoordinator], SelectEntity
):
    """Default EV mode applied when a vehicle plugs in fresh (v0.27.0).

    Previously this was only configurable in the OptionsFlow's OCPP Settings
    step. Now exposed as a live select entity on the dashboard so users can
    flip it without re-running the OptionsFlow.

    Stored in `_stored["ev_default_mode"]` with fallback to the config-entry
    value for installs that haven't touched the dashboard widget yet.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "ev_default_mode"
    _attr_icon = "mdi:car-connected"
    _attr_options = EV_MODES

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_ev_default_mode"
        self._attr_device_info = _device_info(entry)
        self._entry = entry

    @property
    def current_option(self) -> str | None:
        return self.coordinator._stored.get(
            "ev_default_mode",
            self._entry.data.get(CONF_EV_DEFAULT_MODE, DEFAULT_EV_DEFAULT_MODE),
        )

    async def async_select_option(self, option: str) -> None:
        if option not in EV_MODES:
            return
        self.coordinator._stored["ev_default_mode"] = option
        if self.coordinator.hass:
            self.coordinator.hass.async_create_task(
                self.coordinator._store.async_save(self.coordinator._stored)
            )
        self.async_write_ha_state()
