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
    CONF_FORECAST_SOLAR_ENTITY,
    CONF_FOXESS_FORCE_CHARGE_ENTITY,
    CONF_FOXESS_FORCE_DISCHARGE_ENTITY,
    CONF_FOXESS_INVERTER_ID,
    CONF_FOXESS_WORK_MODE_ENTITY,
    CONF_MIN_SPREAD_ARBITRAGE,
    CONF_ROUND_TRIP_EFFICIENCY,
    CONF_SOLAR_FORECAST_SOURCE,
    CONF_SOLCAST_ENTITY,
    CONF_SOLCAST_TOMORROW_ENTITY,
    CONF_LIVE_DATA_SOURCE,
    CONF_FOXESS_GRID_IMPORT_ENTITY,
    CONF_FOXESS_GRID_EXPORT_ENTITY,
    CONF_FOXESS_PV_POWER_ENTITY,
    CONF_FOXESS_LOAD_POWER_ENTITY,
    CONF_ACKNOWLEDGE_NO_EV,
    CONF_EV_CONTROLLER_ENABLED,
    CONF_EV_OCPP_CHARGE_POINT_ID,
    CONF_EV_OCPP_STATUS_ENTITY,
    CONF_EV_OCPP_POWER_ENTITY,
    CONF_EV_DEFAULT_MODE,
    CONF_EV_CONTROL_INTERVAL_SECONDS,
    CONF_EV_START_WINDOW_SECONDS,
    CONF_EV_STOP_WINDOW_SECONDS,
    CONF_EV_CHARGE_THRESHOLD_W,
    CONF_OCPP_EMBEDDED,
    CONF_OCPP_PORT,
    CONF_OCPP_RESTART_STRICT,
    CONF_OCPP_REMOTE_START_COOLDOWN_S,
    DEFAULT_EV_CONTROL_INTERVAL_SECONDS,
    DEFAULT_EV_START_WINDOW_SECONDS,
    DEFAULT_EV_STOP_WINDOW_SECONDS,
    DEFAULT_EV_CHARGE_THRESHOLD_W,
    DEFAULT_OCPP_EMBEDDED,
    DEFAULT_OCPP_PORT,
    DEFAULT_OCPP_RESTART_STRICT,
    DEFAULT_OCPP_REMOTE_START_COOLDOWN_S,
    CONF_SPOT_PRICE_ENTITY,
    DEFAULT_BATTERY_CAPACITY,
    DEFAULT_BATTERY_FLOOR_SOC,
    DEFAULT_BATTERY_MAX_SOC,
    DEFAULT_CURRENCY,
    DEFAULT_DSO_GLN,
    DEFAULT_EVCC_URL,
    DEFAULT_FAST_POLL_SECONDS,
    DEFAULT_FORECAST_HOURS,
    DEFAULT_MIN_SPREAD_ARBITRAGE,
    DEFAULT_ROUND_TRIP_EFFICIENCY,
    DEFAULT_SOLAR_FORECAST_SOURCE,
    DEFAULT_LIVE_DATA_SOURCE,
    DEFAULT_FOXESS_GRID_IMPORT,
    DEFAULT_FOXESS_GRID_EXPORT,
    DEFAULT_FOXESS_PV_POWER,
    DEFAULT_FOXESS_LOAD_POWER,
    SOLAR_SOURCE_EVCC,
    SOLAR_SOURCE_FORECAST_SOLAR,
    SOLAR_SOURCE_SOLCAST,
    SOLAR_SOURCE_AUTO,
    LIVE_SOURCE_EVCC,
    LIVE_SOURCE_HYBRID,
    LIVE_SOURCE_FOXESS,
    DEFAULT_EV_CONTROLLER_ENABLED,
    DEFAULT_EV_DEFAULT_MODE,
    EV_MODE_LOCKED,
    EV_MODE_PV,
    EV_MODE_PV_BATTERY,
    EV_MODE_FULL,
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

from . import discovery

_LOGGER = logging.getLogger(__name__)


def _entity_optional(key: str, current_value: str):
    """Voluptuous Optional for an EntitySelector that may be blank.

    Don't supply `default=""` when there's no saved value: the EntitySelector
    validator rejects empty strings, and an unset default would otherwise
    leak `""` into the validation phase. Without a default, the frontend
    serializes the field as null/undefined when empty and the schema treats
    it as absent — which voluptuous handles cleanly for `vol.Optional`.
    """
    if current_value:
        return vol.Optional(key, default=current_value)
    return vol.Optional(key)


class BatteryArbitrageConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the setup wizard."""

    VERSION = 15

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: Live data source — EVCC, Hybrid, or FoxESS only."""
        if user_input is not None:
            source = user_input[CONF_LIVE_DATA_SOURCE]
            self._data[CONF_LIVE_DATA_SOURCE] = source
            if source == LIVE_SOURCE_FOXESS:
                return await self.async_step_foxess_live_warning()
            # EVCC or Hybrid both need EVCC URL
            return await self.async_step_evcc_url()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_LIVE_DATA_SOURCE,
                             default=DEFAULT_LIVE_DATA_SOURCE):
                    selector.SelectSelector(selector.SelectSelectorConfig(
                        options=[
                            {"value": LIVE_SOURCE_EVCC,
                             "label": "EVCC (everything from EVCC)"},
                            {"value": LIVE_SOURCE_HYBRID,
                             "label": "Hybrid (FoxESS grid/PV, EVCC for EV)"},
                            {"value": LIVE_SOURCE_FOXESS,
                             "label": "FoxESS only (no EVCC — no EV coordination)"},
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                    )),
            }),
        )

    async def async_step_evcc_url(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1b: EVCC URL (only for EVCC + Hybrid modes)."""
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
                # Hybrid mode also needs FoxESS live entities before continuing
                if self._data.get(CONF_LIVE_DATA_SOURCE) == LIVE_SOURCE_HYBRID:
                    return await self.async_step_foxess_live_entities()
                return await self.async_step_foxess()

        return self.async_show_form(
            step_id="evcc_url",
            errors=errors,
            data_schema=vol.Schema({
                vol.Required(CONF_EVCC_URL, default=DEFAULT_EVCC_URL): str,
            }),
        )

    async def async_step_foxess_live_warning(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """FoxESS-only mode: hard acknowledgement that no EV is being managed.

        Without EVCC there is no way for the integration to know that an EV
        is plugged in or charging. If the user has an EV and Solar AI starts
        grid-charging the battery while the EV is also drawing power, the
        combined draw can exceed the breaker. This step refuses to continue
        until the user explicitly ticks the acknowledgement.
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_ACKNOWLEDGE_NO_EV, False):
                errors[CONF_ACKNOWLEDGE_NO_EV] = "must_acknowledge_no_ev"
            else:
                self._data[CONF_ACKNOWLEDGE_NO_EV] = True
                return await self.async_step_foxess_live_entities()

        return self.async_show_form(
            step_id="foxess_live_warning",
            errors=errors,
            data_schema=vol.Schema({
                vol.Required(CONF_ACKNOWLEDGE_NO_EV, default=False): bool,
            }),
        )

    async def async_step_foxess_live_entities(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the FoxESS sensors used for live grid / PV / load."""
        if user_input is not None:
            self._data.update(user_input)
            # We need a battery capacity even without EVCC; seed default for FoxESS-only.
            self._data.setdefault(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY)
            return await self.async_step_foxess()

        return self.async_show_form(
            step_id="foxess_live_entities",
            data_schema=vol.Schema({
                vol.Required(CONF_FOXESS_GRID_IMPORT_ENTITY,
                             default=discovery.discover_grid_import(self.hass)
                                      or DEFAULT_FOXESS_GRID_IMPORT):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Required(CONF_FOXESS_GRID_EXPORT_ENTITY,
                             default=discovery.discover_grid_export(self.hass)
                                      or DEFAULT_FOXESS_GRID_EXPORT):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Required(CONF_FOXESS_PV_POWER_ENTITY,
                             default=discovery.discover_pv_power(self.hass)
                                      or DEFAULT_FOXESS_PV_POWER):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Required(CONF_FOXESS_LOAD_POWER_ENTITY,
                             default=discovery.discover_load_power(self.hass)
                                      or DEFAULT_FOXESS_LOAD_POWER):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            }),
        )

    async def async_step_foxess(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: Inverter control entities."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_battery_sensors()

        # Discover by integration ownership + unique_id suffix — survives
        # entity renames, language packs, and multi-inverter installs.
        detected_inverter_id    = discovery.discover_inverter_id(self.hass) or self._detect_inverter_id()
        detected_work_mode      = discovery.discover_work_mode_select(self.hass)
        detected_force_charge   = discovery.discover_force_charge_power(self.hass)
        detected_force_discharge = discovery.discover_force_discharge_power(self.hass)

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

        # Pre-fill via device-registry-aware discovery, falling back to the
        # well-known default entity ID so the user still sees something
        # reasonable when discovery returns None (e.g. integration not yet
        # installed at the time the wizard is opened).
        return self.async_show_form(
            step_id="battery_sensors",
            data_schema=vol.Schema({
                vol.Required(CONF_BATTERY_SOC_ENTITY,
                             default=discovery.discover_battery_soc(self.hass) or FOXESS_BATTERY_SOC):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Required(CONF_CELL_TEMP_ENTITY,
                             default=discovery.discover_cell_temp_low(self.hass) or FOXESS_CELL_TEMP_LOW):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Required(CONF_BATTERY_CHARGE_ENTITY,
                             default=discovery.discover_battery_charge_power(self.hass) or FOXESS_BATTERY_CHARGE_POWER):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Required(CONF_BATTERY_DISCHARGE_ENTITY,
                             default=discovery.discover_battery_discharge_power(self.hass) or FOXESS_BATTERY_DISCHARGE_POWER):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Required(CONF_BATTERY_CHARGE_TOTAL_ENTITY,
                             default=discovery.discover_battery_charge_total(self.hass) or FOXESS_BATTERY_CHARGE_TOTAL):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Required(CONF_BATTERY_DISCHARGE_TOTAL_ENTITY,
                             default=discovery.discover_battery_discharge_total(self.hass) or FOXESS_BATTERY_DISCHARGE_TOTAL):
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
            return await self.async_step_solar_source()

        detected = self._find_entity(STROMLIGNING_SPOTPRICE_EX_VAT)

        return self.async_show_form(
            step_id="spot_price",
            data_schema=vol.Schema({
                vol.Required(CONF_SPOT_PRICE_ENTITY,
                             default=detected or STROMLIGNING_SPOTPRICE_EX_VAT):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            }),
        )

    async def async_step_solar_source(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step: Pick the solar forecast source.

        Four options: EVCC (Solcast under the hood), Solcast direct (HA
        integration), Forecast.Solar (HA integration), or Auto (try them all
        in order). The Forecast.Solar and Solcast entity fields are stored
        if provided, regardless of source — that way Auto-mode fallback works.

        For FoxESS-only live-data installs the EVCC and Auto options are
        excluded since there is no EVCC to call.
        """
        if user_input is not None:
            self._data[CONF_SOLAR_FORECAST_SOURCE] = user_input[CONF_SOLAR_FORECAST_SOURCE]
            fs_entity = user_input.get(CONF_FORECAST_SOLAR_ENTITY, "")
            sc_entity = user_input.get(CONF_SOLCAST_ENTITY, "")
            if fs_entity:
                self._data[CONF_FORECAST_SOLAR_ENTITY] = fs_entity
            if sc_entity:
                self._data[CONF_SOLCAST_ENTITY] = sc_entity
            return await self.async_step_battery()

        # Auto-detect entity defaults
        fs_detected = self._find_entity("sensor.energy_production_today")
        sc_detected = self._find_entity("sensor.solcast_pv_forecast_forecast_today")

        # If FoxESS-only mode, EVCC and Auto options have no EVCC to call —
        # restrict the dropdown to options that don't require EVCC.
        live_source = self._data.get(CONF_LIVE_DATA_SOURCE, DEFAULT_LIVE_DATA_SOURCE)
        if live_source == LIVE_SOURCE_FOXESS:
            source_options = [
                {"value": SOLAR_SOURCE_FORECAST_SOLAR,
                 "label": "Forecast.Solar (HA integration)"},
                {"value": SOLAR_SOURCE_SOLCAST,
                 "label": "Solcast (HA integration)"},
            ]
            default_source = SOLAR_SOURCE_FORECAST_SOLAR
        else:
            source_options = [
                {"value": SOLAR_SOURCE_EVCC,
                 "label": "EVCC (Solcast via EVCC)"},
                {"value": SOLAR_SOURCE_SOLCAST,
                 "label": "Solcast (HA integration, direct)"},
                {"value": SOLAR_SOURCE_FORECAST_SOLAR,
                 "label": "Forecast.Solar (HA integration)"},
                {"value": SOLAR_SOURCE_AUTO,
                 "label": "Auto (EVCC → Forecast.Solar → Solcast)"},
            ]
            default_source = DEFAULT_SOLAR_FORECAST_SOURCE

        return self.async_show_form(
            step_id="solar_source",
            data_schema=vol.Schema({
                vol.Required(CONF_SOLAR_FORECAST_SOURCE, default=default_source):
                    selector.SelectSelector(selector.SelectSelectorConfig(
                        options=source_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )),
                _entity_optional(CONF_FORECAST_SOLAR_ENTITY, fs_detected or ""):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                _entity_optional(CONF_SOLCAST_ENTITY, sc_detected or ""):
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
            return await self.async_step_ocpp_settings()

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
                vol.Required(CONF_LIVE_DATA_SOURCE,
                             default=data.get(CONF_LIVE_DATA_SOURCE,
                                              DEFAULT_LIVE_DATA_SOURCE)):
                    selector.SelectSelector(selector.SelectSelectorConfig(
                        options=[
                            {"value": LIVE_SOURCE_EVCC,
                             "label": "EVCC (everything from EVCC)"},
                            {"value": LIVE_SOURCE_HYBRID,
                             "label": "Hybrid (FoxESS grid/PV, EVCC for EV)"},
                            {"value": LIVE_SOURCE_FOXESS,
                             "label": "FoxESS only (no EVCC — no EV coordination)"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )),
                vol.Required(CONF_SOLAR_FORECAST_SOURCE,
                             default=data.get(CONF_SOLAR_FORECAST_SOURCE,
                                              DEFAULT_SOLAR_FORECAST_SOURCE)):
                    selector.SelectSelector(selector.SelectSelectorConfig(
                        options=[
                            {"value": SOLAR_SOURCE_EVCC,
                             "label": "EVCC (Solcast via EVCC)"},
                            {"value": SOLAR_SOURCE_SOLCAST,
                             "label": "Solcast (HA integration, direct)"},
                            {"value": SOLAR_SOURCE_FORECAST_SOLAR,
                             "label": "Forecast.Solar (HA integration)"},
                            {"value": SOLAR_SOURCE_AUTO,
                             "label": "Auto (EVCC → Forecast.Solar → Solcast)"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )),
                _entity_optional(CONF_FORECAST_SOLAR_ENTITY,
                                 data.get(CONF_FORECAST_SOLAR_ENTITY, "")):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                _entity_optional(CONF_SOLCAST_ENTITY,
                                 data.get(CONF_SOLCAST_ENTITY, "")):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                _entity_optional(CONF_SOLCAST_TOMORROW_ENTITY,
                                 data.get(CONF_SOLCAST_TOMORROW_ENTITY, "")):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(CONF_FOXESS_GRID_IMPORT_ENTITY,
                             default=data.get(CONF_FOXESS_GRID_IMPORT_ENTITY,
                                              DEFAULT_FOXESS_GRID_IMPORT)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(CONF_FOXESS_GRID_EXPORT_ENTITY,
                             default=data.get(CONF_FOXESS_GRID_EXPORT_ENTITY,
                                              DEFAULT_FOXESS_GRID_EXPORT)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(CONF_FOXESS_PV_POWER_ENTITY,
                             default=data.get(CONF_FOXESS_PV_POWER_ENTITY,
                                              DEFAULT_FOXESS_PV_POWER)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(CONF_FOXESS_LOAD_POWER_ENTITY,
                             default=data.get(CONF_FOXESS_LOAD_POWER_ENTITY,
                                              DEFAULT_FOXESS_LOAD_POWER)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            }),
        )

    async def async_step_ocpp_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """OCPP / EV charge controller settings.

        Everything Solar AI needs to talk to the OCPP-connected charger:
        - Master enable toggle (off by default)
        - The OCPP charge point ID (what the charger announces)
        - Optional explicit entity overrides for status + power sensors
          (auto-derived from the charge point ID if left blank)
        - Default EV mode that's applied when a vehicle plugs in fresh
        """
        if user_input is not None:
            # Strip empty optional strings so defaults can apply at read time
            cleaned = {k: v for k, v in user_input.items() if v != ""}
            self._data.update(cleaned)
            return await self.async_step_entities()

        data = self._entry.data

        # Auto-detect defaults for the entity overrides if a charge point ID
        # is already configured.
        current_id = data.get(CONF_EV_OCPP_CHARGE_POINT_ID, "")
        default_status = (
            data.get(CONF_EV_OCPP_STATUS_ENTITY)
            or (f"sensor.{current_id.lower()}_status" if current_id else "")
        )
        default_power = (
            data.get(CONF_EV_OCPP_POWER_ENTITY)
            or (f"sensor.{current_id.lower()}_power_active_import" if current_id else "")
        )

        return self.async_show_form(
            step_id="ocpp_settings",
            data_schema=vol.Schema({
                # ── Embedded OCPP server (v0.27.0) ──────────────────────
                vol.Required(CONF_OCPP_EMBEDDED,
                             default=data.get(CONF_OCPP_EMBEDDED,
                                              DEFAULT_OCPP_EMBEDDED)):
                    bool,
                vol.Required(CONF_OCPP_PORT,
                             default=data.get(CONF_OCPP_PORT,
                                              DEFAULT_OCPP_PORT)):
                    vol.All(vol.Coerce(int), vol.Range(min=1024, max=65535)),
                # ── EV controller ───────────────────────────────────────
                vol.Required(CONF_EV_CONTROLLER_ENABLED,
                             default=data.get(CONF_EV_CONTROLLER_ENABLED,
                                              DEFAULT_EV_CONTROLLER_ENABLED)):
                    bool,
                vol.Optional(CONF_EV_OCPP_CHARGE_POINT_ID,
                             default=current_id):
                    str,
                _entity_optional(CONF_EV_OCPP_STATUS_ENTITY, default_status):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                _entity_optional(CONF_EV_OCPP_POWER_ENTITY, default_power):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Required(CONF_EV_DEFAULT_MODE,
                             default=data.get(CONF_EV_DEFAULT_MODE,
                                              DEFAULT_EV_DEFAULT_MODE)):
                    selector.SelectSelector(selector.SelectSelectorConfig(
                        options=[
                            {"value": EV_MODE_LOCKED,     "label": "Låst (ingen opladning)"},
                            {"value": EV_MODE_PV,         "label": "Kun solenergi"},
                            {"value": EV_MODE_PV_BATTERY, "label": "Min via sol+batteri"},
                            {"value": EV_MODE_FULL,       "label": "Fuld kraft"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )),
                # Time-based control loop tuning (v0.26.0).
                # Loop interval ≤ start_window/4 is recommended (so the loop
                # samples the threshold-crossing several times during the window).
                vol.Required(CONF_EV_CONTROL_INTERVAL_SECONDS,
                             default=data.get(CONF_EV_CONTROL_INTERVAL_SECONDS,
                                              DEFAULT_EV_CONTROL_INTERVAL_SECONDS)):
                    vol.All(vol.Coerce(int), vol.Range(min=5, max=60)),
                vol.Required(CONF_EV_START_WINDOW_SECONDS,
                             default=data.get(CONF_EV_START_WINDOW_SECONDS,
                                              DEFAULT_EV_START_WINDOW_SECONDS)):
                    vol.All(vol.Coerce(int), vol.Range(min=10, max=600)),
                vol.Required(CONF_EV_STOP_WINDOW_SECONDS,
                             default=data.get(CONF_EV_STOP_WINDOW_SECONDS,
                                              DEFAULT_EV_STOP_WINDOW_SECONDS)):
                    vol.All(vol.Coerce(int), vol.Range(min=30, max=1800)),
                vol.Required(CONF_EV_CHARGE_THRESHOLD_W,
                             default=data.get(CONF_EV_CHARGE_THRESHOLD_W,
                                              DEFAULT_EV_CHARGE_THRESHOLD_W)):
                    vol.All(vol.Coerce(int), vol.Range(min=500, max=10000)),
                # ── OCPP charger compatibility (v0.28.7) ────────────────
                # Strict = restart only from spec-compliant plugged-in
                # states. Lenient (default) also restarts from Charging
                # and Finishing for chargers (e.g. FoxESS L11PMC) that
                # linger in non-spec states after a cool-down stop.
                vol.Required(CONF_OCPP_RESTART_STRICT,
                             default=data.get(CONF_OCPP_RESTART_STRICT,
                                              DEFAULT_OCPP_RESTART_STRICT)):
                    bool,
                vol.Required(CONF_OCPP_REMOTE_START_COOLDOWN_S,
                             default=data.get(CONF_OCPP_REMOTE_START_COOLDOWN_S,
                                              DEFAULT_OCPP_REMOTE_START_COOLDOWN_S)):
                    vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
            }),
        )

    async def async_step_entities(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: Entity mappings — inverter controls and battery sensors."""
        if user_input is not None:
            self._data.update(user_input)
            # Persist into entry.data so the coordinator reads the new values on reload.
            # (HA's default OptionsFlow saves to entry.options which the coordinator
            # never reads — that's why prior options-flow edits were silently no-ops.)
            new_data = {**self._entry.data, **self._data}
            self.hass.config_entries.async_update_entry(self._entry, data=new_data)
            return self.async_create_entry(title="", data={})

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
