"""Constants for Battery Arbitrage integration."""
from __future__ import annotations

DOMAIN = "battery_arbitrage"
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.data"

# Config entry keys
CONF_EVCC_URL = "evcc_url"
CONF_FOXESS_INVERTER_ID = "foxess_inverter_id"
CONF_BATTERY_FLOOR_SOC = "battery_floor_soc"
CONF_BATTERY_MAX_SOC = "battery_max_soc"
CONF_BATTERY_CAPACITY = "battery_capacity"
CONF_ROUND_TRIP_EFFICIENCY = "round_trip_efficiency"
CONF_MIN_SPREAD_ARBITRAGE = "min_spread_arbitrage"
CONF_MIN_SOLAR_EXPORT_PRICE = "min_solar_export_price"
CONF_FORECAST_HOURS = "forecast_hours"
CONF_DASHBOARD_URL_PATH = "dashboard_url_path"
CONF_FOXESS_WORK_MODE_ENTITY = "foxess_work_mode_entity"
CONF_FOXESS_FORCE_CHARGE_ENTITY = "foxess_force_charge_entity"
CONF_FOXESS_FORCE_DISCHARGE_ENTITY = "foxess_force_discharge_entity"
CONF_STROMLIGNING_ENTITY = "stromligning_entity"

# Defaults
DEFAULT_EVCC_URL = "http://192.168.1.2:7070"
DEFAULT_BATTERY_FLOOR_SOC = 50
DEFAULT_BATTERY_MAX_SOC = 100
DEFAULT_BATTERY_CAPACITY = 11.52
DEFAULT_ROUND_TRIP_EFFICIENCY = 0.92
DEFAULT_MIN_SPREAD_ARBITRAGE = 1.0
DEFAULT_MIN_SOLAR_EXPORT_PRICE = 0.50
DEFAULT_FORECAST_HOURS = 24
DEFAULT_EXPORT_DEDUCTION = 0.01  # DKK/kWh deducted by electricity company

# Well-known FoxESS entity IDs (auto-detected, user can override)
FOXESS_BATTERY_SOC = "sensor.foxessmodbus_battery_soc_1"
FOXESS_BATTERY_TEMP = "sensor.foxessmodbus_battery_temp_1"
FOXESS_CELL_TEMP_LOW = "sensor.foxessmodbus_bms_cell_temp_low_1"
FOXESS_CELL_TEMP_HIGH = "sensor.foxessmodbus_bms_cell_temp_high_1"
FOXESS_BATTERY_CHARGE_POWER = "sensor.foxessmodbus_battery_charge"
FOXESS_BATTERY_DISCHARGE_POWER = "sensor.foxessmodbus_battery_discharge"
FOXESS_LOAD_POWER = "sensor.foxessmodbus_load_power"
FOXESS_FEED_IN = "sensor.foxessmodbus_feed_in"
FOXESS_WORK_MODE_ENTITY = "select.foxessmodbus_work_mode"
FOXESS_FORCE_CHARGE_ENTITY = "number.foxessmodbus_force_charge_power"
FOXESS_FORCE_DISCHARGE_ENTITY = "number.foxessmodbus_force_discharge_power"
FOXESS_EXPORT_LIMIT_REGISTER = 46616

# Strømligning
STROMLIGNING_SPOTPRICE_EX_VAT = "sensor.stromligning_spotprice_ex_vat"

# EVCC API endpoints
EVCC_API_STATE = "/api/state"
EVCC_API_SOLAR = "/api/tariff/solar"
EVCC_API_GRID = "/api/tariff/grid"
EVCC_API_BATTERY_MODE = "/api/batterymode"
EVCC_API_BUFFER_SOC = "/api/buffersoc"
EVCC_API_PRIORITY_SOC = "/api/prioritysoc"

# FoxESS work mode values
WORK_MODE_SELF_USE = "Self Use"
WORK_MODE_FORCE_CHARGE = "Force Charge"
WORK_MODE_FORCE_DISCHARGE = "Force Discharge"
WORK_MODE_FEED_IN_FIRST = "Feed-in First"

# EVCC battery mode values
EVCC_BATTERY_NORMAL = "normal"
EVCC_BATTERY_HOLD = "hold"
EVCC_BATTERY_CHARGE = "charge"

# EV charging modes
EV_MODE_PV = "pv"
EV_MODE_NOW = "now"
EV_MODE_MIN_PV = "minpv"
EV_MODE_OFF = "off"

# System operating modes
MODE_NORMAL = "normal"
MODE_EXPORTING = "exporting"
MODE_GRID_CHARGING = "grid_charging"
MODE_DISABLED = "disabled"

# Temperature buckets for learned charge rates: (key, min_c, max_c, default_kw)
TEMP_BUCKETS: list[tuple[str, float | None, float | None, float]] = [
    ("below_0",   None, 0.0,  0.5),
    ("0_to_10",   0.0,  10.0, 1.5),
    ("10_to_20",  10.0, 20.0, 2.5),
    ("20_to_35",  20.0, 35.0, 3.6),
    ("above_35",  35.0, None, 2.0),
]

# Coordinator update intervals
UPDATE_INTERVAL_SECONDS = 300        # 5 min — normal polling
CALIBRATION_MIN_CHARGE_KW = 0.3     # Minimum charge power to count as a calibration sample
CALIBRATION_MAX_SOC = 95            # Don't calibrate near-full (BMS tapers naturally)
CALIBRATION_MAX_SAMPLES = 200       # Per temp bucket
LOAD_HISTORY_MAX_SAMPLES = 8064     # 4 weeks × 7 days × 24h × 12 per hour
VACATION_SHORT_WINDOW = 24          # Samples for short-term (2h) average
VACATION_THRESHOLD = 0.25           # 25% of long-term baseline → vacation
VACATION_MIN_DURATION = 48          # Must be below threshold for 4h (48 × 5min samples)
MIN_EXPORTABLE_KWH = 0.5            # Don't bother exporting less than this
MIN_GRID_CHARGE_KWH = 0.5           # Don't bother grid-charging less than this
