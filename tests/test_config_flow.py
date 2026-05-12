"""Tests for Battery Arbitrage config flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.battery_arbitrage.const import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests in this module."""
    yield


async def test_full_flow(hass, mock_config):
    """Test the full config flow succeeds with mocked EVCC and entities."""
    # Pre-populate hass states so entity lookups work
    hass.states.async_set("select.foxessmodbus_work_mode", "Self Use")
    hass.states.async_set("number.foxessmodbus_force_charge_power", "3600")
    hass.states.async_set("number.foxessmodbus_force_discharge_power", "3600")
    hass.states.async_set("sensor.stromligning_spotprice_ex_vat", "1.5")

    with patch(
        "custom_components.battery_arbitrage.config_flow."
        "BatteryArbitrageConfigFlow._test_evcc",
        return_value=(True, {"battery": {"capacity": 11520}}),
    ), patch(
        "custom_components.battery_arbitrage.config_flow."
        "BatteryArbitrageConfigFlow._list_dashboards",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"evcc_url": "http://localhost:7070"},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "foxess"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                "foxess_inverter_id": "test_id",
                "foxess_work_mode_entity": "select.foxessmodbus_work_mode",
                "foxess_force_charge_entity": "number.foxessmodbus_force_charge_power",
                "foxess_force_discharge_entity": "number.foxessmodbus_force_discharge_power",
            },
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "stromligning"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"stromligning_entity": "sensor.stromligning_spotprice_ex_vat"},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "battery"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                "battery_capacity": 11.52,
                "battery_floor_soc": 50,
                "battery_max_soc": 100,
                "round_trip_efficiency": 92,
                "min_spread_arbitrage": 1.0,
                "min_solar_export_price": 0.50,
                "forecast_hours": 24,
            },
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "dashboard"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"dashboard_url_path": ""},
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "Battery Arbitrage"
        data = result["data"]
        assert data["evcc_url"] == "http://localhost:7070"
        # Efficiency should be normalised to 0–1
        assert data["round_trip_efficiency"] == pytest.approx(0.92)


async def test_evcc_unreachable(hass):
    """Test that an unreachable EVCC shows an error."""
    with patch(
        "custom_components.battery_arbitrage.config_flow."
        "BatteryArbitrageConfigFlow._test_evcc",
        return_value=(False, {}),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"evcc_url": "http://bad.host:7070"},
        )
        assert result["type"] == FlowResultType.FORM
        assert "evcc_url" in result["errors"]
        assert result["errors"]["evcc_url"] == "evcc_unreachable"
