"""Shared pytest fixtures for Battery Arbitrage tests."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

MOCK_CONFIG = {
    "evcc_url": "http://localhost:7070",
    "foxess_inverter_id": "test_inverter_id",
    "foxess_work_mode_entity": "select.foxessmodbus_work_mode",
    "foxess_force_charge_entity": "number.foxessmodbus_force_charge_power",
    "foxess_force_discharge_entity": "number.foxessmodbus_force_discharge_power",
    "stromligning_entity": "sensor.stromligning_spotprice_ex_vat",
    "battery_capacity": 11.52,
    "battery_floor_soc": 50,
    "battery_max_soc": 100,
    "round_trip_efficiency": 0.92,
    "min_spread_arbitrage": 1.0,
    "min_solar_export_price": 0.50,
    "forecast_hours": 24,
    "dashboard_url_path": "",
}

MOCK_EVCC_STATE = {
    "homePower": 500,
    "pvPower": 3000,
    "battery": {"capacity": 11520},
    "loadpoints": [{"chargePower": 0, "mode": "pv", "connected": False}],
}

MOCK_SOLAR_RATES = {
    "rates": [
        {
            "start": datetime.now(timezone.utc).isoformat(),
            "end": datetime.now(timezone.utc).isoformat(),
            "value": 2000,
        }
    ]
}

MOCK_GRID_RATES = {
    "rates": [
        {
            "start": datetime.now(timezone.utc).isoformat(),
            "end": datetime.now(timezone.utc).isoformat(),
            "value": 1.5,
        }
    ]
}


@pytest.fixture
def mock_config():
    return dict(MOCK_CONFIG)


@pytest.fixture
def mock_evcc_responses():
    return MOCK_EVCC_STATE, MOCK_SOLAR_RATES, MOCK_GRID_RATES
