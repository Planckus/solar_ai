"""Config flow for Battery Arbitrage — the setup wizard."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow, ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector

from .const import (
    CONF_BATTERY_CAPACITY,
    CONF_BATTERY_FLOOR_SOC,
    CONF_BATTERY_MAX_SOC,
    CONF_DASHBOARD_URL_PATH,
    CONF_EVCC_URL,
    CONF_FORECAST_HOURS,
    CONF_FOXESS_FORCE_CHARGE_ENTITY,
    CONF_FOXESS_FORCE_DISCHARGE_ENTITY,
    CONF_FOXESS_INVERTER_ID,
    CONF_FOXESS_WORK_MODE_ENTITY,
    CONF_MIN_SOLAR_EXPORT_PRICE,
    CONF_MIN_SPREAD_ARBITRAGE,
    CONF_ROUND_TRIP_EFFICIENCY,
    CONF_STROMLIGNING_ENTITY,
    DEFAULT_BATTERY_CAPACITY,
    DEFAULT_BATTERY_FLOOR_SOC,
    DEFAULT_BATTERY_MAX_SOC,
    DEFAULT_EVCC_URL,
    DEFAULT_FORECAST_HOURS,
    DEFAULT_MIN_SOLAR_EXPORT_PRICE,
    DEFAULT_MIN_SPREAD_ARBITRAGE,
    DEFAULT_ROUND_TRIP_EFFICIENCY,
    DOMAIN,
    EVCC_API_STATE,
    FOXESS_FORCE_CHARGE_ENTITY,
    FOXESS_FORCE_DISCHARGE_ENTITY,
    FOXESS_WORK_MODE_ENTITY,
    STROMLIGNING_SPOTPRICE_EX_VAT,
)

_LOGGER = logging.getLogger(__name__)


class BatteryArbitrageConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the setup wizard."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: EVCC connection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            evcc_url = user_input[CONF_EVCC_URL].rstrip("/")
            evcc_ok, evcc_data = await self._test_evcc(evcc_url)

            if not evcc_ok:
                errors[CONF_EVCC_URL] = "evcc_unreachable"
            elif not evcc_data.get("battery"):
                errors[CONF_EVCC_URL] = "evcc_no_battery"
            else:
                # Auto-fill battery capacity from EVCC
                capacity = evcc_data["battery"].get("capacity", DEFAULT_BATTERY_CAPACITY)
                self._data.update({
                    CONF_EVCC_URL: evcc_url,
                    CONF_BATTERY_CAPACITY: capacity,
                    "_evcc_data": evcc_data,
                })
                return await self.async_step_foxess()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_EVCC_URL, default=DEFAULT_EVCC_URL): str,
            }),
            errors=errors,
            description_placeholders={"default_url": DEFAULT_EVCC_URL},
        )

    async def async_step_foxess(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: FoxESS inverter entity detection."""
        errors: dict[str, str] = {}

        # Auto-detect FoxESS entities
        detected_work_mode = self._find_entity(FOXESS_WORK_MODE_ENTITY)
        detected_force_charge = self._find_entity(FOXESS_FORCE_CHARGE_ENTITY)
        detected_force_discharge = self._find_entity(FOXESS_FORCE_DISCHARGE_ENTITY)
        detected_inverter_id = self._detect_inverter_id()

        if user_input is not None:
            self._data.update(user_input)

            # Verify entities exist
            missing = []
            for key in [CONF_FOXESS_WORK_MODE_ENTITY, CONF_FOXESS_FORCE_CHARGE_ENTITY,
                         CONF_FOXESS_FORCE_DISCHARGE_ENTITY]:
                eid = user_input.get(key)
                if eid and not self.hass.states.get(eid):
                    missing.append(eid)

            if missing:
                errors["base"] = "entity_not_found"
            else:
                return await self.async_step_stromligning()

        return self.async_show_form(
            step_id="foxess",
            data_schema=vol.Schema({
                vol.Required(CONF_FOXESS_INVERTER_ID,
                             default=detected_inverter_id or ""): str,
                vol.Required(CONF_FOXESS_WORK_MODE_ENTITY,
                             default=detected_work_mode or ""): str,
                vol.Required(CONF_FOXESS_FORCE_CHARGE_ENTITY,
                             default=detected_force_charge or ""): str,
                vol.Required(CONF_FOXESS_FORCE_DISCHARGE_ENTITY,
                             default=detected_force_discharge or ""): str,
            }),
            errors=errors,
        )

    async def async_step_stromligning(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3: Strømligning price entity."""
        errors: dict[str, str] = {}
        detected = self._find_entity(STROMLIGNING_SPOTPRICE_EX_VAT)

        if user_input is not None:
            entity = user_input[CONF_STROMLIGNING_ENTITY]
            if not self.hass.states.get(entity):
                errors[CONF_STROMLIGNING_ENTITY] = "entity_not_found"
            else:
                self._data[CONF_STROMLIGNING_ENTITY] = entity
                return await self.async_step_battery()

        return self.async_show_form(
            step_id="stromligning",
            data_schema=vol.Schema({
                vol.Required(CONF_STROMLIGNING_ENTITY,
                             default=detected or STROMLIGNING_SPOTPRICE_EX_VAT): str,
            }),
            errors=errors,
        )

    async def async_step_battery(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 4: Battery and trading parameters."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_dashboard()

        capacity = self._data.get(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY)

        return self.async_show_form(
            step_id="battery",
            data_schema=vol.Schema({
                vol.Required(CONF_BATTERY_CAPACITY, default=capacity): vol.Coerce(float),
                vol.Required(CONF_BATTERY_FLOOR_SOC, default=DEFAULT_BATTERY_FLOOR_SOC):
                    vol.All(int, vol.Range(min=10, max=90)),
                vol.Required(CONF_BATTERY_MAX_SOC, default=DEFAULT_BATTERY_MAX_SOC):
                    vol.All(int, vol.Range(min=50, max=100)),
                vol.Required(CONF_ROUND_TRIP_EFFICIENCY, default=int(DEFAULT_ROUND_TRIP_EFFICIENCY * 100)):
                    vol.All(int, vol.Range(min=70, max=100)),
                vol.Required(CONF_MIN_SPREAD_ARBITRAGE, default=DEFAULT_MIN_SPREAD_ARBITRAGE):
                    vol.Coerce(float),
                vol.Required(CONF_MIN_SOLAR_EXPORT_PRICE, default=DEFAULT_MIN_SOLAR_EXPORT_PRICE):
                    vol.Coerce(float),
                vol.Required(CONF_FORECAST_HOURS, default=DEFAULT_FORECAST_HOURS):
                    vol.All(int, vol.Range(min=4, max=48)),
            }),
        )

    async def async_step_dashboard(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 5: Optional dashboard integration."""
        if user_input is not None:
            dashboard_path = user_input.get(CONF_DASHBOARD_URL_PATH, "")
            self._data[CONF_DASHBOARD_URL_PATH] = dashboard_path

            # Normalise efficiency: stored as 0.0–1.0
            eff = self._data.get(CONF_ROUND_TRIP_EFFICIENCY, 92)
            if eff > 1:
                self._data[CONF_ROUND_TRIP_EFFICIENCY] = eff / 100

            # Clean internal keys
            self._data.pop("_evcc_data", None)

            return self.async_create_entry(
                title="Solar AI",
                data=self._data,
            )

        # Build list of available Lovelace dashboards
        dashboards = await self._list_dashboards()

        return self.async_show_form(
            step_id="dashboard",
            data_schema=vol.Schema({
                vol.Optional(CONF_DASHBOARD_URL_PATH, default=""): vol.In(
                    [""] + [d["url_path"] for d in dashboards]
                ) if dashboards else str,
            }),
            description_placeholders={
                "dashboards": ", ".join(d["title"] for d in dashboards) or "none found"
            },
        )

    # ------------------------------------------------------------------ #
    # Helpers                                                               #
    # ------------------------------------------------------------------ #

    async def _test_evcc(self, url: str) -> tuple[bool, dict]:
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                f"{url}{EVCC_API_STATE}",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    return True, await resp.json()
        except Exception:
            pass
        return False, {}

    def _find_entity(self, entity_id: str) -> str | None:
        state = self.hass.states.get(entity_id)
        return entity_id if state is not None else None

    def _detect_inverter_id(self) -> str | None:
        """Try to find the FoxESS inverter ID from existing Modbus entities."""
        for state in self.hass.states.async_all("select"):
            if "foxessmodbus_work_mode" in state.entity_id:
                # Grab from a known automation if present
                break
        # Fall back to known value — user can correct in form
        return "0c6d23d42d87264a4f0a0dccb6061b12"

    async def _list_dashboards(self) -> list[dict]:
        """Return list of Lovelace dashboards via WebSocket."""
        try:
            from homeassistant.components.lovelace import dashboard as lovelace
            dashboards = await self.hass.components.lovelace.async_get_dashboards()
            return [{"title": d.config.get("title", d.url_path), "url_path": d.url_path}
                    for d in dashboards]
        except Exception:
            return []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BatteryArbitrageOptionsFlow(config_entry)


class BatteryArbitrageOptionsFlow(OptionsFlow):
    """Allow editing battery/trading parameters after setup."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            eff = user_input.get(CONF_ROUND_TRIP_EFFICIENCY, 92)
            if eff > 1:
                user_input[CONF_ROUND_TRIP_EFFICIENCY] = eff / 100
            return self.async_create_entry(title="", data=user_input)

        data = self._entry.data
        eff_pct = int(data.get(CONF_ROUND_TRIP_EFFICIENCY, 0.92) * 100)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_BATTERY_FLOOR_SOC,
                             default=data.get(CONF_BATTERY_FLOOR_SOC, DEFAULT_BATTERY_FLOOR_SOC)):
                    vol.All(int, vol.Range(min=10, max=90)),
                vol.Required(CONF_BATTERY_MAX_SOC,
                             default=data.get(CONF_BATTERY_MAX_SOC, DEFAULT_BATTERY_MAX_SOC)):
                    vol.All(int, vol.Range(min=50, max=100)),
                vol.Required(CONF_ROUND_TRIP_EFFICIENCY, default=eff_pct):
                    vol.All(int, vol.Range(min=70, max=100)),
                vol.Required(CONF_MIN_SPREAD_ARBITRAGE,
                             default=data.get(CONF_MIN_SPREAD_ARBITRAGE, DEFAULT_MIN_SPREAD_ARBITRAGE)):
                    vol.Coerce(float),
                vol.Required(CONF_MIN_SOLAR_EXPORT_PRICE,
                             default=data.get(CONF_MIN_SOLAR_EXPORT_PRICE, DEFAULT_MIN_SOLAR_EXPORT_PRICE)):
                    vol.Coerce(float),
                vol.Required(CONF_FORECAST_HOURS,
                             default=data.get(CONF_FORECAST_HOURS, DEFAULT_FORECAST_HOURS)):
                    vol.All(int, vol.Range(min=4, max=48)),
            }),
        )
