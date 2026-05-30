"""Constants for Battery Arbitrage integration."""
from __future__ import annotations

DOMAIN = "battery_arbitrage"
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.data"

# Config entry keys
CONF_EVCC_URL = "evcc_url"
CONF_LIVE_DATA_SOURCE = "live_data_source"
CONF_FOXESS_GRID_IMPORT_ENTITY = "foxess_grid_import_entity"
CONF_FOXESS_GRID_EXPORT_ENTITY = "foxess_grid_export_entity"
CONF_FOXESS_PV_POWER_ENTITY = "foxess_pv_power_entity"
CONF_FOXESS_LOAD_POWER_ENTITY = "foxess_load_power_entity"
CONF_ACKNOWLEDGE_NO_EV = "acknowledge_no_ev"
# EV charge controller (Phase B1) — drives an OCPP-connected EV charger
# (e.g. FoxESS L11PMC) directly from Solar AI's solar surplus tracker.
CONF_EV_CONTROLLER_ENABLED   = "ev_controller_enabled"
CONF_EV_OCPP_CHARGE_POINT_ID = "ev_ocpp_charge_point_id"
# Optional explicit overrides for the OCPP integration's sensor entity names.
# If left blank Solar AI derives them from the charge point ID:
#   status:  sensor.<id-lowercase>_status
#   power:   sensor.<id-lowercase>_power_active_import
CONF_EV_OCPP_STATUS_ENTITY   = "ev_ocpp_status_entity"
CONF_EV_OCPP_POWER_ENTITY    = "ev_ocpp_power_entity"
CONF_EV_DEFAULT_MODE         = "ev_default_mode"
CONF_EV_MIN_CHARGE_KW        = "ev_min_charge_kw"
CONF_EV_MAX_CHARGE_KW        = "ev_max_charge_kw"
CONF_SOLAR_FORECAST_SOURCE = "solar_forecast_source"
CONF_FORECAST_SOLAR_ENTITY = "forecast_solar_entity"
CONF_SOLCAST_ENTITY = "solcast_entity"                  # today's forecast entity
CONF_SOLCAST_TOMORROW_ENTITY = "solcast_tomorrow_entity"  # tomorrow's forecast (v0.28.0)
CONF_FOXESS_INVERTER_ID = "foxess_inverter_id"
CONF_BATTERY_FLOOR_SOC = "battery_floor_soc"
CONF_BATTERY_MAX_SOC = "battery_max_soc"
CONF_BATTERY_CAPACITY = "battery_capacity"
CONF_ROUND_TRIP_EFFICIENCY = "round_trip_efficiency"
CONF_MIN_SPREAD_ARBITRAGE = "min_spread_arbitrage"
CONF_FORECAST_HOURS = "forecast_hours"
CONF_DASHBOARD_URL_PATH = "dashboard_url_path"
CONF_FOXESS_WORK_MODE_ENTITY = "foxess_work_mode_entity"
CONF_FOXESS_FORCE_CHARGE_ENTITY = "foxess_force_charge_entity"
CONF_FOXESS_FORCE_DISCHARGE_ENTITY = "foxess_force_discharge_entity"
CONF_STROMLIGNING_ENTITY = "stromligning_entity"   # legacy key — migrated to CONF_SPOT_PRICE_ENTITY
CONF_SPOT_PRICE_ENTITY = "spot_price_entity"        # generic spot-price source (any DKK/kWh sensor)

# Configurable battery sensor entity IDs (default to FoxESS Modbus names; any compatible sensor works)
CONF_BATTERY_SOC_ENTITY            = "battery_soc_entity"
CONF_CELL_TEMP_ENTITY              = "cell_temp_entity"
CONF_BATTERY_CHARGE_ENTITY         = "battery_charge_entity"
CONF_BATTERY_DISCHARGE_ENTITY      = "battery_discharge_entity"
CONF_BATTERY_CHARGE_TOTAL_ENTITY   = "battery_charge_total_entity"
CONF_BATTERY_DISCHARGE_TOTAL_ENTITY = "battery_discharge_total_entity"

# Defaults
DEFAULT_EVCC_URL = "http://homeassistant.local:7070"
DEFAULT_BATTERY_FLOOR_SOC = 50
DEFAULT_BATTERY_MAX_SOC = 100
DEFAULT_BATTERY_CAPACITY = 11.52
DEFAULT_ROUND_TRIP_EFFICIENCY = 0.92
DEFAULT_MIN_SPREAD_ARBITRAGE = 0.30
DEFAULT_FORECAST_HOURS = 24
# Solar forecast source: where the integration fetches the per-hour PV forecast from.
# Options:
#   "evcc"           — read from EVCC's /api/tariff/solar (default; Solcast under the hood)
#   "forecast_solar" — read the `watts` attribute from a user-picked Forecast.Solar HA entity
#   "auto"           — try EVCC first; fall back to Forecast.Solar if EVCC fails/empty
SOLAR_SOURCE_EVCC = "evcc"
SOLAR_SOURCE_FORECAST_SOLAR = "forecast_solar"
SOLAR_SOURCE_SOLCAST = "solcast"
SOLAR_SOURCE_AUTO = "auto"
DEFAULT_SOLAR_FORECAST_SOURCE = SOLAR_SOURCE_EVCC

# Live data source: where live grid / PV / load / EV state comes from.
#   "evcc"   — EVCC /api/state for everything (default, unchanged behaviour)
#   "hybrid" — FoxESS Modbus sensors for grid/PV/load; EVCC for EV (loadpoints + battery mode)
#   "foxess" — FoxESS Modbus sensors only; no EV info, no EVCC POST coordination
LIVE_SOURCE_EVCC = "evcc"
LIVE_SOURCE_HYBRID = "hybrid"
LIVE_SOURCE_FOXESS = "foxess"
DEFAULT_LIVE_DATA_SOURCE = LIVE_SOURCE_EVCC

# Auto-detected default FoxESS Modbus entity IDs for live-state replacement
DEFAULT_FOXESS_GRID_IMPORT = "sensor.foxessmodbus_grid_consumption"
DEFAULT_FOXESS_GRID_EXPORT = "sensor.foxessmodbus_feed_in"
DEFAULT_FOXESS_PV_POWER = "sensor.pv_power_foxessmodbus"
DEFAULT_FOXESS_LOAD_POWER = "sensor.foxessmodbus_load_power"

# EV charge controller defaults
# Modes:
#   "locked"       — no charging (current = 0)
#   "pv"           — solar surplus only; stops if surplus < min
#   "pv_battery"   — like pv, but battery may discharge to hit min if needed;
#                    never pulls grid for the EV. Stops at battery floor.
#   "full"         — charge at max; battery and grid cover whatever solar can't.
EV_MODE_LOCKED      = "locked"
EV_MODE_PV          = "pv"
EV_MODE_PV_BATTERY  = "pv_battery"
EV_MODE_FULL        = "full"
EV_MODE_SCHEDULED   = "scheduled"          # v0.36.0: defer to user-configured HA schedule entities
DEFAULT_EV_DEFAULT_MODE = EV_MODE_LOCKED   # safe choice on first connect

# ── EV scheduling (Phase A — v0.36.0) ──────────────────────────────────────
# When `_ev_active_mode == EV_MODE_SCHEDULED`, the controller resolves the
# active mode by walking a user-configured list of (HA schedule entity → EV
# mode) links. First link whose schedule entity is in state "on" wins.
# When no link is active, the configured fallback mode applies.
#
# The link list lives in entry.data under CONF_EV_SCHEDULE_LINKS as a list of
# dicts: [{"schedule_entity": "schedule.cheap_nights", "mode": "full"}, ...].
# Up to four links are configurable in the options flow. Users edit the
# schedule entities themselves via Settings → Helpers → Schedule (HA's
# native schedule helper), where they can set per-weekday time ranges with
# the full HA UI.
CONF_EV_SCHEDULE_LINKS = "ev_schedule_links"
CONF_EV_SCHEDULED_FALLBACK_MODE = "ev_scheduled_fallback_mode"
DEFAULT_EV_SCHEDULED_FALLBACK_MODE = EV_MODE_LOCKED
EV_SCHEDULE_LINKS_MAX = 4    # Practical cap; revisit if real users need more
EV_SCHEDULES_MAX = 4         # v0.38.0 — same cap, new native-schedule data model

# v0.37.0 — per-slot mode dropdown on the EV/OCPP dashboard tab.
# `locked` and `scheduled` are deliberately excluded: a schedule that
# "locks" charging is just an empty schedule (no time ranges), and a
# schedule that itself defers to another schedule would loop.
EV_SCHEDULE_LINK_MODE_OPTIONS = [EV_MODE_PV, EV_MODE_PV_BATTERY, EV_MODE_FULL]
# Storage key prefix for the per-slot live mode override. Indexed 1..N.
# `_stored[f"ev_schedule_link_{idx}_mode"]` wins over the link dict's
# `mode` field set via the options flow, so the dashboard selects act
# as the canonical source once a user has touched them.
EV_SCHEDULE_LINK_MODE_STORAGE_PREFIX = "ev_schedule_link_"

# ── EV schedules — v0.38.0 native model ───────────────────────────────────
# Schedules are owned entirely by Solar AI and edited from the dashboard.
# No dependency on HA's `schedule.*` helper integration. Each slot lives
# in `_stored["ev_schedules"]` as:
#   {"slot": 1, "enabled": True, "mode": "pv_battery",
#    "start": "23:00", "end": "06:00",
#    "days": ["mon", "tue", "wed", "thu", "fri"]}
# When `_ev_active_mode == EV_MODE_SCHEDULED`, the resolver walks the
# list in slot-order and returns the first enabled slot whose `days`
# include today AND whose `[start, end)` covers the current local time
# (end < start means the slot wraps midnight).
EV_SCHEDULE_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
EV_SCHEDULE_DEFAULT_START = "23:00"
EV_SCHEDULE_DEFAULT_END = "06:00"
EV_SCHEDULE_DEFAULT_DAYS = ["mon", "tue", "wed", "thu", "fri"]
EV_SCHEDULE_DEFAULT_MODE = EV_MODE_PV_BATTERY
DEFAULT_EV_CONTROLLER_ENABLED = False       # opt-in feature
# 3-phase Danish standard: 230 V × √3 × A → kW
EV_VOLTAGE = 230.0
EV_PHASES  = 3
EV_OCPP_MIN_AMPS = 6        # IEC 61851 minimum
EV_OCPP_MAX_AMPS = 16       # typical home 3-phase max
# 6 A × 230 V × √3 ≈ 2.39 kW per phase * 3 phases? Actually:
# 3-phase line-to-neutral 230 V, line current 6 A:
#   P = √3 × V_LL × I = √3 × 400 × 6 ≈ 4.14 kW
# We work in kW for user-facing limits and convert to amps when commanding OCPP.
DEFAULT_EV_MIN_CHARGE_KW = 4.14   # 3-phase 6 A
DEFAULT_EV_MAX_CHARGE_KW = 11.0   # 3-phase 16 A
# Hysteresis / anti-flap defaults
# NOTE: legacy tick-based constants kept for back-compat with older code paths.
# The active anti-flap logic is now time-based and configurable via
# CONF_EV_START_WINDOW_SECONDS / CONF_EV_STOP_WINDOW_SECONDS below.
EV_HYSTERESIS_START_TICKS = 2     # legacy — ticks above start threshold before resuming
EV_HYSTERESIS_STOP_TICKS  = 2     # legacy — ticks below stop threshold before stopping
EV_MAX_AMP_STEP_PER_TICK  = 2     # max ramp rate (A) per control-loop tick
EV_MIN_AMP_CHANGE         = 1     # don't bother sending OCPP write below this delta

# v0.36.2 — Curtailment-probe parameters.
# When the inverter reports PV curtailment (reg 49251 = 1) and the house
# battery is at/near its max SoC, the EV controller starts a probe: it
# guarantees `min charge kW` of EV demand for this many seconds, giving
# MPPT time to lift its output to match. After the window the real solar
# reading drives the EV target — no forecast needed. If the flag clears
# during the probe, the probe ends early and normal control resumes.
EV_CURTAILMENT_PROBE_SECONDS = 60

# v0.38.1 — When a probe expires with the PV-limited flag still set
# (MPPT didn't respond — usually grid-operator hard limit, not the
# price-floor case), wait this long before trying again. Avoids
# hammering MPPT and importing ~0.07 kWh from the grid every 4 minutes.
# Reset on EV disconnect so a new car plug-in isn't blocked by the
# previous session's failed probe.
EV_CURTAILMENT_PROBE_COOLDOWN_SECONDS = 900   # 15 minutes

# v0.39.18 — Soft cool-down for the battery-full override (v0.39.17).
# When an override-induced charging session ends for any reason (override
# conditions changed, stop-window confirmed a stop, etc.), block the
# override from firing again for this many seconds. Prevents rapid
# on/off cycling when surplus oscillates around min during partly-cloudy
# periods with a small house battery — without this, the override would
# fire → battery drains briefly → conditions fail → EV stops → battery
# refills → override fires again, with cycle times of 5-10 minutes.
# 10 minutes is short enough that the EV recovers reasonably fast when
# sun stabilises, but long enough that one passing cloud doesn't cause
# multiple restart cycles.
EV_OVERRIDE_SOFT_COOLDOWN_SECONDS = 600       # 10 minutes

# v0.39.21 — Active ramp during the battery-full override.
# When battery is full and export is blocked, the FoxESS MPPT self-throttles
# to match whatever the AC bus is drawing, so the measured solar surplus
# always equals the EV's current draw — surplus tracking can never discover
# spare PV headroom. The only way to find the real ceiling is to actively
# command more current and watch the grid meter: if MPPT lifts to cover the
# extra draw, grid import stays ~0 and we keep climbing; if it can't, the
# extra comes from the grid and we back off.
#   - Step up 1 A at most once per RAMP_INTERVAL while grid import stays at or
#     below RAMP_GRID_IMPORT_THRESHOLD_KW.
#   - If grid import exceeds the threshold, step down 1 A and freeze ramping
#     for RAMP_FREEZE_SECONDS (lets MPPT/load settle before trying again).
#   - Floor at the configured min amps; cap at the configured max amps.
#   - Reset to min on session end, EV disconnect, or when the override
#     deactivates (export resumes / battery drops below near-full).
EV_OVERRIDE_RAMP_INTERVAL_SECONDS = 30          # min seconds between up-steps
EV_OVERRIDE_RAMP_GRID_IMPORT_THRESHOLD_KW = 0.3 # kW grid import that triggers back-off
EV_OVERRIDE_RAMP_FREEZE_SECONDS = 120           # back-off freeze after over-commit

# v0.38.3 — Once the EV stop-window is armed (surplus dipped below min
# and we're counting down to actually stop), require this many seconds
# of sustained ABOVE-min surplus before clearing the stop timer. Without
# this, a single ~50 W noise blip clears the timer and the system can
# never actually transition to stopped — it spends hours in COOLING
# while the charger keeps drawing at min from solar (cosmetically wrong
# even though the physical outcome is fine).
EV_STOP_RECOVERY_SECONDS = 10

# v0.38.5 — Mirror image of EV_STOP_RECOVERY_SECONDS for the start-window
# side. When the EV is IDLE with a start timer running (surplus has been
# above min for some of the start_window already), a single tick of
# surplus dipping below min should NOT immediately reset the timer to
# zero — that's the cause of "EV won't start on borderline surplus even
# though it averages above min" (mirror of the v0.38.3 stop-window bug).
# Require sustained below-min for this many seconds before clearing the
# start timer.
EV_START_DROP_TIMEOUT_SECONDS = 10

# v0.39.11 — Entry debounce for the COOLING state. Mirror image of
# EV_STOP_RECOVERY_SECONDS in the opposite direction: when CHARGING, a
# single tick of surplus dipping below min should NOT immediately flip
# the state name to COOLING. On variable cloud cover near min_kw (e.g.
# 3-phase 6 A = 4.14 kW) the surplus can oscillate by 50-100 W with
# 10-20 s cycles, and without this debounce the dashboard flaps
# CHARGING ↔ COOLING dozens of times per hour while the EV actually
# charges continuously. Require sustained below-min for this many
# seconds before setting `_ev_surplus_below_min_since_ts` (which is
# what drives the COOLING state name in _ev_telemetry).
EV_COOL_ENTRY_SECONDS = 10

# v0.39.0 — Auto-promote EV master mode to Full when the live buy price
# goes negative, then auto-revert to the pre-promotion mode when the
# price-floor block closes (export price rises back above the user's
# min_export_price). Opt-in via switch — default OFF to preserve
# backwards-compatible behaviour. Once enabled:
#   - Trigger IN: buy_price ≤ 0 sustained for AUTO_FULL_DEBOUNCE_SECONDS
#                 AND EV plugged in AND master mode is not already Full
#   - Trigger OUT: floor block transitions from active → inactive
# Manual mode overrides clear the auto state. EV unplug clears it too.
CONF_AUTO_FULL_ON_NEGATIVE_PRICE = "auto_full_on_negative_price"
DEFAULT_AUTO_FULL_ON_NEGATIVE_PRICE = False
# Debounce window — buy price must be sustained ≤ 0 for this many
# seconds before the auto-promotion fires. Avoids flapping on
# zero-crossing noise (~5 minutes is plenty given price changes
# hourly in DK).
AUTO_FULL_DEBOUNCE_SECONDS = 300   # 5 minutes

# EV control loop (v0.26.0) — decoupled from main coordinator fast-poll.
# Lets the user match the loop cadence to their charger's OCPP write tolerance,
# and tune the start/stop windows in seconds (not ticks).
CONF_EV_CONTROL_INTERVAL_SECONDS  = "ev_control_interval_seconds"
CONF_EV_START_WINDOW_SECONDS      = "ev_start_window_seconds"
CONF_EV_STOP_WINDOW_SECONDS       = "ev_stop_window_seconds"
CONF_EV_CHARGE_THRESHOLD_W        = "ev_charge_threshold_w"
DEFAULT_EV_CONTROL_INTERVAL_SECONDS = 10   # 5–60 s; how often the EV controller re-evaluates
DEFAULT_EV_START_WINDOW_SECONDS     = 60   # 10–600 s; sustained surplus before starting
DEFAULT_EV_STOP_WINDOW_SECONDS      = 180  # 30–1800 s; sustained shortage before stopping
DEFAULT_EV_CHARGE_THRESHOLD_W       = 3000 # 500–10000 W; above this the EV is truly charging
# v0.40.2 — how often the EV controller re-asserts the active charge-rate
# limit to the charger while charging, even when the target hasn't changed.
# Recovers a charger that silently dropped its charging profile (reconnect,
# reboot, new transaction) and reverted to full current. Forced re-send
# bypasses the value-unchanged dedupe on both the controller and OCPP layers.
EV_RATE_REASSERT_SECONDS = 60

# Battery-priority threshold (v0.26.4): in PV and PV+battery modes, EV charging
# is held off until the house battery reaches this SoC. Solar surplus flows
# into the battery (via the inverter's normal priority) until the threshold,
# then diverts to the EV. Set to the battery floor SoC to revert to the old
# "EV gets surplus immediately" behaviour. Set to 100 to always fill the
# battery before letting the EV charge.
CONF_EV_BATTERY_PRIORITY_SOC     = "ev_battery_priority_soc"
DEFAULT_EV_BATTERY_PRIORITY_SOC  = 80   # %; range 50–100

# Embedded OCPP server (v0.27.0): Solar AI hosts its own OCPP 1.6 server,
# eliminating the lbbrhzn/ocpp dependency. User can still turn it off to
# go back to the external integration if they want.
CONF_OCPP_EMBEDDED  = "ocpp_embedded"
CONF_OCPP_PORT      = "ocpp_port"
DEFAULT_OCPP_EMBEDDED = True
DEFAULT_OCPP_PORT     = 9000   # 1024–65535, user-configurable
# OCPP restart compatibility (v0.28.7) — controls which charger statuses
# are considered "plugged in and ready for RemoteStartTransaction" after a
# session ends. Lenient (default) allows restart from Charging and
# Finishing in addition to the OCPP 1.6 spec set (Preparing, SuspendedEV,
# SuspendedEVSE) — required for FoxESS L11PMC and other chargers that
# linger in non-spec states after a cool-down stop. Strict restricts to
# the spec set for spec-compliant chargers.
CONF_OCPP_RESTART_STRICT = "ocpp_restart_strict"
DEFAULT_OCPP_RESTART_STRICT = False
# Cooldown between consecutive RemoteStartTransaction attempts on the same
# charger, in seconds. Throttles rapid-fire restart loops within a single
# failed start sequence. Cleared on every clean StopTransaction.
CONF_OCPP_REMOTE_START_COOLDOWN_S = "ocpp_remote_start_cooldown_s"
DEFAULT_OCPP_REMOTE_START_COOLDOWN_S = 30   # 5–300 s, user-configurable
# Battery wear cost per kWh cycled (DKK/kWh). Subtracted from CHARGE and EXPORT rewards
# in the optimizer so the model accounts for finite cycle life. Default is calibrated
# for residential LFP at ~2000 DKK/kWh installed cost using marginal-wear literature.
DEFAULT_BATTERY_DEGRADATION_COST = 0.10
# Terminal value floor: minimum DKK/kWh assumed for SoC remaining at end of horizon.
# Used when the planning window has too little price data to estimate.
DEFAULT_TERMINAL_VALUE_FALLBACK = 0.30
DEFAULT_VAT_PCT = 25.0              # VAT percentage applied to buy-side prices (%)
DEFAULT_EXPORT_FEE = 0.0            # Sell-side fee/cut taken by grid company (currency/kWh)
DEFAULT_CURRENCY = "DKK"            # Currency label used in price sensor units
CONF_CURRENCY = "currency"          # Config entry key for currency selection

# Well-known FoxESS entity IDs (auto-detected, user can override)
FOXESS_BATTERY_SOC = "sensor.foxessmodbus_battery_soc_1"
FOXESS_CELL_TEMP_LOW = "sensor.foxessmodbus_bms_cell_temp_low_1"
FOXESS_BATTERY_CHARGE_POWER = "sensor.foxessmodbus_battery_charge"
FOXESS_BATTERY_DISCHARGE_POWER = "sensor.foxessmodbus_battery_discharge"
FOXESS_LOAD_POWER = "sensor.foxessmodbus_load_power"
FOXESS_FEED_IN = "sensor.foxessmodbus_feed_in"
FOXESS_WORK_MODE_ENTITY = "select.foxessmodbus_work_mode"
FOXESS_FORCE_CHARGE_ENTITY = "number.foxessmodbus_force_charge_power"
FOXESS_FORCE_DISCHARGE_ENTITY = "number.foxessmodbus_force_discharge_power"
FOXESS_EXPORT_LIMIT_REGISTER = 46616
# RO holding register: 0 = inverter not curtailing PV; 1 = MPPT actively
# throttled (set whenever the inverter is clipping PV output for any
# reason — price-floor export limit, grid-operator limit, battery-full
# with low export ceiling, etc.). Used by the EV controller as the
# trigger for the curtailment probe (v0.36.2 — replaces the v0.30.1
# forecast-substitution heuristic).
FOXESS_PV_POWER_LIMITED_FLAG_REGISTER = 49251

# Strømligning
STROMLIGNING_SPOTPRICE_EX_VAT = "sensor.stromligning_spotprice_ex_vat"

# EVCC API endpoints
EVCC_API_STATE = "/api/state"
EVCC_API_SOLAR = "/api/tariff/solar"
EVCC_API_GRID = "/api/tariff/grid"
EVCC_API_BATTERY_MODE = "/api/batterymode"

# FoxESS work mode values
WORK_MODE_SELF_USE = "Self Use"
WORK_MODE_FORCE_CHARGE = "Force Charge"
WORK_MODE_EXPORT = "Feed-in First"  # FoxESS mode for grid export (battery + solar pushed to grid)

# Pre-existing HA automation that controls the export limit register —
# disabled while our integration is running to avoid conflicts
LEGACY_EXPORT_AUTOMATION = "automation.foxess_export_limit_by_systemtariff"

# EVCC battery mode values
EVCC_BATTERY_NORMAL = "normal"
EVCC_BATTERY_HOLD = "hold"
EVCC_BATTERY_CHARGE = "charge"

# EV charging modes
EV_MODE_NOW = "now"
EV_MODE_MIN_PV = "minpv"

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
# Per-hour solar accuracy buckets — learns shape (e.g. east vs south vs west
# orientation) from observation without requiring panel-spec input.
SOLAR_ACCURACY_HOUR_BUCKET_MAX = 168  # 7 days × 24 samples max per hour bucket
SOLAR_ACCURACY_HOUR_MIN_SAMPLES = 8   # Need ≥ 8 daylight samples per hour before trusting bucket
# Hour buckets fall back to the global rolling median until they warm up.

# Coordinator update intervals
DEFAULT_FAST_POLL_SECONDS = 15       # v0.36.0: dropped from 30 → 15 so Lovelace cards driven by integration sensors refresh every 15 s (configurable 10–300)
CONF_FAST_POLL_INTERVAL = "fast_poll_interval"
TARIFF_REFRESH_INTERVAL_SECONDS = 3600   # Hourly tariff/price refresh (not configurable)
LEARNING_TICK_INTERVAL_SECONDS = 300     # Learning model write cadence (5 min)
CALIBRATION_MIN_CHARGE_KW = 0.3     # Minimum charge power to count as a calibration sample
CALIBRATION_MAX_SOC = 95            # Don't calibrate near-full (BMS tapers naturally)
CALIBRATION_MAX_SAMPLES = 200       # Per temp bucket
LOAD_HISTORY_MAX_SAMPLES = 8064     # 4 weeks × 7 days × 24h × 12 per hour
SAVINGS_LOG_MAX_DAYS = 90           # Keep 90 days of daily savings data

# EV charge learning
EV_CHARGE_THRESHOLD_W = 3000        # W — above this the EV is truly charging
EV_CHARGE_BLOCK_PROBABILITY = 0.7   # Skip grid charge if EV charges >70% of time this hour
EV_LEARNING_ALPHA = 0.01            # Exp. smoothing factor (~100 sample memory ≈ 8 days/hour)
# EV maximum charge rate learning (single value, season-independent)
EV_MAX_KW_LEARNING_ALPHA = 0.05     # ~20-sample memory — adapts in ~2 days of full-speed sessions
EV_MAX_KW_HIGH_POWER_FRACTION = 0.8 # Only learn from sessions at ≥80% of current max (car/charger is bottleneck, not solar)

# House load profile learning
HOUSE_LOAD_LEARNING_ALPHA = 0.01    # Same memory as EV probability (~8 days per hour slot)
HOUSE_LOAD_OUTLIER_FACTOR = 5.0     # Clamp spikes to 5× learned value (once model is warm)
HOUSE_LOAD_WARM_THRESHOLD_KW = 0.05 # Model considered warm above this value (> standby noise)

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

# Spot price markup (retailer's per-kWh margin on top of raw spot price)
CONF_SPOT_MARKUP = "spot_markup"
DEFAULT_SPOT_MARKUP = 0.0               # DKK/kWh — user-adjustable via number entity
DEFAULT_MAX_EXPORT_KW = 0.0             # kW — 0 = no cap; set > 0 to limit inverter export power
DEFAULT_MIN_EXPORT_PRICE = 0.0          # DKK/kWh — minimum net export price; blocks export below this floor

# DSO tariff integration — DatahubPricelist API
CONF_DSO_GLN = "dso_gln"
DEFAULT_DSO_GLN = "5790000610099"        # Dinel nettarif C time — change to your DSO's GLN if different

# Known DSOs with confirmed GLN numbers from Energi Data Service DatahubPricelist.
# Each entry binds:
#   value          — DSO GLN used for the DatahubPricelist tariff fetches
#   label          — display name in the config flow dropdown
#   price_area     — Nord Pool zone (DK1 = Jutland/Fyn, DK2 = Sjælland)
#   stromligning   — matching DSO id on the Strømligning API (None if no match)
# The Strømligning mapping enables v0.29.0's retailer-aware pricing — when the
# user picks one of these DSOs and Strømligning mode is selected, the retailer
# dropdown filters to the right price area automatically.
DSO_OPTIONS: list[dict[str, str | None]] = [
    {"value": "5790000610099", "label": "Dinel (Aarhus + central Jutland)", "price_area": "DK1", "stromligning": "dinel_c"},
    {"value": "5790000705689", "label": "Radius (Sjælland/Copenhagen)",     "price_area": "DK2", "stromligning": "radius_c"},
    {"value": "5790000610877", "label": "Cerius (Sjælland + Lolland-Falster)", "price_area": "DK2", "stromligning": "cerius_c"},
    {"value": "5790001089030", "label": "N1 (Jutland, ex-NRGi/Konstant)",   "price_area": "DK1", "stromligning": "n1_c"},
    {"value": "5790000392261", "label": "TREFOR El-net (Trekantområdet)",   "price_area": "DK1", "stromligning": "trefor_el-net_c"},
    {"value": "5790000681075", "label": "Vores Elnet (West/South Jutland)", "price_area": "DK1", "stromligning": "vores_elnet"},
    {"value": "5790001088231", "label": "Elnet Midt (Central Jutland)",     "price_area": "DK1", "stromligning": "elnet_midt_c"},
]

# ── EV battery-lock threshold (v0.30.1) ────────────────────────────────────
# In FULL EV charge mode the house battery is locked from discharging so the
# EV can't raid it. Previously the lock engaged as soon as FULL mode was
# selected, even if the car had its own internal scheduled-charge timer and
# wouldn't pull power for hours. Now the lock follows actual draw — engages
# when observed charger power exceeds the threshold, releases when it drops.
EV_BATTERY_LOCK_POWER_THRESHOLD_KW = 0.3

# ── Strømligning retailer pricing (v0.29.0) ─────────────────────────────────
# Strømligning aggregates Danish electricity retailer pricing and exposes a
# free public API. When the buy-price mode is set to "stromligning", the
# coordinator fetches the chosen retailer's per-15-min all-in price stack
# (electricity + retailer surcharge + DSO distribution + Energinet system +
# Energinet transmission + elafgift + VAT) instead of composing it manually.
STROMLIGNING_API_BASE = "https://stromligning.dk/api"
STROMLIGNING_CACHE_HOURS = 24             # Price data refresh interval
STROMLIGNING_PRICES_TIMEOUT_SEC = 15

CONF_BUY_PRICE_MODE = "buy_price_mode"
BUY_PRICE_MODE_MANUAL = "manual"          # Existing manual stack (default, backward-compatible)
BUY_PRICE_MODE_STROMLIGNING = "stromligning"  # Strømligning retailer pricing (DK)
BUY_PRICE_MODE_OCTOPUS = "octopus"        # Octopus Energy retailer pricing (UK, v0.30.0)
DEFAULT_BUY_PRICE_MODE = BUY_PRICE_MODE_MANUAL

# ── Country picker (v0.30.0) ────────────────────────────────────────────────
# Selects the regional defaults and which smart-pricing source is available
# in the config flow. Currently:
#   denmark — Strømligning retailer pricing (DK), default VAT 25%
#   uk      — Octopus Energy retailer pricing, default VAT 5%
# More countries can be added later; the manual stack always remains
# available as a fallback regardless of country.
CONF_COUNTRY = "country"
COUNTRY_DENMARK = "denmark"
COUNTRY_UK = "uk"
DEFAULT_COUNTRY = COUNTRY_DENMARK
COUNTRY_OPTIONS: list[dict] = [
    {"value": COUNTRY_DENMARK, "label": "Denmark (Strømligning + Energi Data Service)"},
    {"value": COUNTRY_UK,      "label": "United Kingdom (Octopus Energy)"},
]

# ── Octopus Energy retailer pricing (v0.30.0) ──────────────────────────────
# Octopus exposes a free public REST API that returns per-half-hour
# inc-VAT and ex-VAT rates per product per GSP region. Both buy-side
# (import) and sell-side (Outgoing / SEG) products live on the same API.
# Initial v0.30.0 scope: buy-side only. Sell-side will follow in a later
# version (the existing manual seller-fee slider still works in the
# meantime).
OCTOPUS_API_BASE = "https://api.octopus.energy/v1"
OCTOPUS_CACHE_HOURS = 24                  # Refresh interval for the per-slot cache
OCTOPUS_PRICES_TIMEOUT_SEC = 15

CONF_OCTOPUS_PRODUCT_CODE = "octopus_product_code"     # e.g. "AGILE-24-10-01"
CONF_OCTOPUS_REGION       = "octopus_region"           # GSP region letter A–N
DEFAULT_OCTOPUS_REGION    = "A"                        # Eastern England, harmless default

# Octopus tariff codes are constructed from the product code and region:
#     E-1R-{product_code}-{region}
# (E = Electricity, 1R = single register / single rate).
OCTOPUS_TARIFF_CODE_TEMPLATE = "E-1R-{product_code}-{region}"

# GSP regions correspond to UK Distribution Network Operator (DNO) zones.
# Source: Octopus public docs + Elexon GSP group letter mapping.
OCTOPUS_GSP_REGIONS: list[dict] = [
    {"value": "A", "label": "A — Eastern England (UK Power Networks)"},
    {"value": "B", "label": "B — East Midlands (National Grid Electricity Distribution)"},
    {"value": "C", "label": "C — London (UK Power Networks)"},
    {"value": "D", "label": "D — Merseyside & North Wales (SP Energy Networks)"},
    {"value": "E", "label": "E — West Midlands (National Grid Electricity Distribution)"},
    {"value": "F", "label": "F — North East England (Northern Powergrid)"},
    {"value": "G", "label": "G — North West England (Electricity North West)"},
    {"value": "H", "label": "H — Northern Scotland (SSEN)"},
    {"value": "J", "label": "J — South East England (UK Power Networks)"},
    {"value": "K", "label": "K — Southern England (SSEN)"},
    {"value": "L", "label": "L — South Wales (National Grid Electricity Distribution)"},
    {"value": "M", "label": "M — South West England (National Grid Electricity Distribution)"},
    {"value": "N", "label": "N — Southern Scotland (SP Energy Networks)"},
    {"value": "P", "label": "P — Yorkshire (Northern Powergrid)"},
]

# Strømligning identifiers — populated when buy_price_mode == "stromligning"
CONF_STROMLIGNING_SUPPLIER_ID = "stromligning_supplier_id"   # DSO id from /api/suppliers (e.g. "dinel_c")
CONF_STROMLIGNING_PRODUCT_ID  = "stromligning_product_id"    # Retailer product id from /api/companies (e.g. "oe_stroem")
CONF_STROMLIGNING_CUSTOMER_GROUP = "stromligning_customer_group"
DEFAULT_STROMLIGNING_CUSTOMER_GROUP = "c"                    # Private households / small business

# When true, the existing manual VAT/markup/elafgift fields override
# Strømligning's per-component values. Allows surgical fixes for users whose
# contract has a markup not reflected in Strømligning's database, or when a
# regulatory rate change hasn't propagated yet.
CONF_STROMLIGNING_USE_MANUAL_OVERRIDES = "stromligning_use_manual_overrides"
DEFAULT_STROMLIGNING_USE_MANUAL_OVERRIDES = False

# ── Sell-side company picker (v0.29.0) ──────────────────────────────────────
# Strømligning catalogues consumer (buy-side) pricing only. The Danish sell-
# side market — companies that pay you for solar export — is more fragmented.
# Most retailers buy your excess at spot minus a small commission, but the
# fee varies. Some users have a different sell-side company than their
# buy-side retailer.
#
# This is a curated list of typical Danish sell-side companies with their
# per-kWh commission, used to seed the export_fee value. The user can always
# override via the existing Sell-side fee number entity (which becomes the
# active value when sell_side_company == "custom").
#
# Fees here are typical values from public price lists; verify against the
# actual contract. List is maintained manually in const.py and refreshed
# with each release.
CONF_SELL_SIDE_COMPANY = "sell_side_company"
DEFAULT_SELL_SIDE_COMPANY = "custom"     # Preserves the manual export_fee slider for existing installs
SELL_SIDE_COMPANY_OPTIONS: list[dict] = [
    {"id": "custom",            "label": "Custom — use the manual Sell-side fee slider", "fee_dkk_kwh": None},
    {"id": "same_as_buy",       "label": "Same as buy-side retailer (no separate fee)",  "fee_dkk_kwh": 0.0},
    {"id": "andel_indfodning",  "label": "Andel Energi — Indfødningsaftale",             "fee_dkk_kwh": 0.03},
    {"id": "nrgi_solcellepris", "label": "NRGi — Solcellepris",                          "fee_dkk_kwh": 0.05},
    {"id": "ewii_solcelle",     "label": "EWII — Solcellekøb",                           "fee_dkk_kwh": 0.03},
    {"id": "tibber",            "label": "Tibber (samme som køb, ingen gebyr)",          "fee_dkk_kwh": 0.0},
    {"id": "stroempaa_solcelle","label": "Strøm på — Solcelleaftale",                    "fee_dkk_kwh": 0.04},
    {"id": "modstrom_solcelle", "label": "Modstrøm — Solcellebørs",                       "fee_dkk_kwh": 0.04},
    {"id": "ostroem_salg",      "label": "Ø/strøm — Solcellesalg",                        "fee_dkk_kwh": 0.04},
    {"id": "norlys",            "label": "Norlys — Solcelle",                             "fee_dkk_kwh": 0.05},
]

ENERGINET_GLN = "5790000432752"          # Energinet — transmission/system tariffs
ENERGINET_TARIFF_CODES = frozenset({"40000", "41000"})
# v0.39.8 — `41000` (Systemtarif) added. Was missing prior to v0.39.8, which
# halved the Energinet contribution to `_tariff_schedule[h]`. Per the
# Strømligning breakdown for a residential DK1 customer the two components
# are transmission (40000, ~0.043 DKK/kWh) and system (41000, ~0.072
# DKK/kWh). Both are flat hourly rates updated annually.
# Excluded: 40010 (Indfødningstarif produktion, sell-side), 40020 (HV 132/150 kV),
# 40021/40023 (DK1/DK2 Nettabstarif — TSO-connected industrial), 40022 (Effekt-
# abonnement capacity charges), 40024 (begrænset netadgang), 41003 (storforbruger),
# 41004 (TSO system abonnement), 45012 (Balancetarif production).
DEFAULT_ELAFGIFT_DKK_KWH = 0.01         # Danish electricity duty (elafgift) — user-adjustable
TARIFF_SCHEDULE_REFRESH_SECONDS = 86400  # Refresh tariff schedule daily (tariffs are stable within a day)
EDS_ELSPOT_URL = "https://api.energidataservice.dk/dataset/DayAheadPrices"

# Spot price area (Nord Pool zone) — used by EDS Elspotprices fetch
CONF_PRICE_AREA = "price_area"
DEFAULT_PRICE_AREA = "DK2"  # Eastern Denmark default; DK1 for Jutland/Fyn
PRICE_AREA_OPTIONS: list[dict] = [
    {"value": "DK1", "label": "DK1 — Western Denmark (Jutland + Fyn)"},
    {"value": "DK2", "label": "DK2 — Eastern Denmark (Zealand + Copenhagen)"},
]

# Tariff fetching toggle (v0.30.1). The DatahubPricelist API is Danish-
# specific (DSO + Energinet hourly tariffs + indfødningstarif). Non-DK users
# should disable this; the manual stack still works without it. When
# disabled the daily tariff-refresh block is skipped entirely and the
# tariff_schedule stays at the seeded zero array, so per-hour tariff
# components don't get added to the buy/sell price.
CONF_TARIFF_FETCH_ENABLED = "tariff_fetch_enabled"
DEFAULT_TARIFF_FETCH_ENABLED = True   # Auto-disable when country != denmark

# FoxESS lifetime energy totals (for auto-detecting round-trip efficiency)
FOXESS_BATTERY_CHARGE_TOTAL = "sensor.foxessmodbus_battery_charge_total"
FOXESS_BATTERY_DISCHARGE_TOTAL = "sensor.foxessmodbus_battery_discharge_total"

# BMS-reported remaining energy, per battery module (FoxESS Modbus). Lets the
# integration auto-detect usable pack capacity straight from the BMS without
# waiting for a grid-charge cycle:
#     capacity = Σ kwh_remaining / (SoC / 100)
# Multi-module stacks expose one entity per module (`_bms_kwh_remaining_1`,
# `_bms_kwh_remaining_2`, …); modules that aren't installed report "unknown"
# and are skipped. The unique_id suffix is matched via discovery first; these
# well-known IDs are the fallback. Sampling is gated to the same safe
# mid-range as the grid-charge learner (CAPACITY_MIN_SOC..CAPACITY_MAX_SOC),
# which also excludes the near-full region where the BMS holds SoC flat while
# balancing and kwh_remaining lags.
FOXESS_BMS_KWH_REMAINING = [
    "sensor.foxessmodbus_bms_kwh_remaining_1",
    "sensor.foxessmodbus_bms_kwh_remaining_2",
]

# Battery capacity learning (from BMS kWh-remaining samples, with Force
# Charge cycles as a secondary source)
CAPACITY_MIN_SOC = 15               # % — don't sample below this (BMS edge effects near empty)
CAPACITY_MAX_SOC = 85               # % — don't sample above this (BMS tapers near full)
CAPACITY_MIN_DELTA_SOC = 0.3        # % — minimum SoC rise per tick to count as a sample
CAPACITY_MIN_CHARGE_KW = 0.5        # kW — minimum charge power to count as a valid sample
CAPACITY_MIN_SAMPLES = 20           # Need this many samples before trusting the learned value
CAPACITY_MAX_SAMPLES = 300          # Rolling window size
EFFICIENCY_MIN_TOTAL_KWH = 100      # kWh — minimum lifetime charge before trusting auto-efficiency
