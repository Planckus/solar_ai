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
    CONF_BATTERY_CHARGE_ENTITY,
    CONF_BATTERY_CHARGE_TOTAL_ENTITY,
    CONF_BATTERY_DISCHARGE_ENTITY,
    CONF_BATTERY_DISCHARGE_TOTAL_ENTITY,
    CONF_BATTERY_FLOOR_SOC,
    CONF_BATTERY_MAX_SOC,
    CONF_BATTERY_SOC_ENTITY,
    CONF_CELL_TEMP_ENTITY,
    CONF_CURRENCY,
    CONF_DASHBOARD_URL_PATH,
    CONF_DSO_GLN,
    CONF_EVCC_URL,
    CONF_FAST_POLL_INTERVAL,
    CONF_FORECAST_HOURS,
    CONF_FOXESS_FORCE_CHARGE_ENTITY,
    CONF_FOXESS_FORCE_DISCHARGE_ENTITY,
    CONF_FOXESS_INVERTER_ID,
    CONF_FOXESS_WORK_MODE_ENTITY,
    CONF_MIN_SOLAR_EXPORT_PRICE,
    CONF_MIN_SPREAD_ARBITRAGE,
    CONF_ROUND_TRIP_EFFICIENCY,
    CONF_SPOT_PRICE_ENTITY,
    DEFAULT_BATTERY_CAPACITY,
    DEFAULT_BATTERY_FLOOR_SOC,
    DEFAULT_BATTERY_MAX_SOC,
    DEFAULT_CURRENCY,
    DEFAULT_DSO_GLN,
    DEFAULT_EVCC_URL,
    DEFAULT_FAST_POLL_SECONDS,
    DEFAULT_FORECAST_HOURS,
    DEFAULT_MIN_SOLAR_EXPORT_PRICE,
    DEFAULT_MIN_SPREAD_ARBITRAGE,
    DEFAULT_ROUND_TRIP_EFFICIENCY,
    DOMAIN,
    DSO_OPTIONS,
    EVCC_API_STATE,
    FOXESS_BATTERY_CHARGE_POWER,
    FOXESS_BATTERY_CHARGE_TOTAL,
    FOXESS_BATTERY_DISCHARGE_POWER,
    FOXESS_BATTERY_DISCHARGE_TOTAL,
    FOXESS_BATTERY_SOC,
    FOXESS_CELL_TEMP_LOW,
    FOXESS_FORCE_CHARGE_ENTITY,
    FOXESS_FORCE_DISCHARGE_ENTITY,
    FOXESS_WORK_MODE_ENTITY,
    STROMLIGNING_SPOTPRICE_EX_VAT,  # used as the default entity ID hint
)

_LOGGER = logging.getLogger(__name__)


class BatteryArbitrageConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the setup wizard."""

    VERSION = 8

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
        """Step 2: Inverter control entities."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_battery_sensors()

        detected_inverter_id = self._detect_inverter_id()
        detected_work_mode = self._find_entity(FOXESS_WORK_MODE_ENTITY)
        detected_force_charge = self._find_entity(FOXESS_FORCE_CHARGE_ENTITY)
        detected_force_discharge = self._find_entity(FOXESS_FORCE_DISCHARGE_ENTITY)

        return self.async_show_form(
            step_id="foxess",
            data_schema=vol.Schema({
                vol.Required(CONF_FOXESS_INVERTER_ID,
                             default=detected_inverter_id or ""): str,
                vol.Required(CONF_FOXESS_WORK_MODE_ENTITY,
                             default=detected_work_mode or FOXESS_WORK_MODE_ENTITY):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="select")),
                vol.Required(CONF_FOXESS_FORCE_CHARGE_ENTITY,
                             default=detected_force_charge or FOXESS_FORCE_CHARGE_ENTITY):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="number")),
                vol.Required(CONF_FOXESS_FORCE_DISCHARGE_ENTITY,
                             default=detected_force_discharge or FOXESS_FORCE_DISCHARGE_ENTITY):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="number")),
            }),
        )

    async def async_step_battery_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3: Battery sensor entities."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_spot_price()

        return self.async_show_form(
            step_id="battery_sensors",
            data_schema=vol.Schema({
                vol.Required(CONF_BATTERY_SOC_ENTITY,
                             default=self._find_entity(FOXESS_BATTERY_SOC) or FOXESS_BATTERY_SOC):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Required(CONF_CELL_TEMP_ENTITY,
                             default=self._find_entity(FOXESS_CELL_TEMP_LOW) or FOXESS_CELL_TEMP_LOW):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Required(CONF_BATTERY_CHARGE_ENTITY,
                             default=self._find_entity(FOXESS_BATTERY_CHARGE_POWER) or FOXESS_BATTERY_CHARGE_POWER):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Required(CONF_BATTERY_DISCHARGE_ENTITY,
                             default=self._find_entity(FOXESS_BATTERY_DISCHARGE_POWER) or FOXESS_BATTERY_DISCHARGE_POWER):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Required(CONF_BATTERY_CHARGE_TOTAL_ENTITY,
                             default=self._find_entity(FOXESS_BATTERY_CHARGE_TOTAL) or FOXESS_BATTERY_CHARGE_TOTAL):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Required(CONF_BATTERY_DISCHARGE_TOTAL_ENTITY,
                             default=self._find_entity(FOXESS_BATTERY_DISCHARGE_TOTAL) or FOXESS_BATTERY_DISCHARGE_TOTAL):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            }),
        )

    async def async_step_spot_price(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 4: Generic spot price entity (excl. VAT, in local currency/kWh).

        Accepts any HA sensor — Strømligning, Tibber, or any compatible source.
        """
        if user_input is not None:
            self._data[CONF_SPOT_PRICE_ENTITY] = user_input[CONF_SPOT_PRICE_ENTITY]
            return await self.async_step_battery()

        detected = self._find_entity(STROMLIGNING_SPOTPRICE_EX_VAT)

        return self.async_show_form(
            step_id="spot_price",
            data_schema=vol.Schema({
                vol.Required(CONF_SPOT_PRICE_ENTITY,
                             default=detected or STROMLIGNING_SPOTPRICE_EX_VAT):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            }),
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
                vol.Required(CONF_FORECAST_HOURS, default=DEFAULT_FORECAST_HOURS):
                    vol.All(int, vol.Range(min=4, max=48)),
                vol.Required(CONF_CURRENCY, default=DEFAULT_CURRENCY): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["DKK", "EUR", "SEK", "NOK", "GBP", "USD", "AUD"],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_FAST_POLL_INTERVAL, default=DEFAULT_FAST_POLL_SECONDS):
                    vol.All(int, vol.Range(min=10, max=300)),
                vol.Required(CONF_DSO_GLN, default=DEFAULT_DSO_GLN): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": dso["value"], "label": dso["label"]}
                            for dso in DSO_OPTIONS
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
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
    """Allow editing battery/trading parameters and entity mappings after setup."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._data: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: Battery & trading parameters."""
        if user_input is not None:
            eff = user_input.get(CONF_ROUND_TRIP_EFFICIENCY, 92)
            if eff > 1:
                user_input[CONF_ROUND_TRIP_EFFICIENCY] = eff / 100
            self._data.update(user_input)
            return await self.async_step_entities()

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
                vol.Required(CONF_FORECAST_HOURS,
                             default=data.get(CONF_FORECAST_HOURS, DEFAULT_FORECAST_HOURS)):
                    vol.All(int, vol.Range(min=4, max=48)),
                vol.Required(CONF_CURRENCY,
                             default=data.get(CONF_CURRENCY, DEFAULT_CURRENCY)):
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=["DKK", "EUR", "SEK", "NOK", "GBP", "USD", "AUD"],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                vol.Required(CONF_FAST_POLL_INTERVAL,
                             default=data.get(CONF_FAST_POLL_INTERVAL, DEFAULT_FAST_POLL_SECONDS)):
                    vol.All(int, vol.Range(min=10, max=300)),
                vol.Required(CONF_DSO_GLN,
                             default=data.get(CONF_DSO_GLN, DEFAULT_DSO_GLN)):
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": dso["value"], "label": dso["label"]}
                                for dso in DSO_OPTIONS
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
            }),
        )

    async def async_step_entities(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: Entity mappings — inverter controls and battery sensors."""
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title="", data=self._data)

        data = self._entry.data

        return self.async_show_form(
            step_id="entities",
            data_schema=vol.Schema({
                vol.Required(CONF_FOXESS_INVERTER_ID,
                             default=data.get(CONF_FOXESS_INVERTER_ID, "")):
                    str,
                vol.Required(CONF_FOXESS_WORK_MODE_ENTITY,
                             default=data.get(CONF_FOXESS_WORK_MODE_ENTITY, FOXESS_WORK_MODE_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="select")),
                vol.Required(CONF_FOXESS_FORCE_CHARGE_ENTITY,
                             default=data.get(CONF_FOXESS_FORCE_CHARGE_ENTITY, FOXESS_FORCE_CHARGE_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="number")),
                vol.Required(CONF_FOXESS_FORCE_DISCHARGE_ENTITY,
                             default=data.get(CONF_FOXESS_FORCE_DISCHARGE_ENTITY, FOXESS_FORCE_DISCHARGE_ENTITY)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="number")),
                vol.Required(CONF_BATTERY_SOC_ENTITY,
                             default=data.get(CONF_BATTERY_SOC_ENTITY, FOXESS_BATTERY_SOC)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Required(CONF_CELL_TEMP_ENTITY,
                             default=data.get(CONF_CELL_TEMP_ENTITY, FOXESS_CELL_TEMP_LOW)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Required(CONF_BATTERY_CHARGE_ENTITY,
                             default=data.get(CONF_BATTERY_CHARGE_ENTITY, FOXESS_BATTERY_CHARGE_POWER)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Required(CONF_BATTERY_DISCHARGE_ENTITY,
                             default=data.get(CONF_BATTERY_DISCHARGE_ENTITY, FOXESS_BATTERY_DISCHARGE_POWER)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Required(CONF_BATTERY_CHARGE_TOTAL_ENTITY,
                             default=data.get(CONF_BATTERY_CHARGE_TOTAL_ENTITY, FOXESS_BATTERY_CHARGE_TOTAL)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Required(CONF_BATTERY_DISCHARGE_TOTAL_ENTITY,
                             default=data.get(CONF_BATTERY_DISCHARGE_TOTAL_ENTITY, FOXESS_BATTERY_DISCHARGE_TOTAL)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            }),
        )
