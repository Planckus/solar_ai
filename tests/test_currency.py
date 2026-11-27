"""Money units and messages follow the currency chosen in the settings."""
from __future__ import annotations

from custom_components.battery_arbitrage.coordinator import BatteryArbitrageCoordinator
from custom_components.battery_arbitrage.sensor import SENSORS


def test_no_sensor_has_a_fixed_dkk_unit():
    fixed = [d.key for d in SENSORS
             if d.native_unit_of_measurement and "DKK" in d.native_unit_of_measurement]
    assert fixed == []


def test_money_sensors_use_the_currency_template():
    keys = {d.key: d.currency_unit_template for d in SENSORS}
    for key in ("export_income", "import_cost", "net_grid_balance",
                "total_savings_today", "total_savings_all", "total_savings_range"):
        assert keys[key] == "{}"
    for key in ("feed_in_tariff", "min_export_price_display", "price_forecast"):
        assert keys[key] == "{}/kWh"


def test_coordinator_currency_follows_the_setting():
    c = object.__new__(BatteryArbitrageCoordinator)
    c.config = {"currency": "PLN"}
    assert c._currency == "PLN"
    c.config = {}
    assert c._currency == "DKK"
