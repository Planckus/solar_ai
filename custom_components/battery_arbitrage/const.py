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
CONF_CREATE_DASHBOARD = "create_dashboard"   # v0.51.0 — auto-create the bundled Solar AI dashboard
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

# ── EV charger backend selector (v0.57.0) ─────────────────────────────────
# The EV controller can drive the charger through one of two backends.
# OCPP and Modbus are mutually exclusive at the charger (the mode is set in
# the FoxESS app), so this is a structural choice that requires a reload.
#   "ocpp"          — embedded OCPP server (default, unchanged behaviour)
#   "foxess_modbus" — direct Modbus TCP to a FoxESS L11PMC charger
# The Modbus backend can throttle the car to single-phase (~1.4 kW min),
# which the 3-phase OCPP path cannot — the point of the feature is to follow
# small solar surpluses without the 4.14 kW three-phase floor.
CONF_EV_CHARGER_BACKEND = "ev_charger_backend"
EV_BACKEND_OCPP = "ocpp"
EV_BACKEND_FOXESS_MODBUS = "foxess_modbus"
DEFAULT_EV_CHARGER_BACKEND = EV_BACKEND_OCPP

# FoxESS Modbus charger connection (only used when backend == foxess_modbus).
CONF_FOXESS_CHARGER_HOST = "foxess_charger_host"
CONF_FOXESS_CHARGER_PORT = "foxess_charger_port"
CONF_FOXESS_CHARGER_UNIT = "foxess_charger_unit"
DEFAULT_FOXESS_CHARGER_PORT = 502
DEFAULT_FOXESS_CHARGER_UNIT = 1

# Phase-1 single-phase envelope for the Modbus backend.
# 0x3002 (max power cap) acts as the phase selector with auto-switching on:
# a value in the 1.4-4.2 kW band keeps the charger in single-phase. We write
# 3.0 kW every heartbeat to hold single-phase; the actual current is set via
# 0x3001 (6-16 A → ~1.4-3.7 kW on one phase at 230 V).
EV_MODBUS_SINGLE_PHASE_CAP_KW = 3.0
EV_MODBUS_MIN_AMPS = 6
EV_MODBUS_MAX_AMPS = 16
# Setpoints (0x3001/0x3002) expire after ~180 s (Time Validity, reg 0x3005),
# after which the charger reverts to full three-phase. The control loop
# re-asserts them every tick (cadence = CONF_EV_CONTROL_INTERVAL_SECONDS),
# which must stay well under that window.

# ── Phase 2 — 3-phase + hysteresis ────────────────────────────────────────
# The power cap selects the phase count (auto-switching on): a cap >= 4.2 kW
# runs three-phase, 1.4-4.2 kW runs single-phase. We hold 11 kW for 3-phase.
EV_MODBUS_THREE_PHASE_CAP_KW = 11.0
# Phase decision (v0.59.6): hysteresis on a ROLLING AVERAGE of the EV-available
# surplus, not the instantaneous value. The averaging window is the dwell — it
# rides out both brief clouds (won't downshift) and brief sun peaks (won't
# upshift), and unlike a countdown timer it can't be reset by a single noisy
# sample. On a choppy day where the instantaneous surplus oscillates across the
# threshold every few seconds, a reset-on-blip timer never completes its
# countdown and the charger stays stranded; an average does not have that flaw.
#
# Single-phase tops out at ~3.68 kW (16 A) and three-phase starts at 4.14 kW
# (6 A × 3). Upshift only when the average clears the 3φ floor with comfortable
# margin (so a normal dip doesn't immediately strand us below the floor), and
# downshift with a gap below that so a surplus hovering in the dead zone between
# 1φ-max and 3φ-min doesn't flap.
EV_MODBUS_UPSHIFT_KW = 5.5     # avg surplus above this → three-phase (v0.68.0: 5.0→5.5, wider margin over the 4.14 kW 3φ floor to cut up/down flapping)
EV_MODBUS_DOWNSHIFT_KW = 4.2   # avg surplus below this → single-phase
# v0.70.0 — Minimum hysteresis band. The upshift threshold is dashboard-adjustable;
# this floors how close it may sit to the downshift line, so the band can never be
# made pathologically thin. A 0.1 kW band (slider at its 4.3 minimum vs the 4.2
# downshift) gave effectively no hysteresis and flapped on any noise (12-21
# switches/hour, verified live). v0.73.0 — narrowed 0.8→0.3 (slider min 5.0→4.5) so
# users can tune closer to the 4.14 kW hardware floor; 0.3 kW is still well clear of
# the proven-bad 0.1 kW band. Effective upshift = max(DOWNSHIFT + this, slider
# value); downshift itself stays fixed (already only 60 W above the hardware floor).
EV_MODBUS_MIN_DEADBAND_KW = 0.3
# Window over which the available surplus is averaged for the phase decision.
# Longer = more stable / slower to engage 3φ; shorter = snappier upshift when sun
# returns. v0.71.0 — default lowered 300→180 s (3 min) and made dashboard-adjustable
# (ev_modbus_phase_avg_window_min). It can be this responsive because the window is
# now only a secondary smoother: the anti-flap protection is the wide band, the
# 90 s sustained import-guard, and the downshift dwell — all independent of the
# window — so a shorter window speeds the UPSHIFT while the downshift stays sticky.
EV_MODBUS_PHASE_AVG_WINDOW_SECONDS = 180
# Buffer-aware fast downshift. On three-phase, a surplus that can't hold the 4.14 kW
# 3φ floor shows up as grid import (a house battery covers a brief dip, so no import
# appears; without a battery — or with an empty one — it does). Import above this kW
# threshold, SUSTAINED for the seconds below, while on 3φ and NOT curtailing drops
# the car to 1φ. Set the kW above ordinary house-load noise.
EV_MODBUS_IMPORT_DOWNSHIFT_KW = 0.5
# v0.70.0 — Import must persist this long before the guard drops to 1φ. A full house
# battery does brief charge/discharge balancing pulses at ~100% SoC that flip the
# meter to import for ~15 s at a time even under perfectly steady sun; an
# instantaneous check bounced the phase on those blips (verified on live data:
# 0.5–0.9 kW import spikes with zero between, PV rock-steady at 7.5 kW). Requiring
# the import to be CONTINUOUS for this window filters the blips while still
# protecting a battery-less / empty-battery install, where a real shortfall imports
# without interruption. Dashboard-adjustable via ev_modbus_import_sustained_sec.
EV_MODBUS_IMPORT_SUSTAINED_SECONDS = 90
# v0.69.0 — Asymmetric anti-flap dwell on the DOWNSHIFT. Upshift (→3φ) stays fast
# (only the rolling average gates it) so the car grabs solar at once. Downshift
# (→1φ) requires the low surplus to persist this long since the last switch. The
# surplus signal SUBTRACTS battery discharge, so when a passing cloud dips PV the
# battery covers the car (no grid import — good) but the signal collapses anyway
# (e.g. 5.9→3.1 kW) and punches through the downshift line; without this dwell that
# starts a 1φ↔3φ bounce. Holding 3φ rides the dip out on battery cover. Exempt: the
# grid-import guard (no/empty battery → drop at once) and the curtailment override
# (Regime A bump-up is never delayed). Dashboard-adjustable via
# ev_modbus_downshift_dwell_min.
EV_MODBUS_DOWNSHIFT_DWELL_SECONDS = 300
# Charging-current step (v0.59.9). The Modbus current register (0x3001) has
# 0.1 A resolution; we quantise the per-phase target to this step. 1.0 = the
# historical whole-amp behaviour; finer steps track the solar surplus more
# closely (less spill to grid / draw from battery), subject to whether the EV
# itself follows sub-amp setpoints. Dashboard-selectable.
CONF_EV_MODBUS_CURRENT_STEP = "ev_modbus_current_step"
DEFAULT_EV_MODBUS_CURRENT_STEP = "1.0"
EV_MODBUS_CURRENT_STEP_OPTIONS = ["0.1", "0.5", "1.0"]
# The charger only permits a phase switch once this interval (0x300B, minutes,
# hardware minimum 5) has elapsed since the last change; a too-early downshift
# pauses the session instead of switching. This also serves as the anti-thrash
# gate between phase changes.
# v0.59.13 — verified the L11PMC accepts a 1-min value on 0x300B (the documented
# 5-min "minimum" is not hardware-enforced), so default to 1 for snappy phase
# switching. Both the hardware write and the controller's anti-thrash gate use
# this; the gate is dashboard-adjustable (the hardware write stays at this floor).
EV_MODBUS_SUSPEND_INTERVAL_MIN = 1

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
EV_OVERRIDE_RAMP_INTERVAL_SECONDS = 12          # default min seconds between up-steps (v0.59.13, dashboard-adjustable; was 30)
EV_OVERRIDE_RAMP_GRID_IMPORT_THRESHOLD_KW = 0.3 # kW grid import that triggers back-off
EV_OVERRIDE_RAMP_FREEZE_SECONDS = 120           # back-off freeze after over-commit
# v0.59.13 — after the override's three-phase attempt fails (PV can't sustain
# the 4.14 kW floor) it falls back to single-phase and retries three-phase after
# this long, in case the sun strengthens.
EV_OVERRIDE_3PH_RETRY_SECONDS = 300
# v0.54.0 — the battery-full override harvests *curtailed* PV (battery full,
# export blocked) into the EV. If the house battery is DISCHARGING above this
# threshold to cover the EV draw, there is no curtailed PV — the override's
# premise is false and it must yield, otherwise it silently drains the battery
# into the car (grid import stays ~0 because the battery, not the grid, covers
# the gap, so the grid-import back-off above never fires).
EV_OVERRIDE_RAMP_BATTERY_DISCHARGE_THRESHOLD_KW = 0.3

# v0.75.3 — fixed SoC floor for the Regime A "battery near-full" curtailment
# trigger, replacing the previous `battery_max_soc - 2` (98%) relative gate.
# Measured directly on live hardware: this battery's charge acceptance tapers
# starting around 96%, one point below what the old gate required, which
# missed a confirmed real curtailment case at 97% SoC on 2026-07-12.
EV_OVERRIDE_NEAR_FULL_SOC = 96

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

# v0.40.5 — OCPP desync watchdog / auto-heal. When the controller wants the
# EV charging (commanded > 0) but the charger isn't actually delivering power
# for a sustained period, escalate recovery instead of waiting for the user
# to replug / reboot:
#   Stage 1 (>= RESYNC s): re-sync state via TriggerMessage (StatusNotification
#           + MeterValues) and let the normal RemoteStart retry fire. Low risk.
#   Stage 2 (>= RECOVER s, rate-limited to once per RECOVER_COOLDOWN s): cycle
#           connector availability (Inoperative → Operative) to force the
#           charger out of a wedged Preparing/SuspendedEVSE/Finishing state.
#           Never applied to a live Charging session or a car-side SuspendedEV.
EV_STUCK_RESYNC_SECONDS = 60
EV_STUCK_RECOVER_SECONDS = 180
EV_STUCK_RECOVER_COOLDOWN_SECONDS = 600
# "Delivering" threshold — charger draw above this counts as actually charging.
EV_STUCK_DELIVERING_KW = 0.3

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
# v0.65.0 — the on-grid Min-SoC register. Force Discharge stops discharging to
# the grid when SoC reaches this. Solar AI raises it to the export floor while
# Force-Discharging (a HARDWARE backstop so a stalled tick can't over-sell), and
# restores the user's original value the moment it stops, so overnight HOUSE
# self-use is never blocked.
FOXESS_MIN_SOC_ON_GRID_ENTITY = "number.foxessmodbus_min_soc_on_grid"
CONF_FOXESS_MIN_SOC_ENTITY = "foxess_min_soc_entity"
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
WORK_MODE_EXPORT = "Feed-in First"  # legacy: only re-routes SOLAR surplus to grid — does NOT
                                    # discharge the battery at night. Kept for reference.
WORK_MODE_FORCE_DISCHARGE = "Force Discharge"  # actively discharges the battery to grid at the
                                               # force-discharge power — the correct mode for
                                               # battery arbitrage export (v0.47.6).

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

# v0.43.0 — prediction scorecard (M1). Pure observability: logs the optimiser's
# predicted SoC per 15-min slot vs the realised SoC so accuracy can be measured
# before any logic change is allowed to claim it improved precision.
PREDICTION_LOG_MAX = 2880             # 30 days × 96 fifteen-minute slots
PREDICTION_MAE_WINDOW_SLOTS = 672     # 7 days × 96 slots (rolling SoC-MAE window)
PREDICTION_MAE_WINDOW_SLOTS_LONG = 2880  # 30 days
# v0.46.1 — skip scorecard logging for this long after (re)start: the optimiser
# plan is cold and emits garbage predicted SoC until live inputs stabilise. A
# restart is an operational event, not a prediction to grade.
PREDICTION_WARMUP_SECONDS = 1800      # 30 min — long enough for prices/solar/SoC
                                      # + the optimiser plan to fully stabilise
                                      # after a restart before the scorecard logs

# v0.44.0 — S1: solar-forecast confidence percentile fed to the DP optimiser.
# 50 = the per-hour median (numerically identical to the prior behaviour, so the
# default is a no-op). Lower it to plan against more conservative solar (assume
# less free production) → the planner is more willing to grid-charge in cheap
# windows and less likely to over-export battery it will need on a cloudy day.
DEFAULT_SOLAR_CONFIDENCE_PCT = 50     # percentile; range enforced 10–90 by the number entity

# v0.47.0 — receding-horizon planning (A). The DP plan is re-solved at least
# this often (and on restart / tariff refresh) instead of only once per day, so
# it incorporates tomorrow's day-ahead prices as soon as they publish (~13:00)
# and adapts to the live SoC / solar through the day.
PLAN_REFRESH_SECONDS = 900            # 15 min

# v0.47.0 — dynamic self-learning discharge floor (C). When enabled, the export
# floor is set so the battery keeps enough charge to run the house (projected
# load) until the next "refill" — sunrise solar or a cheap grid window — instead
# of a fixed SoC. Clamped to a battery-health band; a learned safety margin
# self-corrects from whether the reserve actually lasted the night.
DYNAMIC_FLOOR_MIN_SOC = 20            # never reserve below this (battery health)
DYNAMIC_FLOOR_MAX_SOC = 85            # never reserve above this (leave room to arbitrage)
DYNAMIC_FLOOR_REFILL_MAX_H = 18.0     # cap the bridge horizon used for the reserve
# v0.52.0 — solar must EXCEED house load by this factor to count as a "refill"
# (covering the house), so the slow dawn ramp where solar ≈ house is still
# reserved for. Raised from 1.0 → 1.3 after a battery near-drain (the floor
# released the reserve too early at first light).
DYNAMIC_FLOOR_SOLAR_ONSET_FACTOR = 1.3
# v0.61.0 — fixed safety factor on the deterministic overnight reserve, replacing
# the self-learning margin. The learner was a band-aid over the capacity/solar/
# bridge bugs fixed in v0.60.x; with those corrected the reserve is accurate, and
# the integrator only added fragility (ratcheted on noise, was poisoned by
# post-restart SoC=0 reads). A fixed factor cannot ratchet or be poisoned.
DYNAMIC_FLOOR_RESERVE_FACTOR = 1.3
# v0.61.x step 2 — passively learn the overnight house-load forecast error and
# size the reserve factor from it (the empirical p80 of actual-vs-predicted core
# -night house energy over clean nights), clamped + falling back to the fixed
# factor until warm. The clamp+fallback guarantee the floor stays in a sane band
# no matter what the estimator does.
OVERNIGHT_START_HOUR = 22             # local hour the core-night window opens
OVERNIGHT_END_HOUR = 6                # local hour it closes (window spans midnight)
OVERNIGHT_MIN_TICKS = 60              # min 5-min ticks in the window for a usable night (~5h of 8)
OVERNIGHT_SAMPLES_MAX = 30            # rolling window of clean nightly ratios
OVERNIGHT_MIN_NIGHTS = 7             # need this many before trusting the empirical factor
OVERNIGHT_PERCENTILE = 0.80          # cover the forecast error this fraction of nights
RESERVE_FACTOR_MIN = 1.05            # clamp: never reserve less than +5 %
RESERVE_FACTOR_MAX = 1.60            # clamp: never reserve more than +60 %
RESERVE_RATIO_SANE_LO = 0.3          # drop a night whose actual/predicted ratio is wilder than this
RESERVE_RATIO_SANE_HI = 3.0

# Tier-1 model-health monitor (v0.64.0) — watches the learned models for drift,
# clamp-pinning, or persistently-wrong predictions and surfaces it (a flag +
# notification) rather than silently compensating. Detection only; it never
# changes a model. Thresholds are deliberately loose so it fires on a real
# problem, not normal variation.
MODEL_HEALTH_CAPACITY_DRIFT_FRAC = 0.25   # BMS-learned capacity vs the set value
MODEL_HEALTH_EFFICIENCY_LO = 0.72         # auto round-trip efficiency clamp-edge band
MODEL_HEALTH_EFFICIENCY_HI = 0.985
MODEL_HEALTH_SOLAR_LO = 0.35              # solar accuracy factor clamp-edge band
MODEL_HEALTH_SOLAR_HI = 1.45
MODEL_HEALTH_SOC_MAE_PCT = 12.0           # 7-day predicted-vs-actual SoC error above this = degraded
# Tier-2 self-correction (v0.66.0) — if a learner stays flagged for this many
# consecutive 5-min checks (~1 day), auto-reset it (within bounds; never touches
# a safety clamp). The user was already alerted when it first drifted.
MODEL_HEALTH_AUTORESET_STREAK = 288
# Legacy self-learning-margin constants — retained for the (now-uncalled)
# _update_discharge_margin and the one-time upgrade resets; no longer drive the
# floor.
DYNAMIC_FLOOR_MARGIN_DEFAULT = 1.10   # initial learned safety multiplier on projected load
DYNAMIC_FLOOR_MARGIN_MIN = 0.80
# v0.52.0 — raised cap 1.60 → 2.50 so the learner can reserve enough after a
# deep drain (the old cap couldn't compensate for a bad bridge estimate).
DYNAMIC_FLOOR_MARGIN_MAX = 2.50
DYNAMIC_FLOOR_MARGIN_UP = 1.05        # (legacy) — superseded by proportional learning
DYNAMIC_FLOOR_MARGIN_DOWN = 0.98      # relax slowly when it stayed well above comfort
# v0.52.0 — proportional self-learning: per percentage-point the SoC dropped
# below the comfort target, bump the reserve margin by this much (so an 11%
# arrival vs a 20% target ≈ +27%). Only relax once the day stayed this far
# above comfort.
DYNAMIC_FLOOR_MARGIN_UP_PER_PCT = 0.03
DYNAMIC_FLOOR_RELAX_HEADROOM = 15.0

# v0.45.0 — E1: when the EV is plugged in and in a forced-draw mode (or actively
# charging), the optimiser treats the next EV_SESSION_DP_HORIZON_H hours of EV
# demand as near-certain (the live session) rather than the hour-of-day
# probability. Without the car's SoC we can't know the full session length, so
# the certain window is capped; beyond it the learned hourly model resumes.
EV_SESSION_DP_HORIZON_H = 2.0

# Coordinator update intervals
DEFAULT_FAST_POLL_SECONDS = 15       # v0.36.0: dropped from 30 → 15 so Lovelace cards driven by integration sensors refresh every 15 s (configurable 10–300)
CONF_FAST_POLL_INTERVAL = "fast_poll_interval"
TARIFF_REFRESH_INTERVAL_SECONDS = 3600   # Hourly tariff/price refresh (not configurable)
# v0.59.16 — after a price refresh that produced NO usable rates (e.g. an EDS
# gap with the cache drained), retry this soon instead of waiting the full hour,
# so a transient feed outage self-heals in minutes rather than blanking prices.
PRICE_RETRY_AFTER_FAIL_SECONDS = 300     # 5 min
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
# v0.59.15 — data-sanity guard for grid-charge. When the price feed degenerates
# (e.g. a failed/garbled Energi Data Service fetch leaves only a slot or two),
# the "is now a cheap hour?" percentile test breaks down — a lone price is its
# own p25 — and the reactive fallback would grid-charge at whatever price
# happens to be loaded, even an expensive one. Require at least this many price
# slots AND a real cheap-vs-expensive range before any reactive grid-charge;
# otherwise run self-consumption only.
MIN_PRICE_SLOTS_FOR_GRID_CHARGE = 8

# Grid overcurrent protection
GRID_MAX_KW = 17.0                  # Default circuit breaker limit (kW) — user-adjustable via number entity
GRID_SAFETY_MARGIN_KW = 0.5         # Buffer below the breaker limit to avoid nuisance trips
GRID_MIN_CHARGE_KW = 0.3            # Minimum useful battery charge rate under headroom constraint
# v0.65.0 — re-cap the grid-charge power to live headroom only when it moves by
# more than this, to bound register wear (mirrors the export-limit maintainer).
CHARGE_RECAP_DEADBAND_KW = 0.5

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
# The BMS kWh-remaining register updates slowly/stickily while SoC moves live.
# Sampling capacity = kwh_remaining / (SoC/100) during active charge/discharge
# divides a stale-high kWh value by a live SoC and inflates the estimate (a
# 12.1 kWh battery drifted to ~16.9). Only sample when the battery is near idle,
# so the two readings are coherent.
CAPACITY_SAMPLE_MAX_BATTERY_KW = 0.3   # kW — skip BMS capacity sample above this charge/discharge power
EFFICIENCY_MIN_TOTAL_KWH = 100      # kWh — minimum lifetime charge before trusting auto-efficiency

# ── Disk-space alarm (v0.49.0) ────────────────────────────────────────────────
# Watches free space on the partition HA runs on (the real Pi/SD-card concern).
# Threshold is user-editable in the GUI (% free); a push fires once when free
# space first drops below it, and the alarm clears only after recovering past
# threshold + hysteresis, so a borderline reading doesn't spam notifications.
DEFAULT_DISK_ALARM_THRESHOLD_PCT = 10.0    # warn under 10% free by default
DISK_ALARM_RECOVERY_HYSTERESIS_PCT = 3.0   # clear only above threshold + 3 pts
