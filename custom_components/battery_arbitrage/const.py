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
DEFAULT_VAT_PCT = 25.0              # VAT percentage applied to buy-side prices (%)
DEFAULT_EXPORT_FEE = 0.0            # Sell-side fee/cut taken by grid company (currency/kWh)
DEFAULT_CURRENCY = "DKK"            # Currency label used in price sensor units
CONF_CURRENCY = "currency"          # Config entry key for currency selection

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
WORK_MODE_FEED_IN_FIRST = "Feed-in First"  # Best mode for grid export (battery + solar)

# The work mode to use when actively exporting to the grid
WORK_MODE_EXPORT = WORK_MODE_FEED_IN_FIRST

# Pre-existing HA automation that controls the export limit register —
# disabled while our integration is running to avoid conflicts
LEGACY_EXPORT_AUTOMATION = "automation.foxess_export_limit_by_systemtariff"

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
    ("below_0",   None,  0.0,  0.5),
    ("0_to_5",    0.0,   6.0,  1.0),
    ("6_to_15",   6.0,  16.0,  1.8),
    ("16_to_21",  16.0, 21.0,  2.5),
    ("21_to_35",  21.0, 35.0,  3.6),
    ("35_to_50",  35.0, 50.0,  2.0),
    ("above_50",  50.0, None,  1.0),
]

# Solar forecast accuracy tracking
SOLAR_ACCURACY_MAX_SAMPLES = 2016    # 14 days × 24h × 6 per hour
SOLAR_ACCURACY_MIN_FORECAST_W = 50   # Only sample when meaningful production expected
SOLAR_ACCURACY_MIN_SAMPLES = 12      # Need ≥ 1 hour of daylight data before applying factor
SOLAR_ACCURACY_COMPARISON_W = 100    # Min forecast to include in ratio calculation
SOLAR_ACCURACY_WINDOW = 576          # Use last 4 days (576 × 5 min) for the ratio

# Coordinator update intervals
UPDATE_INTERVAL_SECONDS = 300        # 5 min — normal polling
CALIBRATION_MIN_CHARGE_KW = 0.3     # Minimum charge power to count as a calibration sample
CALIBRATION_MAX_SOC = 95            # Don't calibrate near-full (BMS tapers naturally)
CALIBRATION_MAX_SAMPLES = 200       # Per temp bucket
LOAD_HISTORY_MAX_SAMPLES = 8064     # 4 weeks × 7 days × 24h × 12 per hour
SAVINGS_LOG_MAX_DAYS = 90           # Keep 90 days of daily savings data

# EV charge learning
EV_CHARGE_THRESHOLD_W = 3000        # W — above this the EV is truly charging
EV_CHARGE_BLOCK_PROBABILITY = 0.7   # Skip grid charge if EV charges >70% of time this hour
EV_LEARNING_ALPHA = 0.01            # Exp. smoothing factor (~100 sample memory ≈ 8 days/hour)

# Seasonal mode
SEASON_SOLAR_THRESHOLD_KWH = 6.0    # kWh/day 28-day avg — below = winter mode
SOLAR_DAILY_SAMPLES_MAX = 28        # Days of daily solar history to keep
VACATION_SHORT_WINDOW = 24          # Samples for short-term (2h) average
VACATION_THRESHOLD = 0.25           # 25% of long-term baseline → vacation
VACATION_MIN_DURATION = 48          # Must be below threshold for 4h (48 × 5min samples)
MIN_EXPORTABLE_KWH = 0.5            # Don't bother exporting less than this
MIN_GRID_CHARGE_KWH = 0.5           # Don't bother grid-charging less than this

# Grid overcurrent protection
GRID_MAX_KW = 17.0                  # Default circuit breaker limit (kW) — user-adjustable via number entity
GRID_SAFETY_MARGIN_KW = 0.5         # Buffer below the breaker limit to avoid nuisance trips
GRID_MIN_CHARGE_KW = 0.3            # Minimum useful battery charge rate under headroom constraint

# Pricing (VAT % and export fee are now live-configurable via number entities)

# FoxESS lifetime energy totals (for auto-detecting round-trip efficiency)
FOXESS_BATTERY_CHARGE_TOTAL = "sensor.foxessmodbus_battery_charge_total"
FOXESS_BATTERY_DISCHARGE_TOTAL = "sensor.foxessmodbus_battery_discharge_total"

# Battery capacity learning (from Force Charge cycles)
CAPACITY_MIN_SOC = 15               # % — don't sample below this (BMS edge effects near empty)
CAPACITY_MAX_SOC = 85               # % — don't sample above this (BMS tapers near full)
CAPACITY_MIN_DELTA_SOC = 0.3        # % — minimum SoC rise per tick to count as a sample
CAPACITY_MIN_CHARGE_KW = 0.5        # kW — minimum charge power to count as a valid sample
CAPACITY_MIN_SAMPLES = 20           # Need this many samples before trusting the learned value
CAPACITY_MAX_SAMPLES = 300          # Rolling window size
EFFICIENCY_MIN_TOTAL_KWH = 100      # kWh — minimum lifetime charge before trusting auto-efficiency
