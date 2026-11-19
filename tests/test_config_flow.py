"""Tests for the Solar AI setup wizard (config flow)."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.battery_arbitrage import const as C
from custom_components.battery_arbitrage.const import DOMAIN

FLOW = "custom_components.battery_arbitrage.config_flow.BatteryArbitrageConfigFlow"
DISCOVERY = "custom_components.battery_arbitrage.discovery"

# What discovery returns on a FoxESS Modbus install where every entity is found.
DETECTED = {
    C.CONF_BATTERY_SOC_ENTITY: "sensor.foxessmodbus_battery_soc",
    C.CONF_CELL_TEMP_ENTITY: "sensor.foxessmodbus_bms_cell_temp_low",
    C.CONF_BATTERY_CHARGE_ENTITY: "sensor.foxessmodbus_battery_charge",
    C.CONF_BATTERY_DISCHARGE_ENTITY: "sensor.foxessmodbus_battery_discharge",
    C.CONF_BATTERY_CHARGE_TOTAL_ENTITY: "sensor.foxessmodbus_battery_charge_total",
    C.CONF_BATTERY_DISCHARGE_TOTAL_ENTITY: "sensor.foxessmodbus_battery_discharge_total",
    C.CONF_FOXESS_GRID_IMPORT_ENTITY: "sensor.foxessmodbus_grid_consumption",
    C.CONF_FOXESS_GRID_EXPORT_ENTITY: "sensor.foxessmodbus_feed_in",
    C.CONF_FOXESS_PV_POWER_ENTITY: "sensor.foxessmodbus_pv_power_now",
    C.CONF_FOXESS_LOAD_POWER_ENTITY: "sensor.foxessmodbus_load_power",
    C.CONF_FOXESS_WORK_MODE_ENTITY: "select.foxessmodbus_work_mode",
    C.CONF_FOXESS_FORCE_CHARGE_ENTITY: "number.foxessmodbus_force_charge_power",
    C.CONF_FOXESS_FORCE_DISCHARGE_ENTITY: "number.foxessmodbus_force_discharge_power",
    C.CONF_FOXESS_MAX_DISCHARGE_ENTITY: "number.foxessmodbus_max_discharge_current",
    C.CONF_FOXESS_INVERTER_ID: "inverter_device_id",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests in this module."""
    yield


async def test_no_foxess_modbus_aborts(hass):
    """Without the FoxESS Modbus integration the wizard stops at once."""
    with patch(f"{DISCOVERY}.has_foxess_modbus", return_value=False):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "no_foxess_modbus"


async def test_full_flow(hass):
    """EVCC source, EVCC reachable, everything detected: quick setup creates the entry."""
    with patch(f"{DISCOVERY}.has_foxess_modbus", return_value=True), patch(
        f"{DISCOVERY}.discover_all", return_value=dict(DETECTED)
    ), patch(
        f"{FLOW}._test_evcc", return_value=(True, {"battery": {"capacity": 11.52}})
    ), patch(
        "custom_components.battery_arbitrage.async_setup_entry", return_value=True
    ) as mock_setup:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={C.CONF_LIVE_DATA_SOURCE: C.LIVE_SOURCE_EVCC},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "evcc_url"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={C.CONF_EVCC_URL: "http://evcc.local:7070/"},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "quick"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                C.CONF_BATTERY_CAPACITY: 11.52,
                C.CONF_DSO_GLN: C.DEFAULT_DSO_GLN,
                C.CONF_CURRENCY: "DKK",
                C.CONF_CREATE_DASHBOARD: False,
                "advanced": False,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Solar AI"
    data = result["data"]
    assert data[C.CONF_LIVE_DATA_SOURCE] == C.LIVE_SOURCE_EVCC
    assert data[C.CONF_EVCC_URL] == "http://evcc.local:7070"
    assert data[C.CONF_BATTERY_CAPACITY] == 11.52
    assert data[C.CONF_DSO_GLN] == C.DEFAULT_DSO_GLN
    assert data[C.CONF_CURRENCY] == "DKK"
    assert data[C.CONF_CREATE_DASHBOARD] is False
    assert data[C.CONF_SOLAR_FORECAST_SOURCE] == C.SOLAR_SOURCE_FORECAST_SOLAR
    for key, entity_id in DETECTED.items():
        assert data[key] == entity_id
    assert "_evcc_data" not in data
    assert len(mock_setup.mock_calls) == 1


async def test_evcc_unreachable(hass):
    """An unreachable EVCC keeps the user on the EVCC URL step with an error."""
    with patch(f"{DISCOVERY}.has_foxess_modbus", return_value=True), patch(
        f"{FLOW}._test_evcc", return_value=(False, {})
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={C.CONF_LIVE_DATA_SOURCE: C.LIVE_SOURCE_EVCC},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={C.CONF_EVCC_URL: "http://bad.host:7070"},
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "evcc_url"
    assert result["errors"] == {C.CONF_EVCC_URL: "evcc_unreachable"}
