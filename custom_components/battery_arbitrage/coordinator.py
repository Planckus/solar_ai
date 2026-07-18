"""Data coordinator for Battery Arbitrage — the core brain."""
from __future__ import annotations

import asyncio
import logging
import shutil
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CALIBRATION_MAX_SAMPLES,
    CALIBRATION_MAX_SOC,
    CALIBRATION_MIN_CHARGE_KW,
    CONF_DSO_GLN,
    ENERGINET_TARIFF_CODES,
    DEFAULT_BATTERY_CAPACITY,
    DEFAULT_BATTERY_FLOOR_SOC,
    DEFAULT_BATTERY_MAX_SOC,
    DEFAULT_ELAFGIFT_DKK_KWH,
    DEFAULT_FAST_POLL_SECONDS,
    DEFAULT_MIN_SPREAD_ARBITRAGE,
    DEFAULT_ROUND_TRIP_EFFICIENCY,
    CONF_FAST_POLL_INTERVAL,
    DEFAULT_DSO_GLN,
    ENERGINET_GLN,
    GRID_MAX_KW,
    GRID_SAFETY_MARGIN_KW,
    GRID_MIN_CHARGE_KW,
    CHARGE_RECAP_DEADBAND_KW,
    DEFAULT_VAT_PCT,
    DEFAULT_EXPORT_FEE,
    LEARNING_TICK_INTERVAL_SECONDS,
    TARIFF_REFRESH_INTERVAL_SECONDS,
    PRICE_RETRY_AFTER_FAIL_SECONDS,
    TARIFF_SCHEDULE_REFRESH_SECONDS,
    EV_CHARGE_BLOCK_PROBABILITY,
    EV_CHARGE_THRESHOLD_W,
    EV_LEARNING_ALPHA,
    EV_MAX_KW_HIGH_POWER_FRACTION,
    EV_MAX_KW_LEARNING_ALPHA,
    HOUSE_LOAD_LEARNING_ALPHA,
    HOUSE_LOAD_OUTLIER_FACTOR,
    HOUSE_LOAD_WARM_THRESHOLD_KW,
    SEASON_SOLAR_THRESHOLD_KWH,
    SOLAR_DAILY_SAMPLES_MAX,
    DOMAIN,
    EVCC_API_BATTERY_MODE,
    EVCC_API_GRID,
    EVCC_API_SOLAR,
    EVCC_API_STATE,
    EV_MODE_NOW,
    CONF_BATTERY_CHARGE_ENTITY,
    CONF_BATTERY_CHARGE_TOTAL_ENTITY,
    CONF_BATTERY_DISCHARGE_ENTITY,
    CONF_BATTERY_DISCHARGE_TOTAL_ENTITY,
    CONF_BATTERY_SOC_ENTITY,
    CONF_CELL_TEMP_ENTITY,
    FOXESS_BATTERY_CHARGE_POWER,
    FOXESS_BATTERY_DISCHARGE_POWER,
    FOXESS_BATTERY_SOC,
    FOXESS_CELL_TEMP_LOW,
    FOXESS_FEED_IN,
    FOXESS_FORCE_CHARGE_ENTITY,
    FOXESS_FORCE_DISCHARGE_ENTITY,
    FOXESS_MIN_SOC_ON_GRID_ENTITY,
    CONF_FOXESS_MIN_SOC_ENTITY,
    FOXESS_LOAD_POWER,
    FOXESS_WORK_MODE_ENTITY,
    FOXESS_EXPORT_LIMIT_REGISTER,
    LEGACY_EXPORT_AUTOMATION,
    LOAD_HISTORY_MAX_SAMPLES,
    MIN_EXPORTABLE_KWH,
    SAVINGS_LOG_MAX_DAYS,
    MIN_GRID_CHARGE_KWH,
    MIN_PRICE_SLOTS_FOR_GRID_CHARGE,
    MODE_DISABLED,
    MODE_EXPORTING,
    MODE_GRID_CHARGING,
    MODE_NORMAL,
    SOLAR_ACCURACY_COMPARISON_W,
    SOLAR_ACCURACY_MAX_SAMPLES,
    SOLAR_ACCURACY_MIN_FORECAST_W,
    SOLAR_ACCURACY_MIN_SAMPLES,
    SOLAR_ACCURACY_WINDOW,
    SOLAR_ACCURACY_HOUR_BUCKET_MAX,
    SOLAR_ACCURACY_HOUR_MIN_SAMPLES,
    PREDICTION_LOG_MAX,
    PREDICTION_MAE_WINDOW_SLOTS,
    PREDICTION_MAE_WINDOW_SLOTS_LONG,
    PREDICTION_WARMUP_SECONDS,
    DEFAULT_SOLAR_CONFIDENCE_PCT,
    EV_SESSION_DP_HORIZON_H,
    PLAN_REFRESH_SECONDS,
    DYNAMIC_FLOOR_MIN_SOC,
    DYNAMIC_FLOOR_MAX_SOC,
    DYNAMIC_FLOOR_REFILL_MAX_H,
    DYNAMIC_FLOOR_SOLAR_ONSET_FACTOR,
    DYNAMIC_FLOOR_RESERVE_FACTOR,
    OVERNIGHT_START_HOUR,
    OVERNIGHT_END_HOUR,
    OVERNIGHT_MIN_TICKS,
    OVERNIGHT_SAMPLES_MAX,
    OVERNIGHT_MIN_NIGHTS,
    DEFAULT_RESERVE_PERCENTILE_PCT,
    RESERVE_FACTOR_MIN,
    RESERVE_FACTOR_MAX,
    RESERVE_RATIO_SANE_LO,
    RESERVE_RATIO_SANE_HI,
    MODEL_HEALTH_CAPACITY_DRIFT_FRAC,
    MODEL_HEALTH_EFFICIENCY_LO,
    MODEL_HEALTH_EFFICIENCY_HI,
    MODEL_HEALTH_SOLAR_LO,
    MODEL_HEALTH_SOLAR_HI,
    MODEL_HEALTH_SOC_MAE_PCT,
    MODEL_HEALTH_AUTORESET_STREAK,
    STORAGE_KEY,
    STORAGE_VERSION,
    DEFAULT_DISK_ALARM_THRESHOLD_PCT,
    DISK_ALARM_RECOVERY_HYSTERESIS_PCT,
    STROMLIGNING_SPOTPRICE_EX_VAT,
    TEMP_BUCKETS,
    VACATION_MIN_DURATION,
    VACATION_SHORT_WINDOW,
    VACATION_THRESHOLD,
    WORK_MODE_EXPORT,
    WORK_MODE_FORCE_DISCHARGE,
    WORK_MODE_FORCE_CHARGE,
    WORK_MODE_SELF_USE,
    EVCC_BATTERY_CHARGE,
    EVCC_BATTERY_NORMAL,
    EVCC_BATTERY_HOLD,
    EV_MODE_MIN_PV,
    FOXESS_BATTERY_CHARGE_TOTAL,
    FOXESS_BATTERY_DISCHARGE_TOTAL,
    CAPACITY_MIN_SOC,
    CAPACITY_MAX_SOC,
    CAPACITY_MIN_DELTA_SOC,
    CAPACITY_MIN_CHARGE_KW,
    CAPACITY_MIN_SAMPLES,
    CAPACITY_MAX_SAMPLES,
    CONF_SPOT_PRICE_ENTITY,
    CONF_STROMLIGNING_ENTITY,
    CONF_PRICE_AREA,
    DEFAULT_PRICE_AREA,
    EDS_ELSPOT_URL,
    DEFAULT_MAX_EXPORT_KW,
    DEFAULT_MIN_EXPORT_PRICE,
    DEFAULT_SPOT_MARKUP,
    DEFAULT_BATTERY_DEGRADATION_COST,
    DEFAULT_TERMINAL_VALUE_FALLBACK,
    CONF_SOLAR_FORECAST_SOURCE,
    CONF_FORECAST_SOLAR_ENTITY,
    CONF_SOLCAST_ENTITY,
    CONF_SOLCAST_TOMORROW_ENTITY,
    CONF_LIVE_DATA_SOURCE,
    CONF_FOXESS_GRID_IMPORT_ENTITY,
    CONF_FOXESS_GRID_EXPORT_ENTITY,
    CONF_FOXESS_PV_POWER_ENTITY,
    CONF_FOXESS_LOAD_POWER_ENTITY,
    DEFAULT_SOLAR_FORECAST_SOURCE,
    DEFAULT_LIVE_DATA_SOURCE,
    DEFAULT_EVCC_URL,
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
    CONF_EV_CONTROLLER_ENABLED,
    CONF_EV_OCPP_CHARGE_POINT_ID,
    CONF_EV_OCPP_STATUS_ENTITY,
    CONF_EV_OCPP_POWER_ENTITY,
    CONF_EV_DEFAULT_MODE,
    CONF_EV_MIN_CHARGE_KW,
    CONF_EV_MAX_CHARGE_KW,
    EV_MODE_LOCKED,
    EV_MODE_PV,
    EV_MODE_PV_BATTERY,
    EV_MODE_FULL,
    DEFAULT_EV_CONTROLLER_ENABLED,
    DEFAULT_EV_DEFAULT_MODE,
    DEFAULT_EV_MIN_CHARGE_KW,
    DEFAULT_EV_MAX_CHARGE_KW,
    EV_VOLTAGE,
    EV_PHASES,
    EV_OCPP_MIN_AMPS,
    EV_OCPP_MAX_AMPS,
    EV_HYSTERESIS_START_TICKS,
    EV_HYSTERESIS_STOP_TICKS,
    EV_MAX_AMP_STEP_PER_TICK,
    EV_MIN_AMP_CHANGE,
    EV_RATE_REASSERT_SECONDS,
    EV_STUCK_RESYNC_SECONDS,
    EV_STUCK_RECOVER_SECONDS,
    EV_STUCK_RECOVER_COOLDOWN_SECONDS,
    EV_STUCK_DELIVERING_KW,
    EV_CURTAILMENT_PROBE_SECONDS,
    EV_CURTAILMENT_PROBE_COOLDOWN_SECONDS,
    EV_OVERRIDE_SOFT_COOLDOWN_SECONDS,
    EV_OVERRIDE_RAMP_INTERVAL_SECONDS,
    EV_OVERRIDE_RAMP_GRID_IMPORT_THRESHOLD_KW,
    EV_OVERRIDE_RAMP_FREEZE_SECONDS,
    EV_OVERRIDE_RAMP_BATTERY_DISCHARGE_THRESHOLD_KW,
    EV_OVERRIDE_NEAR_FULL_SOC,
    EV_OVERRIDE_3PH_RETRY_SECONDS,
    EV_STOP_RECOVERY_SECONDS,
    EV_START_DROP_TIMEOUT_SECONDS,
    EV_COOL_ENTRY_SECONDS,
    CONF_AUTO_FULL_ON_NEGATIVE_PRICE,
    DEFAULT_AUTO_FULL_ON_NEGATIVE_PRICE,
    AUTO_FULL_DEBOUNCE_SECONDS,
    CONF_EV_CONTROL_INTERVAL_SECONDS,
    CONF_EV_START_WINDOW_SECONDS,
    CONF_EV_STOP_WINDOW_SECONDS,
    CONF_EV_CHARGE_THRESHOLD_W,
    CONF_EV_BATTERY_PRIORITY_SOC,
    CONF_OCPP_EMBEDDED,
    CONF_OCPP_PORT,
    CONF_OCPP_RESTART_STRICT,
    CONF_BUY_PRICE_MODE,
    CONF_STROMLIGNING_SUPPLIER_ID,
    CONF_STROMLIGNING_PRODUCT_ID,
    CONF_STROMLIGNING_CUSTOMER_GROUP,
    CONF_STROMLIGNING_USE_MANUAL_OVERRIDES,
    CONF_SELL_SIDE_COMPANY,
    CONF_OCTOPUS_PRODUCT_CODE,
    CONF_OCTOPUS_REGION,
    CONF_TARIFF_FETCH_ENABLED,
    DEFAULT_TARIFF_FETCH_ENABLED,
    EV_BATTERY_LOCK_POWER_THRESHOLD_KW,
    EV_MODE_SCHEDULED,
    CONF_EV_SCHEDULE_LINKS,
    CONF_EV_SCHEDULED_FALLBACK_MODE,
    DEFAULT_EV_SCHEDULED_FALLBACK_MODE,
    EV_SCHEDULE_LINKS_MAX,
    EV_SCHEDULE_LINK_MODE_OPTIONS,
    EV_SCHEDULE_LINK_MODE_STORAGE_PREFIX,
    EV_SCHEDULES_MAX,
    EV_SCHEDULE_DAYS,
    EV_SCHEDULE_DEFAULT_START,
    EV_SCHEDULE_DEFAULT_END,
    EV_SCHEDULE_DEFAULT_DAYS,
    EV_SCHEDULE_DEFAULT_MODE,
    DSO_OPTIONS,
    SELL_SIDE_COMPANY_OPTIONS,
    BUY_PRICE_MODE_MANUAL,
    BUY_PRICE_MODE_STROMLIGNING,
    BUY_PRICE_MODE_OCTOPUS,
    DEFAULT_BUY_PRICE_MODE,
    DEFAULT_SELL_SIDE_COMPANY,
    DEFAULT_OCTOPUS_REGION,
    DEFAULT_STROMLIGNING_CUSTOMER_GROUP,
    DEFAULT_STROMLIGNING_USE_MANUAL_OVERRIDES,
    STROMLIGNING_CACHE_HOURS,
    OCTOPUS_CACHE_HOURS,
    DEFAULT_EV_CONTROL_INTERVAL_SECONDS,
    DEFAULT_EV_START_WINDOW_SECONDS,
    DEFAULT_EV_STOP_WINDOW_SECONDS,
    DEFAULT_EV_CHARGE_THRESHOLD_W,
    DEFAULT_EV_BATTERY_PRIORITY_SOC,
    DEFAULT_OCPP_EMBEDDED,
    DEFAULT_OCPP_PORT,
    EFFICIENCY_MIN_TOTAL_KWH,
)

_LOGGER = logging.getLogger(__name__)

# Danish market timezone (DST-aware). Used to interpret EDS/tariff local-time
# stamps and to derive local hours. Defined once here rather than rebuilt in
# each function that needs it.
_CPH_TZ = ZoneInfo("Europe/Copenhagen")


class BatteryArbitrageCoordinator(DataUpdateCoordinator):
    """Coordinator: fetches data, runs model, executes decisions."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        fast_poll = int(config.get(CONF_FAST_POLL_INTERVAL, DEFAULT_FAST_POLL_SECONDS))
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=fast_poll),
        )
        self.config = config
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._stored: dict[str, Any] = {}
        # v0.49.0 — disk-space alarm: latest reading + latched alarm state
        self._disk_usage: dict[str, Any] = {}
        self._disk_low: bool = False
        self._current_mode = MODE_NORMAL
        self._mode_reason = ""
        # v0.41.0 — language for user-facing strings (reasons, notifications).
        # Follows HA's configured language: Danish HA → Danish, anything else
        # → English. Display/notification text only; no behavioural effect.
        self._lang = "da" if str(getattr(hass.config, "language", "") or "").lower().startswith("da") else "en"
        self._enabled = False        # OFF by default — user enables after learning period
        self._we_set_evcc_mode = False  # True while WE have EVCC battery mode set non-normal
        self._prev_soc: float | None = None  # Previous tick SoC for capacity learning
        # Split-poll cache: tariff data refreshed hourly, live state refreshed every tick
        self._cached_solar_rates: dict[str, Any] = {}
        self._cached_grid_rates: dict[str, Any] = {}
        self._last_tariff_refresh: datetime | None = None
        # DSO tariff schedule: 24-entry list (index = local hour), refreshed daily
        self._tariff_schedule: list[float] = [0.0] * 24
        self._last_tariff_schedule_refresh: datetime | None = None
        # Feed-in tariff components (flat-rate, refreshed daily with tariff schedule)
        self._feed_in_tariff_dso: float = 0.0
        self._feed_in_tariff_energinet: float = 0.0
        # Strømligning cache (v0.29.0). Keyed by slot start ISO timestamp →
        # per-15-min breakdown returned by /api/prices. Refreshed once per day
        # alongside the tariff schedule. Empty in manual mode.
        self._cached_stromligning_prices: dict[str, dict] = {}
        self._last_stromligning_refresh: datetime | None = None
        # EDS day-ahead spot-price cache (v0.59.4). Last good rate list, so a
        # restart — or a failed/garbled/rate-limited fetch right after one —
        # falls back to the last known prices instead of blanking the plan.
        self._cached_eds_rates: list[dict] = []
        self._last_eds_refresh: datetime | None = None
        # v0.59.16 — whether the last price refresh yielded usable rates. False
        # ⇒ retry sooner (PRICE_RETRY_AFTER_FAIL_SECONDS) instead of the full
        # hourly interval, so a transient feed gap self-heals in minutes.
        self._last_tariff_fetch_ok: bool = True
        # v0.59.19 — edge-detect the price-data-degraded notification.
        self._prev_price_degraded: bool = False
        # Tier-1 model-health monitor (v0.64.0): cached issue list (recomputed on
        # the 5-min learning tick) + edge-tracking for the notification.
        self._model_health_issues: list[str] = []
        # v0.75.13 — informational notes, distinct from issues: conditions
        # worth surfacing but that don't warrant the "Problem" severity or
        # the attention-needed notification (e.g. reserve factor pinned at
        # its MINIMUM, which is plausibly good news — a very predictable
        # house — not a data-quality problem the way pinning at MAXIMUM is).
        self._model_health_notes: list[str] = []
        self._prev_model_unhealthy: bool = False
        # v0.66.0 Tier-2 — consecutive checks the capacity learner has been drifted,
        # for the bounded auto-reset circuit breaker.
        self._capacity_drift_streak: int = 0
        # v0.65.0 — last grid-charge power cap actually written, so the per-cycle
        # maintainer only re-writes when live headroom moves materially.
        self._last_charge_cap_kw: float | None = None
        # v0.65.0 — effective export floor (max of the user floor and the dynamic
        # reserve), updated each cycle; _transition_to reads it to set the
        # hardware min-SoC backstop on Force Discharge.
        self._effective_floor_soc: float = float(DEFAULT_BATTERY_FLOOR_SOC)
        # Octopus Energy cache (v0.30.0). Keyed by valid_from ISO timestamp →
        # per-30-min rate entry from /standard-unit-rates. Empty when the
        # buy-price mode is not "octopus".
        self._cached_octopus_prices: dict[str, dict] = {}
        self._last_octopus_refresh: datetime | None = None
        # Learning tick gate: storage-write operations run every 5 min, not every fast tick
        self._last_learning_tick: datetime | None = None
        self._vacation_mode: bool = False  # Cached between learning ticks
        # Export limit tracker — avoids unnecessary register writes; -1 forces first write
        self._last_export_limit: int = -1
        # Day-ahead DP optimizer plan — list of {hour, action, soc, buy, sell}
        self._optimizer_plan: list[dict] = []
        # v0.43.0 — prediction scorecard (M1): the 15-min slot currently being
        # tracked. On rollover we log the plan's predicted SoC vs the realised
        # SoC for the slot that just closed. Not persisted (re-derived on start).
        self._sc_slot_start: datetime | None = None
        # v0.46.1 — when this coordinator instance started, so the scorecard can
        # skip the post-restart warm-up window (cold optimiser plan).
        self._started_at: datetime = datetime.now(timezone.utc)
        # v0.47.0 — receding-horizon planning: timestamp of the last DP re-solve.
        self._last_plan_refresh: datetime | None = None
        # v0.47.0 — dynamic discharge floor: last computed value + bridge state.
        self._dynamic_floor_soc: float | None = None
        # Currently open export/charge session (closed when mode exits)
        self._open_action: dict | None = None
        # Currently open solar-floor-blocked event (closed when price rises
        # back above the floor and solar export resumes)
        # v0.36.0: renamed from `_open_floor_block` to `_current_floor_block`
        # to stop it shadowing the `_open_floor_block` method of the same
        # name. The method opens a block by setting this attribute; reading
        # this attribute tells you whether a block is currently active.
        self._current_floor_block: dict | None = None
        # EV charge controller state (Phase B1 → v0.26.0 time-based)
        self._ev_active_mode: str = EV_MODE_LOCKED          # what the user has selected
        # v0.36.0 — when `_ev_active_mode == EV_MODE_SCHEDULED`, the resolver
        # walks the configured schedule links once per tick and stores the
        # concrete operating mode here. Downstream code (battery lock,
        # anti-flap, telemetry) reads `_ev_effective_mode`. For all other
        # values of `_ev_active_mode`, `_ev_effective_mode` mirrors it.
        self._ev_effective_mode: str = EV_MODE_LOCKED
        self._ev_active_schedule_link: str | None = None     # entity_id of the schedule currently in control
        self._ev_last_amps: int = 0                          # last A we commanded
        self._ev_last_rate_assert_ts: datetime | None = None  # v0.40.2 periodic re-assert
        # v0.40.5 — OCPP desync watchdog state
        self._ev_stuck_since_ts: datetime | None = None       # want-charge-but-not-delivering since
        self._ev_last_resync_ts: datetime | None = None       # last Stage-1 TriggerMessage re-sync
        self._ev_last_recover_ts: datetime | None = None      # last Stage-2 availability cycle
        # Legacy tick counters kept for set_ev_mode() back-compat reset only
        self._ev_above_start_count: int = 0
        self._ev_below_stop_count: int = 0
        # v0.75.4 — set by set_ev_mode() on an actual mode change; consumed
        # (one-shot) by the next _apply_ev_time_window() call to bypass the
        # start/stop anti-flap windows for that single tick. Those windows
        # exist to ride out cloud-flicker on the surplus signal, not to delay
        # a deliberate mode switch — without this, switching e.g. pv_battery
        # → pv while charging held the old rate for a full stop_window
        # (default 180s), covered by the battery in the meantime.
        self._ev_mode_change_pending: bool = False
        # Time-based hysteresis (v0.26.0): timestamps mark when surplus first
        # crossed above/below the min-charge threshold. Cleared on the opposite
        # crossing. The control loop only flips state once the elapsed time
        # exceeds start_window / stop_window seconds.
        self._ev_surplus_above_min_since_ts: datetime | None = None
        self._ev_surplus_below_min_since_ts: datetime | None = None
        # v0.38.5 — When idle with a start timer (`_ev_surplus_above_min_since_ts`)
        # running, this tracks when surplus first dropped back below min.
        # Cleared on any tick where surplus is back above min while idle.
        # If the drop is sustained for EV_START_DROP_TIMEOUT_SECONDS, the
        # start timer is cleared (genuine drop). Brief blips don't reset
        # it — mirror image of the v0.38.3 stop-recovery logic.
        self._ev_arm_drop_since_ts: datetime | None = None
        # v0.39.11 — Entry-debounce timestamp. When charging and surplus first
        # drops below min, this records the first below-min tick. Only when
        # the drop has been sustained for EV_COOL_ENTRY_SECONDS do we set
        # `_ev_surplus_below_min_since_ts` (which drives the COOLING state
        # name). Cleared on any above-min recovery while still in CHARGING
        # (before the formal stop timer arms). Mirror of the v0.38.3
        # stop-recovery guard in the opposite direction.
        self._ev_cool_entry_ts: datetime | None = None
        # v0.39.0 — Auto-promote-to-Full on negative buy price state.
        # When `auto_full_on_negative_price` is enabled and the buy price
        # has been ≤ 0 for AUTO_FULL_DEBOUNCE_SECONDS, the coordinator
        # auto-saves the current master mode and switches to Full. On the
        # floor-block-close edge, the previous mode is restored. If the
        # user manually changes mode while in auto-Full, the auto state
        # is cleared and stays cleared until the next negative-price
        # event. Reset on EV disconnect.
        self._ev_neg_price_seen_since_ts: datetime | None = None
        self._ev_auto_full_active_since_ts: datetime | None = None
        self._ev_pre_auto_full_mode: str | None = None
        # Tracks the floor-block state on the prior tick, so we can
        # detect the active → inactive edge that triggers auto-revert.
        self._ev_prev_floor_block_active: bool = False
        self._ev_prev_connected: bool = False               # last known plug state
        self._ev_last_reason: str = ""                      # human-readable status
        # Battery-lock state (v0.27.2): when EV is FULL-mode charging, we
        # set house battery max_discharge_current to 0 so the EV's grid demand
        # isn't supplemented by raiding the house battery. Battery can still
        # charge from solar — only the discharge path is blocked.
        self._ev_battery_locked: bool = False
        self._ev_battery_lock_prev_a: float | None = None
        # ── Short-term solar correction (v0.28.6) ────────────────────────
        # Intra-hour Kalman-style residual: compare actual mean PV in each
        # closed 15-min slot against the Solcast forecast for that slot,
        # and apply the rolling ratio as a short-horizon multiplier on top
        # of the existing 4-day per-hour accuracy factor — only for slots
        # within the next 2 h, with linear decay.
        self._st_solar_slot_start: datetime | None = None
        self._st_solar_pv_sum_w: float = 0.0          # running sum of PV W readings
        self._st_solar_pv_count: int = 0              # running count
        self._st_solar_forecast_sum_w: float = 0.0    # paired forecast sum
        self._st_solar_forecast_count: int = 0
        # Ring of recent (slot_end_iso, actual_w, forecast_w, ratio) tuples
        # Capped at 8 = last 2 h of 15-min slots.
        self._st_solar_residuals: list[dict] = []
        # Current short-term multiplier (rolling mean of last 4 = 1 h)
        self._st_solar_factor: float = 1.0
        # Slot-mean accumulation is restricted to daylight (actual PV OR
        # forecast must exceed this floor — avoids nightly division-by-zero)
        self._st_solar_min_w: float = 200.0
        # Horizon over which the short-term correction decays back to 1.0
        self._st_solar_decay_hours: float = 2.0
        # v0.38.4 — Sticky flag: True if the solar export floor was active
        # at ANY tick during the current accumulating 15-min slot. When True
        # at slot rollover, the slot's residual is discarded — the actual
        # PV reading was clipped by the export-limit register, so the
        # actual/forecast ratio is artificially small. Mirrors the v0.30.1
        # filter that was added for the per-hour accuracy learner; without
        # it, a 2-hour midday floor block could clamp `_st_solar_factor` to
        # 0.3 for the next 2 hours, skewing the "justeret" forecast even
        # after the floor closed.
        self._st_solar_floor_seen_during_slot: bool = False
        # Diagnostic — ISO timestamp of the most recent slot we skipped
        # because of curtailment. None = never. Exposed on the data dict
        # so the dashboard can confirm the filter is firing.
        self._st_solar_last_curtailed_skip_iso: str | None = None
        # v0.36.2 — PV-curtailment signal cached from the inverter's
        # "PV Power Limited Flag" holding register (49251). Updated once
        # per coordinator slow tick by `_async_update_data`. Consumed by
        # `_run_ev_controller` to decide whether to launch a curtailment
        # probe (replaces the v0.30.1 forecast-substitution heuristic).
        # v0.39.17 — still read into solar-accuracy learner as a
        # curtailment signal; no longer drives the EV probe (the probe
        # was replaced by a battery-full override that doesn't depend on
        # this flag, since it proved unreliable on real installs).
        self._pv_power_limited_flag: bool = False
        # v0.39.17 — Cool-down field reused from the old v0.36.2 probe
        # state machine.
        # v0.39.18 — Now set by the battery-full override's soft
        # cool-down: every time an override-induced charging session
        # ends (for any reason), this is set to now + 10 min. Prevents
        # rapid on/off cycling during partly-cloudy periods.
        # Cleared on EV disconnect so the next plug-in is a fresh start.
        self._ev_probe_cooldown_until: datetime | None = None
        # v0.39.18 — Tracks whether the EV's current charging session
        # was started or sustained by the battery-full override. Set
        # True on any tick where the override forces target up to min.
        # Cleared when EV goes IDLE (ev_last_amps drops to 0), on EV
        # disconnect, and when the soft cool-down is applied. Used to
        # decide whether to engage the soft cool-down when the session
        # ends.
        self._ev_session_was_override_induced: bool = False
        # v0.39.21 — Active-ramp state for the battery-full override.
        # `_ev_override_ramp_amps` is the current commanded ceiling in amps
        # (0 = inactive/uninitialised; initialises to min on the first
        # override tick of a session). The controller nudges it up 1 A at a
        # time while grid import stays low, and backs off when it doesn't.
        self._ev_override_ramp_amps: int = 0
        self._ev_override_ramp_last_step_ts: datetime | None = None
        self._ev_override_ramp_freeze_until: datetime | None = None
        # Decoupled EV control loop: runs at CONF_EV_CONTROL_INTERVAL_SECONDS
        # cadence (independent of the main coordinator fast-poll). Inputs are
        # cached by the main update; the loop consumes the cache.
        self._ev_control_task = None                        # asyncio.Task | None
        self._cached_ev_inputs: dict | None = None
        self._latest_ev_telemetry: dict = {
            "ev_enabled": False,
            "ev_reason": "EV control loop initialising",
        }
        # Embedded OCPP server (v0.27.0). Started in __init__.py's
        # async_setup_entry, stopped in async_unload_entry. None until then.
        self.ocpp_server = None  # type: ignore[assignment]
        # FoxESS Modbus charger backend (v0.57.0). Lazily built by
        # `_get_modbus_backend` when the charger backend is foxess_modbus.
        self._ev_modbus_backend = None  # type: ignore[assignment]
        self._ev_modbus_backend_key = None  # (host, port, unit) the backend was built for
        # Phase 2: commanded phase mode (1 or 3) and when it last changed, for
        # hysteresis + the hardware suspend-interval gate.
        self._ev_modbus_phase = 1
        self._ev_modbus_phase_since_ts = None
        self._ev_modbus_avail_hist: list[float] = []  # last few available-surplus reads (median filter)
        # Phase decision (v0.59.6): rolling window of (timestamp, surplus) over
        # EV_MODBUS_PHASE_AVG_WINDOW_SECONDS — the average drives the 1φ/3φ
        # choice, replacing the reset-on-blip dwell timers.
        self._ev_modbus_phase_avg_hist: list[tuple] = []
        # Battery-full override grid-drain guard (v0.59.10): when the override
        # ramp is pinned at min but still importing, this marks when that started
        # so a sustained failure to lift MPPT trips the cool-down.
        self._ev_modbus_override_fail_since_ts = None
        # v0.59.13 — when the override's three-phase attempt can't be sustained
        # (PV < 4.14 kW), three-phase is blocked until this time and the override
        # falls back to single-phase; it retries three-phase afterwards.
        self._ev_modbus_override_3ph_blocked_until = None
        # v0.70.0 — when on 3φ and importing, the timestamp the import started; the
        # grid-import guard only drops to 1φ once import has been continuous for
        # EV_MODBUS_IMPORT_SUSTAINED_SECONDS (filters brief battery-balancing blips).
        self._ev_modbus_import_since_ts = None

    # ------------------------------------------------------------------ #
    # Public helpers                                                        #
    # ------------------------------------------------------------------ #

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        self._stored["enabled"] = value
        # Persist asynchronously (setters can't be awaited)
        if self.hass:
            self.hass.async_create_task(self._store.async_save(self._stored))

    @property
    def current_mode(self) -> str:
        return self._current_mode

    @property
    def mode_reason(self) -> str:
        return self._mode_reason

    def _setting(self, key: str, default):
        """Read a parameter-like structural setting, allowing a live dashboard
        override via `_stored` (falls back to the config entry, then the
        default). v0.56.0 — backs the config `select` entities (data source,
        solar source, buy-price mode, price area). These are read per coordinator
        cycle, so a change takes effect on the next update with no reconfigure.
        """
        return self._stored.get(key, self.config.get(key, default))

    def get_learned_rate(self, bucket_key: str) -> float:
        """Return the learned max charge rate (kW) for a temperature bucket."""
        rates = self._stored.get("charge_rates", {})
        for key, _, _, default in TEMP_BUCKETS:
            if key == bucket_key:
                return rates.get(key, default)
        return 0.0

    def get_all_learned_rates(self) -> dict[str, float]:
        rates = self._stored.get("charge_rates", {})
        return {key: rates.get(key, default) for key, _, _, default in TEMP_BUCKETS}

    def get_current_temp_bucket(self) -> str | None:
        temp = self._get_float_state(self.config.get(CONF_CELL_TEMP_ENTITY, FOXESS_CELL_TEMP_LOW))
        if temp is None:
            return None
        return _temp_bucket(temp)

    def get_current_charge_rate(self) -> float:
        bucket = self.get_current_temp_bucket()
        if bucket is None:
            return 0.0
        return self.get_learned_rate(bucket)

    def get_effective_charge_rate(self) -> float:
        """Continuously-learned *sustained* charge rate (kW) for the current
        temperature bucket — the mean of the observed force-charge power samples,
        not the p90 *peak* that get_learned_rate returns.

        A planned grid-charge never holds the peak across a whole slot — it ramps
        up, tapers near full, and is throttled by grid headroom — so the energy
        it actually delivers is governed by the sustained mean, not the peak.
        The floor uses this to credit a planned charge with the energy it will
        realistically return. It learns continuously from the same samples
        `_calibrate_charge_rate` already collects, and rolls with them, so it
        tracks seasonal/temperature changes. Falls back to the learned peak rate
        until samples exist (the only estimate available; the margin learner
        backstops the cold start)."""
        bucket = self.get_current_temp_bucket()
        if bucket is None:
            return 0.0
        samples = self._stored.get("charge_samples", {}).get(bucket, [])
        if samples:
            return round(sum(samples) / len(samples), 3)
        return self.get_learned_rate(bucket)

    def get_savings_summary(self) -> dict[str, float]:
        """Aggregate savings_log into today / 7-day / 30-day totals."""
        log: list[dict] = self._stored.get("savings_log", [])
        today_str = datetime.now().date().isoformat()
        week_ago = (datetime.now().date() - timedelta(days=7)).isoformat()
        month_ago = (datetime.now().date() - timedelta(days=30)).isoformat()
        totals = dict(
            savings_actual_today=0.0, savings_missed_today=0.0,
            savings_actual_week=0.0,  savings_missed_week=0.0,
            savings_actual_month=0.0, savings_missed_month=0.0,
        )
        for entry in log:
            d = entry["date"]
            a = entry.get("actual_dkk", 0.0)
            m = entry.get("missed_dkk", 0.0)
            if d == today_str:
                totals["savings_actual_today"] += a
                totals["savings_missed_today"] += m
            if d >= week_ago:
                totals["savings_actual_week"] += a
                totals["savings_missed_week"] += m
            if d >= month_ago:
                totals["savings_actual_month"] += a
                totals["savings_missed_month"] += m
        return {k: round(v, 2) for k, v in totals.items()}

    def get_actual_savings_summary(self) -> dict:
        """Actual total saving the system delivers (v0.67.0):
            savings = baseline house cost − grid import cost + export revenue
        summed per day. Returns today, all-time, and the user-set date range
        (the date pickers). 'All-time' covers only the days that have a baseline
        entry — i.e. since this tracking started — so it's never skewed by the
        older import/export history that predates it."""
        def by_date(key: str) -> dict[str, float]:
            return {e["date"]: e.get("dkk", 0.0)
                    for e in self._stored.get(key, []) if "date" in e}
        base = by_date("baseline_cost_log")
        imp = by_date("import_cost_log")
        exp = by_date("export_income_log")

        def savings(lo: str | None, hi: str | None) -> float:
            s = 0.0
            for d, b in base.items():   # baseline dates bound the period
                if (lo is None or d >= lo) and (hi is None or d <= hi):
                    s += b - imp.get(d, 0.0) + exp.get(d, 0.0)
            return round(s, 2)

        today_d = datetime.now().date()
        today = today_d.isoformat()
        # Default range = last 30 days (kept consistent with the date pickers).
        start = self._stored.get("savings_range_start") or (today_d - timedelta(days=30)).isoformat()
        end = self._stored.get("savings_range_end") or today
        return {
            "actual_savings_today": savings(today, today),
            "actual_savings_total": savings(None, None),
            "actual_savings_range": savings(start, end),
            "actual_savings_range_start": start,
            "actual_savings_range_end": end,
            "actual_savings_days": len(base),
        }

    def get_export_income_summary(self) -> dict:
        """Cumulative export income + today / 7-day / 30-day / month / year
        totals, plus the daily series for charting (v0.42.0)."""
        ilog: list[dict] = self._stored.get("export_income_log", [])
        today = datetime.now().date()
        today_str = today.isoformat()
        week_ago = (today - timedelta(days=7)).isoformat()
        month_ago = (today - timedelta(days=30)).isoformat()
        month_prefix = today.strftime("%Y-%m")
        year_prefix = str(today.year)
        t = dict(
            export_income_today=0.0, export_income_7d=0.0, export_income_30d=0.0,
            export_income_month=0.0, export_income_year=0.0,
        )
        for e in ilog:
            d = e.get("date", "")
            v = e.get("dkk", 0.0)
            if d == today_str:
                t["export_income_today"] += v
            if d >= week_ago:
                t["export_income_7d"] += v
            if d >= month_ago:
                t["export_income_30d"] += v
            if d.startswith(month_prefix):
                t["export_income_month"] += v
            if d.startswith(year_prefix):
                t["export_income_year"] += v
        out = {k: round(v, 2) for k, v in t.items()}
        out["export_income_total"] = round(self._stored.get("export_income_total", 0.0), 2)
        out["export_income_daily"] = list(ilog)
        return out

    def get_grid_balance_summary(self) -> dict:
        """Grid IMPORT cost (all import — house + battery charging) and the NET
        grid balance (export income − import cost) over today / 7d / 30d /
        month / year, plus the daily net series. v0.48.0."""
        clog: list[dict] = self._stored.get("import_cost_log", [])
        today = datetime.now().date()
        today_str = today.isoformat()
        week_ago = (today - timedelta(days=7)).isoformat()
        month_ago = (today - timedelta(days=30)).isoformat()
        month_prefix = today.strftime("%Y-%m")
        year_prefix = str(today.year)
        imp = dict(
            import_cost_today=0.0, import_cost_7d=0.0, import_cost_30d=0.0,
            import_cost_month=0.0, import_cost_year=0.0,
        )
        for e in clog:
            d = e.get("date", "")
            v = e.get("dkk", 0.0)
            if d == today_str:
                imp["import_cost_today"] += v
            if d >= week_ago:
                imp["import_cost_7d"] += v
            if d >= month_ago:
                imp["import_cost_30d"] += v
            if d.startswith(month_prefix):
                imp["import_cost_month"] += v
            if d.startswith(year_prefix):
                imp["import_cost_year"] += v
        out = {k: round(v, 2) for k, v in imp.items()}
        out["import_cost_total"] = round(self._stored.get("import_cost_total", 0.0), 2)
        out["import_cost_daily"] = list(clog)
        # Net = export income − import cost, per period.
        exp = self.get_export_income_summary()
        for p in ("today", "7d", "30d", "month", "year", "total"):
            out[f"net_grid_{p}"] = round(
                exp.get(f"export_income_{p}", 0.0) - out[f"import_cost_{p}"], 2,
            )
        # Daily net series (export − import, merged by date) for charting.
        exp_by_date = {e["date"]: e.get("dkk", 0.0) for e in exp.get("export_income_daily", [])}
        imp_by_date = {e["date"]: e.get("dkk", 0.0) for e in clog}
        dates = sorted(set(exp_by_date) | set(imp_by_date))
        out["net_grid_daily"] = [
            {"date": d, "dkk": round(exp_by_date.get(d, 0.0) - imp_by_date.get(d, 0.0), 4)}
            for d in dates
        ]
        return out

    def get_solar_accuracy_factor(self) -> float:
        """Return the rolling median of actual/forecast ratio (clamped 0.3–1.5)."""
        samples = self._stored.get("solar_accuracy_samples", [])
        if len(samples) < SOLAR_ACCURACY_MIN_SAMPLES:
            return 1.0
        ratios = []
        for s in samples[-SOLAR_ACCURACY_WINDOW:]:
            f = s.get("f", 0)
            a = s.get("a", 0)
            if f >= SOLAR_ACCURACY_COMPARISON_W:
                ratios.append(a / f)
        if len(ratios) < 6:
            return 1.0
        factor = statistics.median(ratios)
        return round(max(0.3, min(1.5, factor)), 3)

    def reset_learned_rates(self) -> None:
        """Reset all learned charge rates and history to defaults."""
        self._stored["charge_rates"] = {
            key: default for key, _, _, default in TEMP_BUCKETS
        }
        self._stored["charge_samples"] = {key: [] for key, _, _, _ in TEMP_BUCKETS}
        self._stored["load_history"] = []
        self._stored["solar_accuracy_samples"] = []
        self._stored["capacity_samples"] = []
        self._prev_soc = None
        self.hass.async_create_task(self._store.async_save(self._stored))

    # ------------------------------------------------------------------ #
    # Storage                                                               #
    # ------------------------------------------------------------------ #

    async def async_load_storage(self) -> None:
        data = await self._store.async_load()
        if data is None:
            self._stored = {
                "charge_rates": {key: default for key, _, _, default in TEMP_BUCKETS},
                "charge_samples": {key: [] for key, _, _, _ in TEMP_BUCKETS},
                "load_history": [],
                "vacation_counter": 0,
                "solar_accuracy_samples": [],
                "solar_accuracy_by_hour": {str(h): [] for h in range(24)},
                "savings_log": [],
                "battery_floor_soc": int(self.config.get("battery_floor_soc", DEFAULT_BATTERY_FLOOR_SOC)),
                "battery_max_soc": int(self.config.get("battery_max_soc", DEFAULT_BATTERY_MAX_SOC)),
                "min_spread_arbitrage": float(self.config.get("min_spread_arbitrage", DEFAULT_MIN_SPREAD_ARBITRAGE)),
                "grid_max_kw": float(GRID_MAX_KW),
                "vat_pct": DEFAULT_VAT_PCT,
                "export_fee": DEFAULT_EXPORT_FEE,
                "elafgift": DEFAULT_ELAFGIFT_DKK_KWH,
                "spot_markup": DEFAULT_SPOT_MARKUP,
                "max_export_kw": DEFAULT_MAX_EXPORT_KW,
                "min_export_price": DEFAULT_MIN_EXPORT_PRICE,
                "notifications_enabled": False,
                "ev_charge_hourly": [0.0] * 24,
                "solar_daily_kwh": [],
                "solar_today_kwh": 0.0,
                "solar_today_date": "",
                "ev_min_charge_kw": DEFAULT_EV_MIN_CHARGE_KW,
                "ev_max_charge_kw": DEFAULT_EV_MAX_CHARGE_KW,
                "ev_active_mode": self.config.get(CONF_EV_DEFAULT_MODE, DEFAULT_EV_DEFAULT_MODE),
            }
        else:
            self._stored = data
            # Ensure all keys exist (migration safety)
            self._stored.setdefault("charge_rates", {key: default for key, _, _, default in TEMP_BUCKETS})
            self._stored.setdefault("charge_samples", {key: [] for key, _, _, _ in TEMP_BUCKETS})
            self._stored.setdefault("load_history", [])
            self._stored.setdefault("vacation_counter", 0)
            self._stored.setdefault("solar_accuracy_samples", [])
            # Per-hour buckets — keys are str("0".."23"), values are sample lists
            self._stored.setdefault("solar_accuracy_by_hour", {str(h): [] for h in range(24)})
            self._stored.setdefault("savings_log", [])
            self._stored.setdefault("action_log", [])
            self._stored.setdefault("solar_floor_log", [])
            self._stored.setdefault("ev_charge_hourly", [0.0] * 24)
            self._stored.setdefault("ev_max_kw", 0.0)
            self._stored.setdefault("house_load_hourly", [0.0] * 24)
            # v0.46.0 — L1: split the load profile into weekday vs weekend.
            # Seed both from the legacy combined profile on first upgrade so the
            # model isn't cold after the migration.
            legacy_load = self._stored.get("house_load_hourly", [0.0] * 24)
            if "house_load_weekday" not in self._stored:
                self._stored["house_load_weekday"] = list(legacy_load)
            if "house_load_weekend" not in self._stored:
                self._stored["house_load_weekend"] = list(legacy_load)
            # v0.46.1 — one-time clear of the early prediction_log: the first
            # day's samples were dominated by cold-plan restart artifacts
            # (today's deploy storm). Reset once for a clean scorecard baseline;
            # the warm-up guard prevents new contamination going forward.
            if not self._stored.get("prediction_log_reset_v0461"):
                self._stored["prediction_log"] = []
                self._stored["prediction_log_reset_v0461"] = True
            self._stored.setdefault("solar_daily_kwh", [])
            self._stored.setdefault("solar_today_kwh", 0.0)
            self._stored.setdefault("solar_today_date", "")
            # Seed thresholds from config on first upgrade (slider takes over after)
            self._stored.setdefault(
                "battery_floor_soc",
                int(self.config.get("battery_floor_soc", DEFAULT_BATTERY_FLOOR_SOC)),
            )
            self._stored.setdefault(
                "battery_max_soc",
                int(self.config.get("battery_max_soc", DEFAULT_BATTERY_MAX_SOC)),
            )
            self._stored.setdefault(
                "min_spread_arbitrage",
                float(self.config.get("min_spread_arbitrage", DEFAULT_MIN_SPREAD_ARBITRAGE)),
            )
            self._stored.setdefault("grid_max_kw", float(GRID_MAX_KW))
            self._stored.setdefault("capacity_samples", [])
            self._stored.setdefault("vat_pct", DEFAULT_VAT_PCT)
            self._stored.setdefault("export_fee", DEFAULT_EXPORT_FEE)
            self._stored.setdefault("elafgift", DEFAULT_ELAFGIFT_DKK_KWH)
            self._stored.setdefault("spot_markup", DEFAULT_SPOT_MARKUP)
            self._stored.setdefault("max_export_kw", DEFAULT_MAX_EXPORT_KW)
            self._stored.setdefault("min_export_price", DEFAULT_MIN_EXPORT_PRICE)
            self._stored.setdefault("notifications_enabled", False)
            self._stored.setdefault("notify_export_start", False)
            self._stored.setdefault("notify_export_stop", False)
            self._stored.setdefault("notify_charge_start", False)
            self._stored.setdefault("notify_charge_stop", False)
            self._stored.setdefault("notify_solar_floor_blocked", False)
            self._stored.setdefault("notify_solar_floor_resumed", False)
            # v0.49.0 — disk-space alarm (default ON: it's a safety alert)
            self._stored.setdefault("notify_disk_low", True)
            self._stored.setdefault("disk_alarm_threshold_pct", DEFAULT_DISK_ALARM_THRESHOLD_PCT)
            self._stored.setdefault("notify_targets", [])
            self._stored.setdefault("battery_degradation_cost", DEFAULT_BATTERY_DEGRADATION_COST)
            # EV charge controller (Phase B1)
            self._stored.setdefault("ev_min_charge_kw", DEFAULT_EV_MIN_CHARGE_KW)
            self._stored.setdefault("ev_max_charge_kw", DEFAULT_EV_MAX_CHARGE_KW)
            # Active mode is restored if previously saved; otherwise default
            self._stored.setdefault(
                "ev_active_mode",
                self.config.get(CONF_EV_DEFAULT_MODE, DEFAULT_EV_DEFAULT_MODE),
            )
            # v0.37.0 — seed per-slot schedule-link mode overrides from the
            # config-entry link list. After this point the dashboard select
            # entities are the canonical source; the link dict's `mode` field
            # is treated as the initial value only.
            links = self.config.get(CONF_EV_SCHEDULE_LINKS, []) or []
            for idx, link in enumerate(links, start=1):
                if not isinstance(link, dict):
                    continue
                seeded = link.get("mode")
                if not seeded:
                    continue
                self._stored.setdefault(
                    f"{EV_SCHEDULE_LINK_MODE_STORAGE_PREFIX}{idx}_mode", seeded,
                )
            # v0.38.0 — native schedules. Migrate from v0.36.x/v0.37.x
            # ev_schedule_links + linked schedule.* helpers if present;
            # otherwise initialise as an empty list. Schedules are now
            # owned by Solar AI; the dashboard is the only edit surface.
            if "ev_schedules" not in self._stored:
                migrated: list[dict] = []
                for idx, link in enumerate(links, start=1):
                    if idx > EV_SCHEDULES_MAX or not isinstance(link, dict):
                        continue
                    entity_id = (link.get("schedule_entity") or "").strip()
                    if not entity_id:
                        continue
                    sched_state = self.hass.states.get(entity_id) if self.hass else None
                    if sched_state is None:
                        continue
                    attrs = sched_state.attributes or {}
                    # Pick the first non-empty per-day range as the slot's
                    # canonical (start, end). One range per day in the new
                    # model — if the helper had multiple, the rest are
                    # dropped (and the user can re-edit on the dashboard).
                    start_s: str | None = None
                    end_s: str | None = None
                    days_present: list[str] = []
                    for day_key, day_code in zip(
                        ("monday", "tuesday", "wednesday", "thursday",
                         "friday", "saturday", "sunday"),
                        EV_SCHEDULE_DAYS,
                    ):
                        ranges = attrs.get(day_key) or []
                        if ranges:
                            days_present.append(day_code)
                            if start_s is None and isinstance(ranges[0], dict):
                                start_s = (ranges[0].get("from") or "")[:5]
                                end_s = (ranges[0].get("to") or "")[:5]
                    if not start_s or not end_s or not days_present:
                        continue
                    # Mode: prefer the v0.37.0 _stored override over link dict
                    stored_mode_key = f"{EV_SCHEDULE_LINK_MODE_STORAGE_PREFIX}{idx}_mode"
                    mode = (self._stored.get(stored_mode_key)
                            or link.get("mode") or EV_SCHEDULE_DEFAULT_MODE)
                    if mode not in (EV_MODE_PV, EV_MODE_PV_BATTERY, EV_MODE_FULL):
                        mode = EV_SCHEDULE_DEFAULT_MODE
                    migrated.append({
                        "slot": idx,
                        "enabled": True,
                        "mode": mode,
                        "name": f"Skema {idx}",
                        "start": start_s,
                        "end": end_s,
                        "days": days_present,
                    })
                self._stored["ev_schedules"] = migrated
                if migrated:
                    _LOGGER.info(
                        "v0.38.0 native-schedule migration: imported %d slot(s) "
                        "from ev_schedule_links — orphaned schedule.* helpers "
                        "may remain in Settings → Helpers and can be deleted.",
                        len(migrated),
                    )
        # Hydrate the in-memory active mode from storage
        self._ev_active_mode = self._stored.get("ev_active_mode", EV_MODE_LOCKED)
        # Restore enabled state — default OFF so user must consciously turn on
        self._enabled = self._stored.get("enabled", False)
        # v0.49.1 — restore the last good feed-in tariff so the export price is
        # correct immediately after a restart, instead of sitting at 0 until the
        # next successful daily tariff fetch.
        self._feed_in_tariff_dso = float(self._stored.get("feed_in_tariff_dso", 0.0))
        self._feed_in_tariff_energinet = float(self._stored.get("feed_in_tariff_energinet", 0.0))
        # v0.59.4 — restore last-good price caches so a restart (or a failed /
        # rate-limited fetch right after one) keeps the plan running on known
        # prices instead of blanking until the next successful fetch.
        try:
            self._cached_stromligning_prices = self._stored.get("stromligning_prices_cache", {}) or {}
            _sl_iso = self._stored.get("stromligning_refresh_iso")
            self._last_stromligning_refresh = datetime.fromisoformat(_sl_iso) if _sl_iso else None
            _ts = self._stored.get("tariff_schedule_cache")
            if isinstance(_ts, list) and len(_ts) == 24:
                self._tariff_schedule = [float(x) for x in _ts]
            _tsr_iso = self._stored.get("tariff_schedule_refresh_iso")
            self._last_tariff_schedule_refresh = datetime.fromisoformat(_tsr_iso) if _tsr_iso else None
            self._cached_eds_rates = self._stored.get("eds_rates_cache", []) or []
            _eds_iso = self._stored.get("eds_refresh_iso")
            self._last_eds_refresh = datetime.fromisoformat(_eds_iso) if _eds_iso else None
        except Exception as err:  # noqa: BLE001 — never let a bad cached value block startup
            _LOGGER.warning("Could not restore cached prices from storage: %s", err)
        # v0.60.0 — the BMS capacity learner sampled during active discharge,
        # dividing a stale-high kWh-remaining register by a live (lower) SoC,
        # which drifted the learned capacity high (a 12.1 kWh battery reached
        # ~16.9). The learner is now idle-gated and is diagnostic-only (the GUI
        # Battery capacity number is authoritative). Clear the drifted samples
        # once so the diagnostic re-learns cleanly from idle ticks.
        if not self._stored.get("capacity_samples_reset_v060"):
            self._stored["capacity_samples"] = []
            self._stored["capacity_samples_reset_v060"] = True
        # v0.61.x step 2 — if a restart happened mid-night, the in-progress
        # overnight accumulation has a gap; mark it dirty so it's dropped at
        # finalize rather than logged as an under-counted (too-low) sample.
        if self._stored.get("overnight_night_id"):
            self._stored["overnight_dirty"] = True
        # v0.64.1 — BMS capacity learner retired (see _async_update_data). Clear
        # the sample window once to drop the BMS-polluted values (drifted to
        # ~25.7 kWh). get_learned_capacity() then returns None until the reliable
        # Force-Charge learner re-populates it, clearing the model-health flag.
        if not self._stored.get("capacity_bms_retired_v0641"):
            self._stored["capacity_samples"] = []
            self._stored["capacity_bms_retired_v0641"] = True

    # ------------------------------------------------------------------ #
    # Legacy automation management                                          #
    # ------------------------------------------------------------------ #

    async def async_disable_legacy_automation(self) -> None:
        """Turn off the pre-existing export-limit automation to avoid conflicts."""
        state = self.hass.states.get(LEGACY_EXPORT_AUTOMATION)
        if state is None:
            return
        if state.state == "on":
            try:
                await self.hass.services.async_call(
                    "automation", "turn_off",
                    {"entity_id": LEGACY_EXPORT_AUTOMATION},
                    blocking=True,
                )
                _LOGGER.info(
                    "Battery Arbitrage: disabled legacy automation %s",
                    LEGACY_EXPORT_AUTOMATION,
                )
            except Exception as err:
                _LOGGER.warning("Could not disable legacy automation: %s", err)

    async def async_restore_legacy_automation(self) -> None:
        """Re-enable the pre-existing export-limit automation on unload."""
        state = self.hass.states.get(LEGACY_EXPORT_AUTOMATION)
        if state is None:
            return
        if state.state == "off":
            try:
                await self.hass.services.async_call(
                    "automation", "turn_on",
                    {"entity_id": LEGACY_EXPORT_AUTOMATION},
                    blocking=True,
                )
                _LOGGER.info(
                    "Battery Arbitrage: re-enabled legacy automation %s",
                    LEGACY_EXPORT_AUTOMATION,
                )
            except Exception as err:
                _LOGGER.warning("Could not re-enable legacy automation: %s", err)

    # ------------------------------------------------------------------ #
    # Main update cycle                                                     #
    # ------------------------------------------------------------------ #

    async def _async_update_data(self) -> dict[str, Any]:
        session = async_get_clientsession(self.hass)
        # .get with default: a FoxESS-only entry never sets evcc_url, and this
        # read runs every cycle before the mode gate in _fetch_live_state. The
        # default is harmless — FoxESS/hybrid modes don't call the EVCC URL.
        evcc_url = self.config.get("evcc_url", DEFAULT_EVCC_URL)
        now = datetime.now(timezone.utc)
        forecast_hours = self.config.get("forecast_hours", 24)

        # ── Fast: fetch live state every tick (dispatches on configured source) ──
        # Returns a dict in EVCC /api/state shape: homePower, pvPower, gridPower,
        # loadpoints (list), batteryMode. See _fetch_live_state() for the per-source
        # logic and resilience rules.
        evcc_state = await self._fetch_live_state(session, evcc_url)

        # ── Hourly: refresh tariff / price data ──────────────────────────
        # v0.59.16 — after a refresh that produced no usable rates, retry in
        # minutes instead of waiting the full hour, so a transient feed gap
        # self-heals. Source-agnostic: it just retries whatever source(s) are
        # configured sooner — single-source setups are unaffected.
        _refresh_interval = (
            TARIFF_REFRESH_INTERVAL_SECONDS if self._last_tariff_fetch_ok
            else PRICE_RETRY_AFTER_FAIL_SECONDS
        )
        tariff_stale = (
            self._last_tariff_refresh is None
            or (now - self._last_tariff_refresh).total_seconds() >= _refresh_interval
        )
        if tariff_stale:
            price_area = self._setting(CONF_PRICE_AREA, DEFAULT_PRICE_AREA)

            # Solar forecast — dispatches on configured source (EVCC / forecast_solar / auto).
            # Best-effort: a failure here must not block startup or the price fetch below.
            try:
                solar_data = await self._fetch_solar_forecast(session, evcc_url)
                if solar_data and solar_data.get("rates"):
                    self._cached_solar_rates = solar_data
                elif solar_data is not None:
                    _LOGGER.warning("Solar forecast returned no rates — keeping cached data")
            except Exception as solar_err:
                _LOGGER.warning("Solar forecast fetch failed (%s) — using cached/empty data", solar_err)

            # EDS spot prices — primary price source; _fetch_eds_prices handles its own errors
            eds_data = await self._fetch_eds_prices(session, price_area, now)
            fresh_prices = False
            if eds_data.get("rates"):
                self._cached_grid_rates = eds_data
                fresh_prices = True
                _LOGGER.debug(
                    "EDS: %d spot price slots for area %s",
                    len(eds_data["rates"]), price_area,
                )
            else:
                # v0.59.20 — opt-in cross-source forecast fallback: derive the
                # spot-price forecast from the cached Strømligning prices (their
                # spot component) so an EDS gap doesn't blank the chart/optimiser.
                # Off by default; single-source users are unaffected.
                sl_fc = self._stromligning_spot_forecast(now)
                if sl_fc.get("rates"):
                    self._cached_grid_rates = sl_fc
                    fresh_prices = True
                    _LOGGER.info(
                        "EDS spot prices unavailable for %s — using Strømligning "
                        "spot forecast (%d slots)", price_area, len(sl_fc["rates"]),
                    )
                else:
                    # EDS (+ Strømligning) unavailable — fall back to EVCC grid tariff
                    _LOGGER.info(
                        "EDS spot prices unavailable for %s — falling back to EVCC grid tariff",
                        price_area,
                    )
                    try:
                        grid_data = await self._fetch_json(session, f"{evcc_url}{EVCC_API_GRID}")
                        if grid_data.get("rates"):
                            self._cached_grid_rates = grid_data
                            fresh_prices = True
                        else:
                            _LOGGER.warning("EVCC grid tariff also returned no rates")
                    except Exception as evcc_err:
                        _LOGGER.debug("EVCC grid tariff fallback failed: %s", evcc_err)

            self._last_tariff_refresh = now
            # v0.59.16 — drive the retry cadence: usable rates ⇒ hourly; nothing
            # usable (feed gap + cache drained) ⇒ retry in minutes until it heals.
            self._last_tariff_fetch_ok = fresh_prices
            if not fresh_prices:
                _LOGGER.info(
                    "Price refresh produced no usable rates — retrying in %d s",
                    PRICE_RETRY_AFTER_FAIL_SECONDS,
                )

        solar_rates = self._cached_solar_rates
        grid_rates = self._cached_grid_rates

        # ── Daily: refresh DSO + Energinet tariff schedule ───────────────────
        # Tariff schedules are stable within a day — refresh once every 24 h.
        tariff_schedule_stale = (
            self._last_tariff_schedule_refresh is None
            or (now - self._last_tariff_schedule_refresh).total_seconds()
            >= TARIFF_SCHEDULE_REFRESH_SECONDS
        )
        # v0.30.1: tariff fetching is Danish-specific (Energi Data Service
        # DatahubPricelist). Skip the block when the user has disabled it
        # (typically because they're outside Denmark). The tariff_schedule
        # stays at zeros and per-hour tariff components don't get added.
        if tariff_schedule_stale and self.config.get(
            CONF_TARIFF_FETCH_ENABLED, DEFAULT_TARIFF_FETCH_ENABLED,
        ):
            from .tariffs import fetch_tariff_schedule, fetch_feed_in_tariff  # avoid circular import at module level
            dso_gln = self.config.get(CONF_DSO_GLN, DEFAULT_DSO_GLN)
            try:
                # v0.49.1 — fetch sequentially, NOT via one asyncio.gather.
                # Each call below itself issues two concurrent EDS queries, so
                # gathering all three fired six requests at once and reliably
                # tripped Energi Data Service's rate limit (HTTP 429). A 429 on
                # an unlucky tick committed degenerate/zero data that then stuck
                # for 24 h. This is a once-a-day fetch, so the small extra
                # latency from running them one after another is irrelevant and
                # keeps the burst within the rate limit.
                #
                # DSO: 24 hourly prices + genuinely varying hours, restricted
                # to the residential C-time band via Note substring.
                # v0.39.8 — `note_substring="Nettarif C"` because the
                # require-all-prices + require-varying filters alone still let
                # through tier-A and tier-B records (Dinel publishes 7 parallel
                # bands; previously all 6 distinct profiles were summed,
                # overstating the per-kWh tariff ~3x).
                dso_sched = await fetch_tariff_schedule(
                    session, dso_gln, now,
                    require_all_prices=True,
                    require_varying_prices=True,
                    note_substring="Nettarif C",
                )
                # Energinet: codes 40000 (Transmissions nettarif) + 41000
                # (Systemtarif) — both apply to residential consumers.
                # v0.39.8 — 41000 added; was missing before, halving the
                # Energinet contribution. Excludes 40010 (Indfødningstarif
                # produktion), 40020 (HV 132/150 kV), capacity / industrial.
                energinet_sched = await fetch_tariff_schedule(
                    session, ENERGINET_GLN, now,
                    allowed_codes=ENERGINET_TARIFF_CODES,
                )
                # Feed-in tariffs: DSO indfødning C + Energinet indfødning produktion (40010)
                dso_feed_in, en_feed_in = await fetch_feed_in_tariff(
                    session, dso_gln, ENERGINET_GLN, now,
                )
                # v0.39.13 — only commit if BOTH fetches returned non-empty
                # data. Before this guard, a partial fetch (e.g. Energinet
                # returning [0]*24 due to a Datahub rate-limit or transient
                # network issue) would silently overwrite the cache with
                # bad data and lock that 24-hour-stale state for a full
                # day. Observed live on 2026-05-26: nettarif_denne_time
                # dropped from 0.217 (DSO+Energinet, correct) to 0.1023
                # (DSO only) after one of several restarts re-fetched
                # while Datahub was flaky. Now: keep the previous good
                # cache and retry on the next coordinator tick.
                dso_ok = any(dso_sched)
                energinet_ok = any(energinet_sched)
                if dso_ok and energinet_ok:
                    self._tariff_schedule = [
                        round(d + e, 4) for d, e in zip(dso_sched, energinet_sched)
                    ]
                    # v0.59.4 — persist the schedule + its refresh time so a
                    # restart reuses it and skips the daily Datahub re-fetch
                    # while still fresh (avoids the repeated-restart rate-limit).
                    self._stored["tariff_schedule_cache"] = self._tariff_schedule
                    self._stored["tariff_schedule_refresh_iso"] = now.isoformat()
                    # v0.49.1 — fetch_feed_in_tariff now returns None (not 0.0)
                    # when the lookup failed (e.g. an EDS 429 on the feed-in
                    # queries while the consumption queries succeeded). Only
                    # commit + persist a real value; otherwise keep the last
                    # good cached one instead of zeroing the export price.
                    if dso_feed_in is not None:
                        self._feed_in_tariff_dso = dso_feed_in
                        self._stored["feed_in_tariff_dso"] = dso_feed_in
                    if en_feed_in is not None:
                        self._feed_in_tariff_energinet = en_feed_in
                        self._stored["feed_in_tariff_energinet"] = en_feed_in
                    self._last_tariff_schedule_refresh = now
                    # v0.49.1 — if we still have NO feed-in tariff at all (cold
                    # cache plus a failed feed-in lookup, e.g. a 429 that the
                    # retries didn't clear), don't sit on the 24-hour timer with
                    # the export price stuck at 0. Pretend the refresh is nearly
                    # stale so the next attempt happens in ~15 min instead.
                    # Once any real feed-in value lands (and is persisted) this
                    # branch stops firing and the normal 24-hour cadence holds.
                    if not (self._feed_in_tariff_dso or self._feed_in_tariff_energinet):
                        self._last_tariff_schedule_refresh = now - timedelta(
                            seconds=max(0, TARIFF_SCHEDULE_REFRESH_SECONDS - 900),
                        )
                    _LOGGER.debug(
                        "Tariff schedule refreshed (GLN %s + Energinet). "
                        "Hour 0: %.4f, Hour 12: %.4f DKK/kWh",
                        dso_gln,
                        self._tariff_schedule[0],
                        self._tariff_schedule[12],
                    )
                else:
                    _LOGGER.warning(
                        "Tariff schedule fetch partial — DSO ok=%s (sum=%.4f), "
                        "Energinet ok=%s (sum=%.4f). Keeping previous cache; "
                        "will retry in ~10 minutes.",
                        dso_ok, sum(dso_sched),
                        energinet_ok, sum(energinet_sched),
                    )
                    # Bump the refresh timestamp forward so the next retry
                    # fires after ~10 minutes instead of 24 hours, but not
                    # every coordinator tick (which would hammer Datahub).
                    self._last_tariff_schedule_refresh = (
                        now - timedelta(seconds=TARIFF_SCHEDULE_REFRESH_SECONDS - 600)
                    )
            except Exception as err:
                _LOGGER.warning("Tariff schedule refresh failed, keeping existing: %s", err)

            # ── Strømligning retailer prices (v0.29.0) ─────────────────────
            # Refreshed on the same daily cadence as tariffs. Only runs when
            # the user has selected Strømligning mode and provided IDs. Wrapped
            # in its own try so a Strømligning outage doesn't break the rest
            # of the price refresh path.
            try:
                await self._maybe_refresh_stromligning_prices(session, now)
            except Exception as err:
                _LOGGER.warning("Strømligning price refresh failed: %s", err)

            # ── Octopus Energy retailer prices (v0.30.0) ────────────────────
            # Same daily cadence. No-op when buy_price_mode != "octopus".
            try:
                await self._maybe_refresh_octopus_prices(session, now)
            except Exception as err:
                _LOGGER.warning("Octopus price refresh failed: %s", err)

        # ---- parse EVCC ----
        home_power_w = evcc_state.get("homePower", 0)
        pv_power_w = evcc_state.get("pvPower", 0)
        grid_power_w = evcc_state.get("gridPower", 0)   # positive = import, negative = export
        loadpoints = evcc_state.get("loadpoints", [{}])
        lp = loadpoints[0] if loadpoints else {}
        ev_charge_power_w = lp.get("chargePower", 0)
        ev_mode = lp.get("mode", "pv")
        # v0.28.0 fix — FoxESS-only mode has loadpoints=[] so the EVCC-based
        # ev_charge_power_w defaults to 0. Backfill from the embedded OCPP
        # server's ChargePoint so the EV's draw gets correctly subtracted
        # from house load in `base_load_kw` below, and the hourly house-load
        # learning model doesn't get contaminated with EV-charging spikes.
        if ev_charge_power_w == 0 and self.ocpp_server is not None:
            charger_id = self.config.get(CONF_EV_OCPP_CHARGE_POINT_ID, "")
            if charger_id:
                cp = self.ocpp_server.get(charger_id)
                if cp is not None and cp.power_w > 0:
                    ev_charge_power_w = cp.power_w

        # Check all loadpoints for EV presence and active non-PV charging
        ev_connected = any(lp_.get("connected", False) for lp_ in loadpoints)
        ev_charging_now = any(
            lp_.get("charging", False) and lp_.get("mode") in (EV_MODE_NOW, EV_MODE_MIN_PV)
            for lp_ in loadpoints
        )
        # EV charging purely on solar surplus (pv mode, real charge power flowing)
        ev_charge_threshold_w = self._ev_charge_threshold_w()
        ev_charging_solar = any(
            lp_.get("charging", False)
            and lp_.get("mode") == "pv"
            and lp_.get("chargePower", 0) > ev_charge_threshold_w
            for lp_ in loadpoints
        )

        # v0.39.10 — FoxESS-only mode backfill for `ev_charging_now` and
        # `ev_charging_solar`. In FoxESS-only mode there is no EVCC poll so
        # `loadpoints = []`, which means the two `any(...)` expressions above
        # are always False — the binary_sensor.solar_ai_ev_oplader_solenergi
        # never lit up even when the embedded OCPP server was actively
        # charging the car, and the optimizer's `should_export` guard at the
        # "hold the battery for the EV" check (later in this method) was
        # never engaged either.
        #
        # v0.28.0 fixed the same pattern for `ev_charge_power_w` but missed
        # these two flags. The fix mirrors that backfill: when loadpoints is
        # empty, derive the flags from the live OCPP draw + the EV
        # controller's effective mode (the mode the controller actually
        # applies each tick, resolved by `_resolve_effective_ev_mode` —
        # `_ev_active_mode` may be `scheduled`, but `_ev_effective_mode` is
        # always one of locked/pv/pv_battery/full).
        #
        # Mode → flag mapping (matches the EVCC semantics used above):
        #   pv         → ev_charging_solar (pure surplus)
        #   pv_battery → ev_charging_now (uses house battery — same
        #                  "hold the battery for the EV" rationale as the
        #                  EVCC minpv mode, so should_export is suppressed)
        #   full       → ev_charging_now (fast charge — like EVCC `now`)
        if not loadpoints and ev_charge_power_w > ev_charge_threshold_w:
            if self._ev_effective_mode == EV_MODE_PV:
                ev_charging_solar = True
            elif self._ev_effective_mode in (EV_MODE_PV_BATTERY, EV_MODE_FULL):
                ev_charging_now = True

        # EVCC battery mode: "normal", "hold", or "charge"
        # If EVCC (not us) has set it to hold/charge, we must not override it
        evcc_battery_mode = evcc_state.get("batteryMode", EVCC_BATTERY_NORMAL)
        evcc_managing_battery = (
            evcc_battery_mode != EVCC_BATTERY_NORMAL and not self._we_set_evcc_mode
        )

        # Base house load (subtract EV charging — it's a separate decision)
        base_load_kw = max(0.0, (home_power_w - ev_charge_power_w) / 1000)

        # ---- solar forecast (raw from Solcast via EVCC) ----
        solar_kwh_raw = _sum_forecast(solar_rates.get("rates", []), now, forecast_hours, watts=True)
        solar_kwh_6h_raw = _sum_forecast(solar_rates.get("rates", []), now, 6, watts=True)

        # ── 5-min learning tick: update all storage-backed models ────────
        # These operations use sample-count windows tuned for 5-min granularity.
        # Running them every fast tick would overflow buffers and bias the models.
        current_forecast_w = _current_slot_forecast(solar_rates.get("rates", []), now)
        # v0.28.6: short-term solar residual tracking — runs every tick
        # (not gated on the learning interval) so the intra-hour ratio
        # reflects sub-minute reality.
        self._update_short_term_solar_correction(
            now, float(pv_power_w or 0.0), solar_rates.get("rates", []) or [],
        )

        is_learning_tick = (
            self._last_learning_tick is None
            or (now - self._last_learning_tick).total_seconds() >= LEARNING_TICK_INTERVAL_SECONDS
        )
        if is_learning_tick:
            if current_forecast_w is not None and (
                current_forecast_w >= SOLAR_ACCURACY_MIN_FORECAST_W
                or pv_power_w >= SOLAR_ACCURACY_MIN_FORECAST_W
            ):
                # v0.30.1: when the solar export floor is active the panels
                # are deliberately curtailed — pass `curtailed=True` so the
                # learner drops the sample instead of comparing forecast to
                # throttled-down production.
                # v0.36.0: attribute renamed to `_current_floor_block` (was
                # `_open_floor_block` — clashed with the method of that name).
                # v0.39.15: also drop samples when the inverter itself
                # reports PV throttling (`_pv_power_limited_flag`, reg
                # 49251 = 1). Without this, battery-full MPPT throttling
                # (no price-floor block) was feeding artificially low
                # actuals into the per-hour Solcast factor — model
                # learned "Solcast over-estimates" and biased future
                # forecasts down. Note: the flag is read once per
                # coordinator tick at line ~1468, AFTER this learning
                # call. So this reads the PREVIOUS tick's value (~30 s
                # latency), which is fine because MPPT throttling is
                # stable across multiple ticks.
                floor_active = self._current_floor_block is not None
                mppt_curtailed = self._pv_power_limited_flag
                self._update_solar_accuracy(
                    current_forecast_w, pv_power_w,
                    curtailed=(floor_active or mppt_curtailed),
                )
            self._update_load_history(base_load_kw)
            self._update_house_load_hourly(base_load_kw)
            self._update_ev_charge_learning(ev_charge_power_w)
            self._update_ev_max_kw(ev_charge_power_w)
            self._update_daily_solar(pv_power_w)
            self._last_learning_tick = now

        solar_accuracy_factor = self.get_solar_accuracy_factor()

        # Apply the learned correction to get realistic forecasts
        solar_kwh = round(solar_kwh_raw * solar_accuracy_factor, 3)
        solar_kwh_6h = round(solar_kwh_6h_raw * solar_accuracy_factor, 3)

        # ---- grid price analysis ----
        grid_vals = _forecast_values(grid_rates.get("rates", []), now, forecast_hours)
        if grid_vals:
            sorted_vals = sorted(grid_vals)
            n = len(sorted_vals)
            price_min = sorted_vals[0]
            price_max = sorted_vals[-1]
            price_mean = statistics.mean(sorted_vals)
            price_p25 = sorted_vals[max(0, n // 4 - 1)]
            price_p75 = sorted_vals[min(n - 1, 3 * n // 4)]
            next_slot_vals = _forecast_values(grid_rates.get("rates", []), now, 0.5)
            price_next_slot = next_slot_vals[0] if next_slot_vals else price_min
        else:
            price_min = price_max = price_mean = price_p25 = price_p75 = price_next_slot = 0.0

        # ---- buy-side prices: spot + markup + DSO/Energinet tariff + elafgift + VAT ----
        # The true cost of buying electricity includes the retailer's spot markup,
        # network tariffs (varying hourly), elafgift (government electricity duty),
        # and VAT.  Each forecast slot gets the tariff for its own local hour of day.
        vat_factor = 1 + self._stored.get("vat_pct", DEFAULT_VAT_PCT) / 100
        elafgift = self._stored.get("elafgift", DEFAULT_ELAFGIFT_DKK_KWH)
        spot_markup = self._stored.get("spot_markup", DEFAULT_SPOT_MARKUP)
        tariff_sched = self._tariff_schedule

        current_local_hour = now.astimezone().hour
        tariff_this_hour = round(tariff_sched[current_local_hour] + elafgift, 4)

        # Native-resolution slot data (handles 15-min or hourly depending on DSO/EVCC config)
        grid_slot_data = _forecast_slots(grid_rates.get("rates", []), now, forecast_hours)
        solar_slot_data = _forecast_slots(solar_rates.get("rates", []), now, forecast_hours)
        # Extended window for the DP optimizer — uses all available price data (typically 48 h
        # once tomorrow's day-ahead prices are published at 13:00 CET).
        grid_slot_data_opt = _forecast_slots(grid_rates.get("rates", []), now, 48)
        solar_slot_data_opt = _forecast_slots(solar_rates.get("rates", []), now, 48)
        # Solar lookup: slot_start → kW (value is average Watts during the slot)
        solar_kw_by_start: dict = {s[0]: s[4] / 1000.0 for s in solar_slot_data}
        if grid_slot_data:
            # v0.29.0: buy price computation routes through _compute_buy_price
            # which handles Strømligning mode (with optional overrides) and
            # falls back to the manual stack when no Strømligning data exists
            # for the slot.
            #
            # v0.75.10 — `_buy` now takes the slot's REAL start datetime
            # (from `_forecast_slots`, which keeps the true date and minute)
            # instead of reconstructing a synthetic one as `now`'s date at
            # the slot's bare hour with minute forced to 0. The reconstructed
            # version broke two ways once `forecast_hours` exceeds 24 (a
            # valid, in-range setup-wizard setting): a slot belonging to
            # tomorrow got looked up in the Octopus/Strømligning per-slot
            # cache as if it were today, either hitting the wrong day's
            # cached price or missing the cache and silently falling back to
            # the manual price stack for that slot; and Strømligning's
            # 15-min-resolution lookup could only ever hit the :00 quarter,
            # never :15/:30/:45, for every slot this percentile calculation
            # touched. `_compute_buy_price` already has the correct 15-min
            # cache-key logic (see its Strømligning branch) — this only
            # fixes what was being passed into it.
            def _buy(spot_value: float, slot_start_dt: datetime, hour: int) -> float:
                return self._compute_buy_price(
                    spot=spot_value,
                    hour=hour,
                    slot_start_dt=slot_start_dt,
                    spot_markup=spot_markup,
                    tariff_this_hour_dso=tariff_sched[hour],
                    elafgift=elafgift,
                    vat_factor=vat_factor,
                )
            buy_vals_sorted = sorted(
                _buy(value, start, local_hour)
                for start, _dur_h, local_hour, _local_minute, value in grid_slot_data
            )
            n_buy = len(buy_vals_sorted)
            buy_price_min = buy_vals_sorted[0]
            buy_price_p25 = buy_vals_sorted[max(0, n_buy // 4 - 1)]
            next_slot_data = _forecast_slots(grid_rates.get("rates", []), now, 0.5)
            if next_slot_data:
                start_next, _dur_h, hour_next, _minute_next, spot_next = next_slot_data[0]
                buy_price_next_slot = _buy(spot_next, start_next, hour_next)
            else:
                buy_price_next_slot = buy_price_min
        else:
            buy_price_min = buy_price_p25 = buy_price_next_slot = 0.0

        # ---- FoxESS state ----
        battery_soc = self._get_float_state(self.config.get(CONF_BATTERY_SOC_ENTITY, FOXESS_BATTERY_SOC), 0)
        cell_temp_low = self._get_float_state(self.config.get(CONF_CELL_TEMP_ENTITY, FOXESS_CELL_TEMP_LOW))
        battery_charge_kw = self._get_float_state(self.config.get(CONF_BATTERY_CHARGE_ENTITY, FOXESS_BATTERY_CHARGE_POWER), 0)
        battery_discharge_kw = self._get_float_state(self.config.get(CONF_BATTERY_DISCHARGE_ENTITY, FOXESS_BATTERY_DISCHARGE_POWER), 0)
        current_work_mode = self.hass.states.get(FOXESS_WORK_MODE_ENTITY)
        work_mode_str = current_work_mode.state if current_work_mode else WORK_MODE_SELF_USE
        # v0.61.0 — a 0 / unavailable SoC read (common for the first ticks after a
        # restart, before FoxESS repopulates; `battery_soc` defaults to 0) must not
        # drive control. The battery never legitimately sits at 0 % (it floors well
        # above). Treat <= 0 as unreliable and hold control for that cycle rather
        # than acting on a phantom value (e.g. a spurious grid-charge into a "near
        # empty" reading). The learners are already SoC-range-gated.
        soc_reliable = battery_soc > 0
        # v0.65.0 — crash-recovery for the export-floor hardware backstop: if a
        # raised on-grid Min-SoC was persisted but we are no longer exporting
        # (e.g. HA restarted mid-Force-Discharge), restore it now so overnight
        # house self-use isn't blocked. No-op once nothing is pending.
        if (self._stored.get("export_min_soc_prev") is not None
                and self._current_mode != MODE_EXPORTING):
            await self._restore_export_min_soc()

        # ---- current spot price ----
        # Primary: read from a user-configured HA sensor (Strømligning, Tibber, etc.)
        # Fallback: extract the current hour's rate from the EDS cache that the optimizer
        #           already uses.  This makes the HA spot-price entity fully optional —
        #           when it is not configured or unavailable, Solar AI self-sources the
        #           price from the same Nord Pool data the optimizer uses.
        spot_entity_id = (
            self.config.get(CONF_SPOT_PRICE_ENTITY)
            or self.config.get(CONF_STROMLIGNING_ENTITY)
        )
        spot_ex_vat: float = 0.0
        spot_from_entity = False
        if spot_entity_id:
            spot_state = self.hass.states.get(spot_entity_id)
            if spot_state and spot_state.state not in ("unknown", "unavailable"):
                try:
                    spot_ex_vat = float(spot_state.state)
                    spot_from_entity = True
                except ValueError:
                    pass

        # v0.60.2 — fall back to the EDS cache only when the entity didn't supply
        # a value. (Previously this keyed off `spot_ex_vat == 0.0`, which
        # discarded a legitimately-zero / free-hour spot price and replaced it
        # with the EDS rate.)
        if not spot_from_entity:
            # HA entity missing/unavailable — fall back to EDS rate for this hour
            for rate in self._cached_grid_rates.get("rates", []):
                try:
                    rate_start = datetime.fromisoformat(rate["start"])
                    if rate_start.tzinfo is None:
                        rate_start = rate_start.replace(tzinfo=timezone.utc)
                    rate_local_hour = rate_start.astimezone().hour
                    if rate_local_hour == current_local_hour:
                        spot_ex_vat = float(rate["value"])
                        break
                except (ValueError, TypeError, KeyError):
                    continue
        # v0.29.0: sell-side company picker. If a curated sell-side company is
        # selected and has a known fee, use that. Otherwise fall back to the
        # manual export_fee slider (storage key "export_fee", configurable via
        # the dashboard number entity).
        sell_company = self.config.get(CONF_SELL_SIDE_COMPANY, DEFAULT_SELL_SIDE_COMPANY)
        export_fee = self._stored.get("export_fee", DEFAULT_EXPORT_FEE)
        if sell_company and sell_company != DEFAULT_SELL_SIDE_COMPANY:
            for opt in SELL_SIDE_COMPANY_OPTIONS:
                if opt["id"] == sell_company and opt.get("fee_dkk_kwh") is not None:
                    export_fee = float(opt["fee_dkk_kwh"])
                    break
        feed_in_tariff = round(self._feed_in_tariff_dso + self._feed_in_tariff_energinet, 6)
        # Raw export price before floor guard (used in chart / plan)
        export_price_raw = spot_ex_vat - export_fee - feed_in_tariff
        export_price = max(0.0, export_price_raw)

        # ---- load model (reads from storage, always fresh) ----
        load_history = self._stored.get("load_history", [])
        load_2h_avg = _rolling_mean(load_history, VACATION_SHORT_WINDOW)
        load_28d_avg = _rolling_mean(load_history, LOAD_HISTORY_MAX_SAMPLES)
        # vacation_mode writes to storage — update cached value on learning ticks only
        if is_learning_tick:
            self._vacation_mode = self._update_vacation_mode(load_2h_avg, load_28d_avg)
        vacation_mode = self._vacation_mode
        # v0.47.5 — project from the learned hourly profile (realistic daily
        # shape) instead of flat-extrapolating the 2-hour average across 24 h.
        predicted_house_load_24h = self._predict_house_load_window(
            now, forecast_hours, vacation_mode, load_2h_avg
        )

        # ---- temperature learning (gated) ----
        if is_learning_tick and cell_temp_low is not None:
            self._calibrate_charge_rate(
                cell_temp_low, battery_charge_kw, battery_soc, work_mode_str
            )
        learned_charge_rate = self.get_current_charge_rate()

        # ---- EV charge pattern ----
        ev_block_prob = self.get_ev_charge_probability()
        ev_likely_charging = ev_block_prob >= EV_CHARGE_BLOCK_PROBABILITY

        # ---- seasonal mode ----
        is_summer_mode, solar_28d_avg = self.get_season_mode()

        # ---- capacity & efficiency: auto-detect, fall back to config ----
        floor_soc = int(self._stored.get("battery_floor_soc", self.config.get("battery_floor_soc", DEFAULT_BATTERY_FLOOR_SOC)))
        max_soc = int(self._stored.get("battery_max_soc", self.config.get("battery_max_soc", DEFAULT_BATTERY_MAX_SOC)))
        # v0.75.8 — the setup wizard and the dashboard sliders both accept
        # floor_soc and max_soc independently, with no cross-validation
        # between them. If a user ever pushes floor above max (e.g. raises
        # the export floor without noticing the charge ceiling is lower),
        # should_export's `battery_soc > floor_soc` and should_grid_charge's
        # `battery_soc < max_soc` combine into an unsatisfiable band the
        # battery can never legitimately occupy. Clamp floor down to max —
        # the battery must always be able to reach the floor via normal
        # charging — rather than silently suppressing all arbitrage.
        if floor_soc > max_soc:
            _LOGGER.warning(
                "Battery floor SoC (%d%%) is above max SoC (%d%%) — "
                "clamping floor to %d%%. Check the SoC settings.",
                floor_soc, max_soc, max_soc,
            )
            floor_soc = max_soc

        # Capacity: the GUI "Battery capacity" number is authoritative — the
        # value the user sets there is what the optimiser uses, full stop. It
        # falls back to the configured (setup-wizard) value until the user
        # changes the slider. The BMS auto-learner is kept only as a read-only
        # diagnostic (the `learned_capacity` telemetry below); it no longer
        # overrides the user's value, because the BMS kWh-remaining register
        # lags SoC during discharge and drifts the estimate high.
        configured_capacity = self.config.get("battery_capacity", DEFAULT_BATTERY_CAPACITY)
        capacity_kwh = float(self._stored.get("battery_capacity", configured_capacity))
        learned_capacity = self.get_learned_capacity()  # diagnostic only

        # Efficiency: use FoxESS lifetime totals if available
        auto_efficiency = self.get_auto_efficiency()
        efficiency = auto_efficiency if auto_efficiency is not None \
            else self.config.get("round_trip_efficiency", DEFAULT_ROUND_TRIP_EFFICIENCY)

        # Capacity learning: gate to 5-min ticks (energy calculation needs correct interval_h)
        if is_learning_tick:
            # v0.64.1 — the BMS capacity learner is RETIRED. The FoxESS
            # kWh-remaining register is sticky and lags SoC even near idle, so
            # capacity = kWh_remaining / (SoC/100) drifted badly (16.9 then 25.7
            # vs the real 12.1) despite the v0.60.0 idle-gate — and the model
            # -health monitor flagged it. Capacity is GUI-set (authoritative);
            # the only remaining capacity sampler is the Force-Charge learner
            # below, which measures real energy-in vs ΔSoC and is reliable when
            # it fires. (The BMS-based sampler, `_learn_capacity_from_bms`, was
            # removed entirely in v0.75.7 rather than left as dead code.)
            self._learn_capacity(battery_soc, battery_charge_kw)
            # v0.61.x step 2 — passively learn the overnight house-load forecast
            # error (base_load_kw already excludes the EV). soc_reliable marks a
            # night dirty so a restart-time 0 read can't pollute the sample.
            self._update_overnight_reserve_learning(now, base_load_kw, soc_reliable)
            # v0.64.0 — Tier-1 model-health monitor: detect a learned model that
            # has drifted / pinned at a clamp / gone persistently wrong and
            # surface it (edge-triggered notification), instead of letting it
            # silently skew decisions the way the capacity/margin bugs did.
            self._model_health_issues, self._model_health_notes = self._check_model_health()
            unhealthy = bool(self._model_health_issues)
            if unhealthy and not self._prev_model_unhealthy:
                _LOGGER.warning(
                    "Model health: %s", "; ".join(self._model_health_issues))
                if self._stored.get("notifications_enabled", False):
                    await self._send_mobile_notification(
                        self._msg("⚠️ Solar AI: a learned model needs attention",
                                  "⚠️ Solar AI: en lært model kræver opmærksomhed"),
                        "; ".join(self._model_health_issues),
                    )
            self._prev_model_unhealthy = unhealthy
            # v0.66.0 Tier-2 — bounded auto-correction circuit breaker. If the
            # capacity learner stays drifted from the set value for ~a day,
            # auto-reset its samples (a learner reset is safe — it never changes a
            # safety bound; the GUI capacity stays authoritative). The Tier-1 edge
            # notification already alerted the user when it first drifted.
            _cap_cfg = float(self._stored.get(
                "battery_capacity", self.config.get("battery_capacity", DEFAULT_BATTERY_CAPACITY)))
            _cap_learned = self.get_learned_capacity()
            _cap_drifted = (
                _cap_learned is not None and _cap_cfg > 0
                and abs(_cap_learned - _cap_cfg) / _cap_cfg > MODEL_HEALTH_CAPACITY_DRIFT_FRAC)
            if _cap_drifted:
                self._capacity_drift_streak += 1
                if self._capacity_drift_streak >= MODEL_HEALTH_AUTORESET_STREAK:
                    self._stored["capacity_samples"] = []
                    self._capacity_drift_streak = 0
                    _LOGGER.warning(
                        "Tier-2 self-correction: capacity learner drifted for ~1 day "
                        "(learned %.1f vs set %.1f kWh) — samples reset",
                        _cap_learned, _cap_cfg)
                    if self._stored.get("notifications_enabled", False):
                        await self._send_mobile_notification(
                            self._msg("Solar AI: capacity learner auto-reset",
                                      "Solar AI: kapacitetslæring nulstillet"),
                            self._msg(
                                "The learned capacity drifted from your set value for over "
                                "a day and was reset. Your set value is unchanged.",
                                "Den lærte kapacitet afveg fra din indstilling i over et "
                                "døgn og blev nulstillet. Din indstilling er uændret."))
            else:
                self._capacity_drift_streak = 0

        # v0.47.0 (C) — dynamic self-learning discharge floor. When enabled, the
        # reserve is the SoC needed to bridge the house to the next solar refill
        # (net of any planned grid-charge) × a learned margin.
        # v0.59.18 — the user's Minimum SoC (export) slider is now a HARD floor:
        # the dynamic reserve may only RAISE it (reserve more for the night),
        # never sell below it. Previously it *replaced* the slider and could sell
        # all the way to the hardware minimum on a forecast of a cheap overnight
        # rebuy — which, when that forecast was wrong (or the price feed thin),
        # drained the battery overnight and forced an expensive emergency buy.
        if self._stored.get("dynamic_discharge_floor", False):
            dyn_floor = self._compute_dynamic_floor_soc(
                now=now, capacity_kwh=capacity_kwh, efficiency=efficiency,
                solar_slot_data=solar_slot_data_opt,
                grid_charge_kw=self.get_effective_charge_rate(),
            )
            if dyn_floor is not None:
                # Never below the user's slider — only raise the floor above it.
                floor_soc = max(floor_soc, int(round(dyn_floor)))
                self._dynamic_floor_soc = float(floor_soc)
            # v0.61.0 — the self-learning margin (_update_discharge_margin) is
            # retired: the reserve now uses a fixed safety factor, so there is no
            # integrator to train. The learner ratcheted on noise and was poisoned
            # by post-restart SoC=0 reads (it pegged the floor at the 85% cap).
        else:
            self._dynamic_floor_soc = None
        # v0.65.0 — remember the effective export floor for the hardware-min-SoC
        # backstop set in _transition_to(MODE_EXPORTING).
        self._effective_floor_soc = float(floor_soc)

        exportable_kwh = max(0.0, (battery_soc - floor_soc) / 100 * capacity_kwh * efficiency)
        importable_kwh = max(0.0, (max_soc - battery_soc) / 100 * capacity_kwh)

        # Net house need = predicted load minus expected solar (corrected)
        net_house_need_kwh = max(0.0, predicted_house_load_24h - solar_kwh)
        truly_exportable_kwh = max(0.0, exportable_kwh - net_house_need_kwh)

        # Time to charge to target SoC at current learned rate
        if learned_charge_rate > 0:
            time_to_charge_h = importable_kwh / learned_charge_rate
        else:
            time_to_charge_h = 999.0

        # ---- grid headroom (overcurrent protection) ----
        grid_max_kw = float(self._stored.get("grid_max_kw", GRID_MAX_KW))
        # If we're already grid-charging, battery charge power is inside gridPower —
        # subtract it so headroom reflects non-battery load only
        grid_import_kw = max(0.0, grid_power_w / 1000)
        if self._current_mode == MODE_GRID_CHARGING:
            base_grid_kw = max(0.0, grid_import_kw - battery_charge_kw)
        else:
            base_grid_kw = grid_import_kw
        grid_headroom_kw = max(0.0, grid_max_kw - GRID_SAFETY_MARGIN_KW - base_grid_kw)
        # Cap the charge rate to what the grid can safely supply
        capped_charge_rate_kw = min(learned_charge_rate if learned_charge_rate > 0 else GRID_MAX_KW, grid_headroom_kw)

        # ---- spread calculations ----
        # True cost of arbitrage has two components:
        #
        #  1. Recharge cost: to restore what we sold we must buy back more kWh than we
        #     exported (round-trip losses).  Cost per exported kWh = buy_price_min / efficiency.
        #
        #  2. House drag cost: while the battery is depleted (from now until the cheapest
        #     recharge slot), the house must buy from the grid instead of drawing from the
        #     battery.  We use the actual per-hour buy prices and the temperature-adaptive
        #     charge rate to estimate when the battery can recover.
        #
        # house drag per hour = max(0, house_load - avg_solar) × buy_price[h]
        # drag period         = hours from now until cheapest charge slot
        # (solar_kwh / 24 is a flat per-hour solar estimate; conservative but avoids
        #  requiring per-hour solar forecast that EVCC does not provide)

        house_drag_cost = 0.0
        if grid_slot_data and truly_exportable_kwh > 0 and learned_charge_rate > 0:
            # Find the slot with the cheapest full buy price (native resolution)
            cheapest_slot = min(
                grid_slot_data,
                key=lambda s: (s[4] + spot_markup + tariff_sched[s[2]] + elafgift) * vat_factor,
            )
            cheapest_start = cheapest_slot[0]
            # Only count drag if the cheapest slot is in the future
            if cheapest_start > now:
                for slot_start, dur_h, h, m, spot in grid_slot_data:
                    if now < slot_start < cheapest_start:
                        buy_h = self._compute_buy_price(
                            spot=spot,
                            hour=h,
                            slot_start_dt=slot_start,
                            spot_markup=spot_markup,
                            tariff_this_hour_dso=tariff_sched[h],
                            elafgift=elafgift,
                            vat_factor=vat_factor,
                        )
                        # Per-slot solar: use actual forecast kW, fall back to 24h average
                        solar_kw = solar_kw_by_start.get(slot_start, solar_kwh / 24.0)
                        net_house_kw = max(0.0, load_2h_avg - solar_kw)
                        # Multiply by slot duration (0.25 h for 15-min, 1.0 h for hourly)
                        house_drag_cost += net_house_kw * buy_h * dur_h

        recharge_cost_per_kwh = buy_price_min / efficiency if efficiency > 0 else buy_price_min
        house_drag_per_kwh = house_drag_cost / truly_exportable_kwh if truly_exportable_kwh > 0 else 0.0
        grid_arbitrage_spread = export_price - recharge_cost_per_kwh - house_drag_per_kwh
        min_spread = float(self._stored.get("min_spread_arbitrage", self.config.get("min_spread_arbitrage", DEFAULT_MIN_SPREAD_ARBITRAGE)))
        grid_arbitrage_worthwhile = grid_arbitrage_spread >= min_spread

        # ── Day-ahead DP optimizer ───────────────────────────────────────────
        # Refresh when prices are stale (tariff_stale) or on first run.
        # The optimizer produces a 24-h or 48-h plan (charge/export/idle per 15-min
        # slot) that replaces the reactive p25/p75 threshold logic for decisions.
        # v0.45.0 — E1: derive the live EV session demand the DP should treat as
        # near-certain for the next EV_SESSION_DP_HORIZON_H hours. Only forced-
        # draw situations count (fast / pv+battery / EVCC now/minpv, or actively
        # charging) — pure-PV charging is already captured by the solar→EV idle
        # dynamics. Falls back to the learned hourly model when no session.
        ev_session_kw = self._ev_session_demand_kw(
            connected=bool(ev_connected),
            charging_now=bool(ev_charging_now),
            effective_mode=self._ev_effective_mode,
            requested_mode=ev_mode,
            live_kw=max(0.0, float(ev_charge_power_w or 0) / 1000.0),
            max_kw=float(self._stored.get("ev_max_kw", 0.0)),
        )

        # v0.47.0 (A) — receding-horizon: re-solve at least every
        # PLAN_REFRESH_SECONDS (plus on restart / tariff refresh) instead of
        # once per day, so the plan picks up tomorrow's day-ahead prices when
        # they publish and tracks the live SoC.
        plan_stale = (
            self._last_plan_refresh is None
            or (now - self._last_plan_refresh).total_seconds() >= PLAN_REFRESH_SECONDS
        )
        # v0.47.7 — only (re)solve when the inputs are actually ready. Right
        # after a restart the price cache and live SoC haven't loaded on the
        # first tick(s); solving then produced a degenerate all-IDLE plan that,
        # being non-empty, got cached for up to PLAN_REFRESH_SECONDS (15 min) —
        # so no charge/export executed for that whole window. Gating on
        # inputs-ready leaves the plan empty (the reactive fallback handles the
        # gap) and retries every tick until prices + SoC are present, then
        # caches the first *real* plan.
        inputs_ready = bool(grid_slot_data_opt) and battery_soc > 0
        if inputs_ready and (tariff_stale or plan_stale or not self._optimizer_plan):
            self._last_plan_refresh = now
            max_export_kw_setting = float(self._stored.get("max_export_kw", DEFAULT_MAX_EXPORT_KW))
            self._optimizer_plan = self._run_optimizer(
                now=now,
                grid_slot_data=grid_slot_data_opt,
                solar_slot_data=solar_slot_data_opt,
                solar_accuracy_factor=solar_accuracy_factor,
                current_soc=battery_soc,
                capacity_kwh=capacity_kwh,
                floor_soc=float(floor_soc),
                max_soc=float(max_soc),
                efficiency=efficiency,
                charge_rate_kw=capped_charge_rate_kw if capped_charge_rate_kw > 0 else learned_charge_rate,
                house_load_profile=self.get_house_load_profile(weekend=False),
                house_load_weekend=self.get_house_load_profile(weekend=True),
                ev_charge_hourly=list(self._stored.get("ev_charge_hourly", [0.0] * 24)),
                ev_max_kw=float(self._stored.get("ev_max_kw", 0.0)),
                vat_factor=vat_factor,
                tariff_sched=tariff_sched,
                elafgift=elafgift,
                spot_markup=spot_markup,
                export_fee=export_fee,
                feed_in_tariff=feed_in_tariff,
                min_export_price=float(self._stored.get("min_export_price", DEFAULT_MIN_EXPORT_PRICE)),
                min_spread=min_spread,
                max_export_kw=max_export_kw_setting,
                ev_session_kw=ev_session_kw,
                ev_session_horizon_h=EV_SESSION_DP_HORIZON_H,
            )

        # Translate optimizer plan into flags for the current 15-min slot.
        # The plan now contains one entry per native slot (typically 15 min) so
        # we match on (hour, minute_bucket) to pick the right one.
        now_local = now.astimezone()
        current_minute_bucket = (now_local.minute // 15) * 15
        optimizer_says_export = False
        optimizer_says_charge = False
        for s in self._optimizer_plan:
            slot_h = s.get("hour")
            slot_m = s.get("minute", 0)
            # Bucket the slot minute too in case the slot starts at e.g. :12
            slot_bucket = (slot_m // 15) * 15
            if slot_h == current_local_hour and slot_bucket == current_minute_bucket:
                if s["action"] == "EXPORT":
                    optimizer_says_export = True
                elif s["action"] == "CHARGE":
                    optimizer_says_charge = True
                break
        # Data-sanity guard (v0.59.15): the percentile-based "is now cheap?" test
        # only means something with enough genuine price points AND a real
        # cheap-vs-expensive range. When the price feed fails and degenerates to a
        # slot or two (all reading the same value), a lone price is its own p25 and
        # the reactive fallback below would grid-charge at whatever — possibly
        # expensive — price is loaded. Require real data before any reactive
        # grid-charge; otherwise fall through to self-consumption.
        price_data_sufficient = (
            len(grid_vals) >= MIN_PRICE_SLOTS_FOR_GRID_CHARGE
            and (price_max - price_min) >= min_spread
        )
        # v0.59.19 — price-data HEALTH (distinct from "sufficient", which also
        # requires a real spread). Degraded = a feed problem: too few price
        # slots, or the last refresh produced no usable rates. Surfaced as a
        # binary_sensor + notification so a silent feed failure becomes visible
        # instead of quietly driving (or suppressing) trades. A flat-but-complete
        # price day is NOT degraded — it just has no arbitrage.
        price_data_degraded = (
            len(grid_vals) < MIN_PRICE_SLOTS_FOR_GRID_CHARGE
            or not self._last_tariff_fetch_ok
        )
        # Notify on the edge into degraded (mirror of the solar-floor pattern), so
        # a silent feed failure surfaces. Arbitrage is paused on degraded data
        # (the grid-charge and export guards both require sufficient data), so the
        # system safely runs self-consumption meanwhile.
        if price_data_degraded and not self._prev_price_degraded:
            _LOGGER.warning(
                "Price data degraded (%d slots) — arbitrage paused, running "
                "self-consumption until the price feed recovers", len(grid_vals),
            )
            if self._stored.get("notifications_enabled", False):
                await self._send_mobile_notification(
                    self._msg("⚠️ Solar AI: Price data unavailable",
                              "⚠️ Solar AI: Prisdata utilgængelig"),
                    self._msg(
                        f"Only {len(grid_vals)} price slot(s) — arbitrage paused, "
                        f"running on self-consumption until the feed recovers.",
                        f"Kun {len(grid_vals)} prisslot(s) — arbitrage sat på pause, "
                        f"kører på selvforbrug indtil prisfeedet er tilbage.",
                    ),
                )
        self._prev_price_degraded = price_data_degraded
        # Fall back to reactive thresholds when no plan is available
        if not self._optimizer_plan:
            battery_export_at_peak = price_p75 > 0 and export_price >= price_p75
            optimizer_says_export = battery_export_at_peak and grid_arbitrage_worthwhile
            optimizer_says_charge = (
                price_data_sufficient and buy_price_next_slot <= buy_price_p25
            )

        # ---- decision logic ----
        should_export = (
            optimizer_says_export
            # v0.59.19 — sell-side data-sanity guard (mirrors the grid-charge
            # guard): never sell the battery on degenerate/thin price data, where
            # the "is this a peak?" percentile test is meaningless. Only export
            # when the price set is real (enough slots + a genuine spread).
            and price_data_sufficient
            # v0.65.0 — gate on energy ABOVE THE FLOOR (exportable_kwh), not
            # truly_exportable_kwh. The dynamic floor already reserves the
            # overnight house need; truly_exportable_kwh subtracted the 24 h net
            # house need a SECOND time, which in low-solar/winter could fall to 0
            # and veto a sell even when the (economically-correct) DP plan said
            # export. The floor + the DP own the reservation; energy above the
            # floor is genuinely sellable.
            and exportable_kwh >= MIN_EXPORTABLE_KWH
            and battery_soc > floor_soc
            # Don't fight EVCC: if EV is fast/minpv-charging, hold the battery for it
            and not ev_charging_now
            # Don't override EVCC if it has explicitly taken control of battery mode
            and not evcc_managing_battery
        )

        # Net solar available for battery after house consumption (solar goes to house first)
        # Uses full 24h accuracy-corrected forecast minus predicted house load
        net_solar_for_battery = max(0.0, solar_kwh - predicted_house_load_24h)
        solar_will_fill = net_solar_for_battery >= importable_kwh
        should_grid_charge = (
            not should_export
            and bool(grid_vals)
            # v0.59.15 — never grid-charge on degenerate/thin price data, whatever
            # path set `optimizer_says_charge`. This is the defence that would
            # have prevented buying at 1.65 DKK/kWh during a feed failure.
            and price_data_sufficient
            and optimizer_says_charge
            and importable_kwh >= MIN_GRID_CHARGE_KWH
            # v0.66.0 — the day-ahead DP plan already models solar and the EV
            # session, so when a plan is driving this charge don't re-veto it with
            # the reactive heuristics (solar_will_fill / ev_likely_charging) —
            # they could override an economically-optimal planned charge. They
            # still apply in the reactive fallback (no plan).
            and (bool(self._optimizer_plan) or not solar_will_fill)
            and battery_soc < max_soc
            # Same EVCC respect: don't grid-charge if EVCC is managing battery
            and not evcc_managing_battery
            # Skip if EV typically charges at this hour — only in the reactive
            # fallback; with a plan the DP already accounts for the EV.
            and (bool(self._optimizer_plan) or not ev_likely_charging)
            # Grid overcurrent protection: only charge if there is useful headroom
            and capped_charge_rate_kw >= GRID_MIN_CHARGE_KW
        )

        # ── Export price floor ───────────────────────────────────────────────
        # Never export below the user-configured minimum price floor.
        # Default is 0.0 — blocks only when price is actually negative.
        # Users can raise this to avoid selling at prices they consider too low.
        min_export_price = float(self._stored.get("min_export_price", DEFAULT_MIN_EXPORT_PRICE))
        if export_price_raw <= min_export_price:
            should_export = False

        # ── Blocked sell hours (v0.66.0) ─────────────────────────────────────
        # A user veto on specific hours-of-day, set as a comma-separated list in
        # the "Blocked sell hours" text field (e.g. "20,21"). Never sells the
        # battery in a blocked hour, regardless of price or plan. Self-consumption
        # and solar export are unaffected — only the battery export is held.
        if should_export and current_local_hour in self._blocked_sell_hours():
            should_export = False
            self._mode_reason = f"Sell blocked for hour {current_local_hour:02d}h (user)"

        # If grid is paying US to buy electricity (buy price ≤ 0), always charge if there's
        # room — this overrides the spread threshold and even the EV schedule check.
        # v0.59.15 — only when the price data is real: a failed feed leaves
        # `buy_price_next_slot` at the degenerate 0.0 default, which would
        # otherwise look like a free hour and force a grid-charge.
        if (
            price_data_sufficient
            and buy_price_next_slot <= 0.0
            and not should_export
            and importable_kwh >= MIN_GRID_CHARGE_KWH
            and battery_soc < max_soc
            and not evcc_managing_battery
            and capped_charge_rate_kw >= GRID_MIN_CHARGE_KW
        ):
            should_grid_charge = True

        # ── Price chart data ──────────────────────────────────────────────────
        # When price_resolution_15min is enabled: emit every native slot (15-min or
        # whatever the DSO provides via EVCC).  Otherwise deduplicate to one row per
        # hour (backward-compatible Lovelace behaviour).
        price_resolution_15min = self._stored.get("price_resolution_15min", False)
        price_chart_slots: list[dict] = []
        if price_resolution_15min:
            for slot_start, dur_h, h, m, spot in grid_slot_data:
                buy_slot = round((spot + spot_markup + tariff_sched[h] + elafgift) * vat_factor, 3)
                # v0.59.11 — do NOT clamp at 0: show the true (possibly negative)
                # sell price so the matrix/chart reflect pay-to-export hours.
                sell_slot = round(spot - export_fee - feed_in_tariff, 3)
                price_chart_slots.append({"h": h, "m": m, "buy": buy_slot, "sell": sell_slot})
        else:
            seen_ch: set[int] = set()
            for slot_start, dur_h, h, m, spot in grid_slot_data:
                if h not in seen_ch:
                    seen_ch.add(h)
                    buy_slot = round((spot + spot_markup + tariff_sched[h] + elafgift) * vat_factor, 3)
                    # v0.59.11 — do NOT clamp at 0: show the true (possibly negative)
                    # sell price so the matrix/chart reflect pay-to-export hours.
                    sell_slot = round(spot - export_fee - feed_in_tariff, 3)
                    price_chart_slots.append({"h": h, "m": 0, "buy": buy_slot, "sell": sell_slot})

        # v0.48.1 — hourly, timestamped buy/sell price forecast over the FULL
        # horizon (today + tomorrow once day-ahead publishes ~13:00), for the
        # "price matrix" card. 15-min slots are averaged into their hour.
        hourly_acc: dict = {}
        for slot_start, dur_h, h, m, spot in grid_slot_data_opt:
            buy = (spot + spot_markup + tariff_sched[h] + elafgift) * vat_factor
            # v0.59.11 — unclamped so the price matrix shows negative sell prices.
            sell = spot - export_fee - feed_in_tariff
            key = slot_start.replace(minute=0, second=0, microsecond=0).isoformat()
            hourly_acc.setdefault(key, []).append((buy, sell))
        buy_price_forecast = [
            {
                "iso": k,
                "buy": round(sum(b for b, _ in v) / len(v), 3),
                "sell": round(sum(s for _, s in v) / len(v), 3),
            }
            for k, v in sorted(hourly_acc.items())
        ]

        # ── Solar forecast chart data (v0.28.2, 48 h) ───────────────────────
        # One entry per native forecast slot (hourly for Solcast, 15-min for
        # some Forecast.Solar setups). Each entry carries:
        #   start    — ISO timestamp of the slot start (with tz offset)
        #   raw_kw   — pure forecast source value (Solcast / Forecast.Solar)
        #   adj_kw   — same value scaled by the per-hour accuracy factor
        #              learned by the integration ("solcelleprognose"),
        #              i.e. what the DP optimizer actually plans against
        # The dashboard ApexCharts card on the EV/OCPP tab reads this via
        # data_generator to draw a two-series 48-h forecast (raw + adjusted).
        try:
            solar_hourly_acc_local = self.get_solar_hourly_accuracy_profile()
        except Exception:  # noqa: BLE001
            solar_hourly_acc_local = [1.0] * 24

        def _solar_adj_factor(slot_start_dt) -> float:
            try:
                h_local = slot_start_dt.astimezone().hour
                if 0 <= h_local < 24:
                    base = max(0.0, float(solar_hourly_acc_local[h_local]))
                    # v0.28.6: layer short-term residual onto the chart's
                    # adjusted curve, with linear decay so the user can SEE
                    # the immediate correction on the Solcelleprognose plot
                    try:
                        hours_ahead = max(0.0, (slot_start_dt - now).total_seconds() / 3600.0)
                        return base * self.get_short_term_solar_factor(hours_ahead)
                    except Exception:  # noqa: BLE001
                        return base
            except Exception:  # noqa: BLE001
                pass
            return 1.0

        solar_chart_slots: list[dict] = []
        # Daily kWh totals (v0.28.3) — split by local calendar date so the
        # dashboard can show "today remaining" vs "tomorrow expected".
        # Uses the slot's native duration so this works for both 30-min and
        # hourly forecast sources.
        local_today = now.astimezone().date()
        solar_today_remaining_raw_kwh = 0.0
        solar_today_remaining_adj_kwh = 0.0
        solar_tomorrow_raw_kwh = 0.0
        solar_tomorrow_adj_kwh = 0.0
        for slot_start, dur_h, h, m, watts in solar_slot_data_opt:
            raw_kw = round(float(watts) / 1000.0, 3)
            factor = _solar_adj_factor(slot_start)
            adj_kw = round(raw_kw * factor, 3)
            try:
                start_iso = slot_start.isoformat()
            except Exception:  # noqa: BLE001
                start_iso = str(slot_start)
            solar_chart_slots.append({
                "start": start_iso,
                "raw_kw": raw_kw,
                "adj_kw": adj_kw,
                "factor": round(factor, 3),
            })
            # Accumulate daily totals
            try:
                slot_local_date = slot_start.astimezone().date()
                dur_h_f = float(dur_h)
            except Exception:  # noqa: BLE001
                continue
            if slot_local_date == local_today:
                solar_today_remaining_raw_kwh += raw_kw * dur_h_f
                solar_today_remaining_adj_kwh += adj_kw * dur_h_f
            elif (slot_local_date - local_today).days == 1:
                solar_tomorrow_raw_kwh += raw_kw * dur_h_f
                solar_tomorrow_adj_kwh += adj_kw * dur_h_f

        # ── Tonight's plan (from DP optimizer) ───────────────────────────────
        # Prefer the optimizer plan; fall back to simple greedy if unavailable.
        if self._optimizer_plan:
            charge_hours = sorted({s["hour"] for s in self._optimizer_plan if s["action"] == "CHARGE"})
            export_hours = sorted({s["hour"] for s in self._optimizer_plan if s["action"] == "EXPORT"})

            # v0.47.2 — date-aware plan string: group the hours by day and tag
            # today / tomorrow, so e.g. tomorrow's 10h is not confused with a
            # (past) 10h today. Hours collapse to whole-hour labels for brevity.
            today_local = now.astimezone().date()

            def _fmt_plan(action: str) -> str:
                by_day: dict = {}
                for s in self._optimizer_plan:
                    if s["action"] != action:
                        continue
                    try:
                        d = datetime.fromisoformat(s["iso"]).astimezone().date()
                    except Exception:  # noqa: BLE001
                        d = today_local
                    by_day.setdefault(d, set()).add(s["hour"])
                if not by_day:
                    return self._msg("none", "ingen")
                parts = []
                for d in sorted(by_day):
                    hrs = ", ".join(f"{h:02d}h" for h in sorted(by_day[d]))
                    delta = (d - today_local).days
                    if delta <= 0:
                        label = self._msg("today", "i dag")
                    elif delta == 1:
                        label = self._msg("tomorrow", "i morgen")
                    else:
                        label = d.strftime("%a")
                    parts.append(f"{label} {hrs}")
                return "  |  ".join(parts)

            charge_str = _fmt_plan("CHARGE")
            export_str = _fmt_plan("EXPORT")
            none_label = self._msg("none", "ingen")
            if charge_str == none_label and export_str == none_label:
                # v0.49.0 — the optimizer ran and found nothing worth doing
                # today (e.g. prices too flat to clear the spread, battery
                # covered by solar). Spell that out so a bare "ingen · ingen"
                # doesn't read like an error or a failed calculation.
                plan_text = self._msg(
                    "No trades today — prices too flat to arbitrage (running on self-use)",
                    "Ingen handler i dag — priserne er for flade til arbitrage (kører på selvforbrug)",
                )
            else:
                plan_text = (
                    f"{self._msg('Charge', 'Køb')}: {charge_str}"
                    f"  ·  {self._msg('Export', 'Salg')}: {export_str}"
                )
        elif price_chart_slots:
            # Fallback: simple greedy sort (used before first optimizer run)
            sorted_by_buy = sorted(price_chart_slots, key=lambda s: s["buy"])
            seen_buy: set[int] = set()
            charge_hours = []
            for s in sorted_by_buy:
                if s["h"] not in seen_buy:
                    seen_buy.add(s["h"])
                    charge_hours.append(s["h"])
                if len(charge_hours) >= 3:
                    break
            charge_hours.sort()

            sorted_by_sell = sorted(price_chart_slots, key=lambda s: -s["sell"])
            seen_sell: set[int] = set()
            export_hours = []
            for s in sorted_by_sell:
                if s["sell"] <= min_export_price:
                    continue
                if s["h"] not in seen_sell:
                    seen_sell.add(s["h"])
                    export_hours.append(s["h"])
                if len(export_hours) >= 3:
                    break
            export_hours.sort()

            charge_str = ", ".join(f"{h:02d}h" for h in charge_hours) if charge_hours else "none"
            export_str = ", ".join(f"{h:02d}h" for h in export_hours) if export_hours else "none"
            plan_text = f"Charge: {charge_str}  ·  Export: {export_str}"
        else:
            charge_hours = export_hours = []
            plan_text = "No price data"

        # v0.59.3 — day-split plan hours for the dashboard, so tomorrow's actions
        # aren't drawn on today's grid (the flat charge/export hours are just
        # hour-of-day and can't tell today from tomorrow). Default: treat the
        # flat hours as today; override with date-aware splits when the optimizer
        # produced an iso-stamped plan.
        charge_hours_today = list(charge_hours)
        charge_hours_tomorrow: list = []
        export_hours_today = list(export_hours)
        export_hours_tomorrow: list = []
        if self._optimizer_plan:
            _plan_today = now.astimezone().date()

            def _split_day(action: str, delta: int) -> list:
                out: set = set()
                for s in self._optimizer_plan:
                    if s["action"] != action:
                        continue
                    try:
                        d = datetime.fromisoformat(s["iso"]).astimezone().date()
                    except Exception:  # noqa: BLE001
                        d = _plan_today
                    if (d - _plan_today).days == delta:
                        out.add(s["hour"])
                return sorted(out)

            charge_hours_today = _split_day("CHARGE", 0)
            charge_hours_tomorrow = _split_day("CHARGE", 1)
            export_hours_today = _split_day("EXPORT", 0)
            export_hours_tomorrow = _split_day("EXPORT", 1)

        # ---- execute action (skipped when disabled — data still reported) ----
        # v0.61.0 — also skip execution on an unreliable SoC read (hold current
        # state) so a phantom 0 can't trigger a spurious grid-charge/export.
        prev_mode = self._current_mode
        if self._enabled and soc_reliable:
            new_mode, reason = await self._execute_decision(
                should_export, should_grid_charge, export_price,
                grid_arbitrage_spread, buy_price_next_slot, buy_price_p25, price_p75,
                truly_exportable_kwh, importable_kwh, solar_will_fill,
                ev_charging_now, ev_likely_charging, ev_block_prob,
                evcc_battery_mode, evcc_managing_battery,
                capped_charge_rate_kw,
            )
            # ---- action log: detect export/charge session transitions ----
            # v0.75.8 — deliberately scoped inside this branch, not evaluated
            # unconditionally below. self._current_mode only ever changes
            # inside _execute_decision (via _transition_to), which this branch
            # is the sole caller of. Previously this ran every tick regardless,
            # comparing prev_mode against the LOCAL new_mode — which the `else`
            # branch below force-sets to MODE_DISABLED on a single transient
            # SoC-unreliable tick even though self._current_mode (and the
            # actual inverter state) never changed. That closed an open
            # export/charge session on the spot-glitch tick, and then failed
            # to reopen it once SoC recovered (prev_mode, still the untouched
            # self._current_mode, already matched the freshly recomputed
            # new_mode) — silently truncating revenue tracking for the rest
            # of a real, still-running session.
            if new_mode != prev_mode:
                if prev_mode in (MODE_EXPORTING, MODE_GRID_CHARGING):
                    await self._close_action_session(now, battery_soc, capacity_kwh)
                if new_mode == MODE_EXPORTING:
                    await self._open_action_session(now, "export", battery_soc, export_price)
                elif new_mode == MODE_GRID_CHARGING:
                    current_buy_price = round(
                        (spot_ex_vat + spot_markup + tariff_sched[current_local_hour] + elafgift)
                        * vat_factor,
                        4,
                    )
                    await self._open_action_session(now, "charge", battery_soc, current_buy_price)
        else:
            new_mode = MODE_DISABLED
            if self._enabled and not soc_reliable:
                reason = "Holding — battery SoC unavailable (waiting for a valid reading)"
            elif ev_charging_now:
                reason = "Disabled — EV actively charging"
            elif should_export:
                reason = "Disabled — would export if enabled"
            elif should_grid_charge:
                reason = "Disabled — would grid charge if enabled"
            elif ev_likely_charging:
                reason = f"Disabled — EV typically charges now ({ev_block_prob:.0%} learned)"
            else:
                reason = "Disabled — monitoring only"

        # ---- export limit (every tick — enforces solar floor even when disabled) ----
        await self._maintain_export_limit(export_price_raw, min_export_price, new_mode)
        # ---- grid-charge power (every tick — re-cap to LIVE headroom) ----
        # v0.65.0 — the charge power was only set on the transition into
        # GRID_CHARGING; if house load rose mid-charge the total grid draw could
        # exceed the breaker. Re-cap to current headroom each cycle.
        if self._enabled and soc_reliable:
            await self._maintain_charge_power(capped_charge_rate_kw, new_mode)
            # ---- export-floor hardware backstop (every tick — track a moving floor) ----
            # v0.75.6 — was previously only set once, at the transition into
            # EXPORTING. self._effective_floor_soc is recomputed every tick
            # regardless of mode (it can genuinely move mid-session as the DP
            # plan re-solves and the forecast/bridge shifts), so a session that
            # runs long enough could be left with a stale, too-low hardware
            # stop-point exactly during the stalled-tick scenario this backstop
            # exists to protect against. _apply_export_floor_min_soc() already
            # only ever raises (never lowers) and reads the live register value
            # each call, so re-asserting it every tick is a no-op unless the
            # floor has genuinely risen since the last write.
            if new_mode == MODE_EXPORTING:
                await self._apply_export_floor_min_soc(self._effective_floor_soc)

        # ---- PV-curtailment flag (v0.36.2) — read inverter reg 49251 every tick ----
        # The EV controller consumes this cached value to decide whether to
        # launch a curtailment probe. A failed read leaves the prior value
        # in place (sticky), which is the safe default — a transient modbus
        # blip should not toggle the probe state.
        flag = await self._read_pv_power_limited_flag(
            self.config.get("foxess_inverter_id", "")
        )
        if flag is not None:
            self._pv_power_limited_flag = flag

        # ---- v0.39.0 Auto-Full on negative buy price ----
        # When the opt-in switch is on and buy_price ≤ 0 for ≥
        # AUTO_FULL_DEBOUNCE_SECONDS AND the EV is plugged in AND the
        # master mode is not already Full, save the current mode and
        # switch to Full. On the next floor-block-close edge, restore
        # the saved mode. Manual mode changes and EV unplug both clear
        # the auto state. See operating_log v0.39.0 design lock entry.
        # v0.39.3 fix: was originally using `current_buy_price` which is
        # only defined inside the grid-charge conditional block further
        # down. `buy_price_next_slot` is the always-defined canonical
        # all-in buy price for the current/next slot (computed around
        # line 880 in both the grid_slots and empty-slots branches).
        await self._maybe_auto_full_negative_price(
            now_local=now, buy_price_now=buy_price_next_slot,
        )

        # ---- savings tracking (learning tick only — accumulates per interval_h) ----
        if is_learning_tick:
            self._update_savings(
                new_mode, should_export, should_grid_charge,
                export_price, grid_arbitrage_spread,
                battery_discharge_kw, battery_charge_kw,
                learned_charge_rate, truly_exportable_kwh, importable_kwh,
                grid_import_kw=grid_import_kw,
                buy_price_now=round(
                    (spot_ex_vat + spot_markup + tariff_sched[current_local_hour] + elafgift)
                    * vat_factor, 4,
                ),
                home_power_kw=max(0.0, home_power_w / 1000.0),
            )
        savings = self.get_savings_summary()
        actual_savings = self.get_actual_savings_summary()

        # ---- prediction scorecard (v0.43.0, M1) — observability only ----
        # Records the plan's predicted SoC vs realised SoC on 15-min rollover.
        # Does not influence any decision; written to _stored, saved below on
        # the learning tick.
        self._update_prediction_scorecard(now, battery_soc)

        # ---- EV charge controller (v0.26.0) — runs in its own asyncio loop ----
        # Main update just caches the inputs; the decoupled control loop reads
        # the cache at its configured cadence (default 10 s, range 5–60 s).
        self._cached_ev_inputs = {
            "evcc_state": evcc_state,
            "battery_soc": battery_soc,
            "floor_soc": float(floor_soc),
            "ts": datetime.now(),
        }
        ev_telemetry = self._latest_ev_telemetry

        # Harvest any completed OCPP sessions into the session log (v0.27.0)
        self._harvest_ocpp_sessions()
        # Snapshot charger metadata for restart recovery (v0.27.3)
        self._persist_charger_metadata()
        # Merge the embedded OCPP server's per-charger telemetry into the
        # result dict so the new charger_* sensors can read it (v0.27.0).
        # OCPP telemetry is the BASE and the EV telemetry goes on top: in
        # Modbus mode the EV telemetry carries the live charger_power_kw /
        # status / phase currents, which must not be clobbered by the dead
        # OCPP source (which reports 0). In OCPP mode the EV telemetry doesn't
        # set those keys, so the OCPP values come through unchanged (v0.57.0).
        ev_telemetry = {**self.get_charger_telemetry(), **ev_telemetry}

        # ---- save storage (learning tick only — avoids flash wear on fast ticks) ----
        if is_learning_tick:
            # v0.49.0 — refresh disk usage and evaluate the low-space alarm
            self._disk_usage = await self._async_disk_usage()
            await self._check_disk_alarm()
            await self._store.async_save(self._stored)

        return self._make_result(
            mode=new_mode,
            reason=reason,
            home_power_w=home_power_w,
            pv_power_w=pv_power_w,
            pv_power_kw=round(pv_power_w / 1000, 3),
            ev_charge_power_w=ev_charge_power_w,
            ev_mode=ev_mode,
            ev_connected=ev_connected,
            ev_charging_now=ev_charging_now,
            ev_charging_solar=ev_charging_solar,
            evcc_battery_mode=evcc_battery_mode,
            base_load_kw=base_load_kw,
            load_2h_avg_kw=load_2h_avg,
            load_28d_avg_kw=load_28d_avg,
            vacation_mode=vacation_mode,
            predicted_house_load_24h_kwh=predicted_house_load_24h,
            solar_kwh_24h=solar_kwh_raw,
            solar_kwh_6h=solar_kwh_6h_raw,
            solar_kwh_24h_adjusted=solar_kwh,
            solar_kwh_6h_adjusted=solar_kwh_6h,
            solar_accuracy_factor=solar_accuracy_factor,
            solar_will_fill=solar_will_fill,
            price_min=price_min,
            price_max=price_max,
            price_mean=price_mean,
            price_p25=price_p25,
            price_p75=price_p75,
            price_next_slot=price_next_slot,
            # v0.37.1 — all-in buy price for the next slot (VAT, tariffs, and
            # any retail-API source applied). Consumed by the new
            # `BatteryArbitrageBuyPriceBreakdownSensor` as the state value
            # so the dashboard's "Prissammensætning" card has a single
            # entity to read regardless of buy_price_mode.
            buy_price_next_slot=buy_price_next_slot,
            export_price=export_price,
            # v0.39.2 — export-stop indicator. True when the solar export
            # floor block is currently open (export limit register dropped
            # to 25 W because the live export price ≤ min_export_price).
            # Backs `binary_sensor.solar_ai_eksport_stop_aktiv` for the
            # EV/OCPP tab chip.
            export_stop_active=self._current_floor_block is not None,
            export_stop_start_ts=(
                self._current_floor_block.get("start_ts")
                if self._current_floor_block else None
            ),
            export_stop_floor=(
                self._current_floor_block.get("floor")
                if self._current_floor_block else None
            ),
            export_stop_price_at_start=(
                self._current_floor_block.get("price_at_start")
                if self._current_floor_block else None
            ),
            grid_arbitrage_spread=grid_arbitrage_spread,
            battery_soc=battery_soc,
            cell_temp_low=cell_temp_low,
            exportable_kwh=truly_exportable_kwh,
            importable_kwh=importable_kwh,
            learned_charge_rate=learned_charge_rate,
            time_to_charge_h=time_to_charge_h,
            should_export=should_export,
            should_grid_charge=should_grid_charge,
            # v0.59.19 — price-feed health, for the binary_sensor + dashboard badge.
            price_data_degraded=price_data_degraded,
            price_slots_count=len(grid_vals),
            price_last_good_iso=(
                self._last_tariff_refresh.isoformat()
                if (self._last_tariff_refresh is not None and self._last_tariff_fetch_ok)
                else None
            ),
            net_solar_for_battery=net_solar_for_battery,
            ev_block_prob=ev_block_prob,
            is_summer_mode=is_summer_mode,
            solar_28d_avg=solar_28d_avg,
            grid_power_kw=round(grid_import_kw, 3),
            grid_headroom_kw=round(grid_headroom_kw, 3),
            grid_max_kw=grid_max_kw,
            tariff_this_hour=tariff_this_hour,
            feed_in_tariff_dso=self._feed_in_tariff_dso,
            feed_in_tariff_energinet=self._feed_in_tariff_energinet,
            feed_in_tariff_total=feed_in_tariff,
            min_export_price=min_export_price,
            capped_charge_rate_kw=round(capped_charge_rate_kw, 3),
            learned_rates=self.get_all_learned_rates(),
            learned_capacity=learned_capacity,
            auto_efficiency=auto_efficiency,
            capacity_source="manual" if "battery_capacity" in self._stored else "configured",
            efficiency_source="auto" if auto_efficiency is not None else "configured",
            capacity_sample_count=len(self._stored.get("capacity_samples", [])),
            price_chart_slots=price_chart_slots,
            buy_price_forecast=buy_price_forecast,
            solar_chart_slots=solar_chart_slots,
            solar_today_remaining_raw_kwh=round(solar_today_remaining_raw_kwh, 2),
            solar_today_remaining_adj_kwh=round(solar_today_remaining_adj_kwh, 2),
            solar_tomorrow_raw_kwh=round(solar_tomorrow_raw_kwh, 2),
            solar_tomorrow_adj_kwh=round(solar_tomorrow_adj_kwh, 2),
            plan_text=plan_text,
            plan_charge_hours=charge_hours,
            plan_export_hours=export_hours,
            plan_charge_hours_today=charge_hours_today,
            plan_charge_hours_tomorrow=charge_hours_tomorrow,
            plan_export_hours_today=export_hours_today,
            plan_export_hours_tomorrow=export_hours_tomorrow,
            house_load_hourly=self.get_house_load_profile(),
            ev_max_kw=float(self._stored.get("ev_max_kw", 0.0)),
            action_log=self.get_action_log(20),
            action_log_count=len(self._stored.get("action_log", [])),
            solar_floor_log=self.get_solar_floor_log(20),
            solar_floor_log_count=len(self._stored.get("solar_floor_log", [])),
            # v0.49.0 — disk-space monitor / alarm
            disk_free_gb=self._disk_usage.get("free_gb"),
            disk_pct_free=self._disk_usage.get("pct_free"),
            disk_total_gb=self._disk_usage.get("total_gb"),
            disk_used_gb=self._disk_usage.get("used_gb"),
            disk_path=self._disk_usage.get("path"),
            disk_alarm_threshold_pct=float(self._stored.get(
                "disk_alarm_threshold_pct", DEFAULT_DISK_ALARM_THRESHOLD_PCT)),
            disk_low=self._disk_low,
            solar_hourly_factors=self.get_solar_hourly_accuracy_profile(),
            solar_hourly_samples=self.get_solar_hourly_sample_counts(),
            # v0.43.0 — S1 groundwork: per-hour forecast-ratio percentiles
            # (observability; not yet consumed by the optimiser).
            solar_hourly_p10=self.get_solar_hourly_percentile_profile(10),
            solar_hourly_p50=self.get_solar_hourly_percentile_profile(50),
            solar_hourly_p90=self.get_solar_hourly_percentile_profile(90),
            # v0.44.0 — S1: active confidence percentile the optimiser plans
            # against (50 = median = neutral).
            solar_confidence_pct=float(self._stored.get(
                "solar_confidence_pct", DEFAULT_SOLAR_CONFIDENCE_PCT,
            )),
            # v0.45.0 — E1: live EV session demand the optimiser is reserving
            # for the near-term horizon (0 = no forced session, falls back to
            # the learned hourly EV model).
            ev_dp_session_kw=round(ev_session_kw, 2),
            # v0.47.0 (C) — dynamic discharge floor (None when the feature is
            # off → the static floor slider is used) + the learned safety margin.
            dynamic_floor_soc=self._dynamic_floor_soc,
            dynamic_floor_active=bool(self._stored.get("dynamic_discharge_floor", False)),
            discharge_reserve_margin=self._reserve_factor(),
            overnight_reserve_samples=len(self._stored.get("overnight_ratio_samples", [])),
            model_health_ok=not self._model_health_issues,
            model_health_issues=list(self._model_health_issues),
            model_health_notes=list(self._model_health_notes),
            effective_floor_soc=int(floor_soc),
            # v0.28.6: short-term solar correction visibility
            solar_short_term_factor=round(self._st_solar_factor, 3),
            solar_short_term_samples=len(self._st_solar_residuals),
            solar_short_term_recent=list(self._st_solar_residuals[-4:]),
            solar_short_term_decay_h=self._st_solar_decay_hours,
            # v0.38.4 — diagnostic: timestamp of the most recent slot the
            # intra-hour learner dropped because the export floor was active.
            # None = never. Lets the dashboard / logbook confirm the
            # curtailment filter is firing as expected.
            solar_short_term_last_curtailed_skip=self._st_solar_last_curtailed_skip_iso,
            **ev_telemetry,
            **savings,
            **actual_savings,
            **self.get_export_income_summary(),
            **self.get_grid_balance_summary(),
            **self.get_prediction_accuracy_summary(),
        )

    # ------------------------------------------------------------------ #
    # Action execution                                                      #
    # ------------------------------------------------------------------ #

    async def _execute_decision(
        self,
        should_export: bool,
        should_grid_charge: bool,
        export_price: float,
        spread: float,
        buy_price_next_slot: float,
        buy_price_p25: float,
        price_p75: float,
        exportable_kwh: float,
        importable_kwh: float,
        solar_will_fill: bool,
        ev_charging_now: bool,
        ev_likely_charging: bool,
        ev_block_prob: float,
        evcc_battery_mode: str,
        evcc_managing_battery: bool,
        capped_charge_rate_kw: float = 0.0,
    ) -> tuple[str, str]:
        target_mode = MODE_NORMAL
        reason = "Conditions not met for export or grid charging"

        if should_export:
            target_mode = MODE_EXPORTING
            reason = (
                f"Exporting: sell price {export_price:.2f} DKK/kWh (peak ref p75 {price_p75:.2f}), "
                f"spread {spread:.2f} DKK/kWh, "
                f"{exportable_kwh:.1f} kWh available"
            )
        elif should_grid_charge:
            target_mode = MODE_GRID_CHARGING
            reason = (
                f"Grid charging: buy price {buy_price_next_slot:.2f} ≤ p25 {buy_price_p25:.2f} DKK/kWh (incl. tariffs + VAT), "
                f"{importable_kwh:.1f} kWh room available"
            )
        else:
            if ev_charging_now:
                reason = "EV actively charging (now/minpv) — holding battery for EVCC"
            elif evcc_managing_battery:
                reason = f"EVCC managing battery ({evcc_battery_mode}) — not overriding"
            elif solar_will_fill:
                reason = "Solar will fill battery — grid charging not needed"
            elif ev_likely_charging:
                reason = f"EV typically charges now ({ev_block_prob:.0%} learned) — skipping grid charge"

        if target_mode != self._current_mode:
            await self._transition_to(target_mode, capped_charge_rate_kw, reason=reason)

        self._current_mode = target_mode
        self._mode_reason = reason
        return target_mode, reason

    async def _transition_to(
        self,
        new_mode: str,
        capped_charge_rate_kw: float = 0.0,
        reason: str = "",
    ) -> None:
        """Handle transition between operating modes."""
        _LOGGER.info("Battery Arbitrage: transitioning %s → %s", self._current_mode, new_mode)

        inverter_id = self.config.get("foxess_inverter_id", "")
        session = async_get_clientsession(self.hass)
        evcc_url = self.config.get("evcc_url", "")
        # Only coordinate battery mode with EVCC when EVCC is the live-state source
        # (EVCC-only or hybrid mode). In FoxESS-only mode we own the battery and
        # there is no EVCC to coordinate with.
        live_source = self._setting(CONF_LIVE_DATA_SOURCE, DEFAULT_LIVE_DATA_SOURCE)
        coordinate_with_evcc = live_source in (LIVE_SOURCE_EVCC, LIVE_SOURCE_HYBRID) and evcc_url

        if new_mode == MODE_EXPORTING:
            # v0.47.6 — Force Discharge actively pushes the battery to the grid.
            # (The old "Feed-in First" only re-routes solar surplus and does not
            # discharge the battery at night, so arbitrage export never fired.)
            await self._set_work_mode(WORK_MODE_FORCE_DISCHARGE)
            # Set the discharge power: user export cap if configured, else 0 →
            # full rate (the entity's max). Always set it now that we Force
            # Discharge, so the inverter actually exports.
            max_export_kw = float(self._stored.get("max_export_kw", DEFAULT_MAX_EXPORT_KW))
            await self._set_discharge_power(max_export_kw)
            # v0.65.0 — HARDWARE floor backstop: raise the on-grid Min-SoC to the
            # export floor so Force Discharge physically stops at the floor even
            # if a Solar AI tick stalls. Restored the moment we leave EXPORTING.
            await self._apply_export_floor_min_soc(self._effective_floor_soc)
            # Tell EVCC to hold so it doesn't fight our export
            if coordinate_with_evcc:
                self._we_set_evcc_mode = True
                await self._evcc_post(session, evcc_url, f"{EVCC_API_BATTERY_MODE}/{EVCC_BATTERY_HOLD}")

        elif new_mode == MODE_GRID_CHARGING:
            # Force Charge: inverter charges battery from grid at grid-headroom-capped rate
            await self._restore_export_min_soc()  # leaving export — give the house its SoC back
            await self._set_work_mode(WORK_MODE_FORCE_CHARGE)
            await self._set_charge_power(inverter_id, max_kw=capped_charge_rate_kw)
            if coordinate_with_evcc:
                self._we_set_evcc_mode = True
                await self._evcc_post(session, evcc_url, f"{EVCC_API_BATTERY_MODE}/{EVCC_BATTERY_HOLD}")

        elif new_mode == MODE_NORMAL:
            await self._restore_export_min_soc()  # leaving export — give the house its SoC back
            await self._set_work_mode(WORK_MODE_SELF_USE)
            # Release EVCC back to normal only if WE were the one who set it to hold
            if coordinate_with_evcc and self._we_set_evcc_mode:
                self._we_set_evcc_mode = False
                await self._evcc_post(session, evcc_url, f"{EVCC_API_BATTERY_MODE}/{EVCC_BATTERY_NORMAL}")

        # Send HA notification on mode change if enabled
        if self._stored.get("notifications_enabled", False):
            await self._send_mode_notification(self._current_mode, new_mode, reason)

    async def _maintain_export_limit(
        self,
        export_price_raw: float,
        min_export_price: float,
        current_mode: str,
    ) -> None:
        """Set the FoxESS export limit register every tick.

        Three states:
          - Grid charging  → 0 W    (never export while buying cheap power)
          - Below floor    → 25 W   (block solar export at unprofitable prices)
          - Above floor    → 10 000 W (full export allowed)

        Only writes to the inverter when the limit actually changes, to avoid
        unnecessary register wear. Runs even when Solar AI is disabled so the
        floor is always enforced. Also fires mobile push notifications on
        10000 ↔ 25 transitions when the corresponding event toggle is on.

        The solar-floor open/close log tracks the underlying price condition
        independently of the register write/skip below it (see the v0.75.6
        comment inline) — it is not gated by "did the register value change."
        """
        if current_mode == MODE_GRID_CHARGING:
            limit_w = 0
        elif export_price_raw <= min_export_price:
            limit_w = 25
        else:
            limit_w = 10000

        # ── Solar floor log ───────────────────────────────────────────────
        # v0.75.6 — tracks the underlying price condition directly, not the
        # register value. limit_w is pinned to 0 whenever MODE_GRID_CHARGING
        # is active regardless of price, so the previous limit_w==25
        # transition check closed and reopened the floor block on every
        # grid-charge cycle that happened to overlap an already-active
        # floor — fragmenting one continuous block into several and
        # flickering binary_sensor.solar_ai_eksport_stop_aktiv, even though
        # the price never actually crossed the floor. Evaluated every tick,
        # ahead of the register-write skip below, so a genuine price
        # crossing that happens to land mid-grid-charge (where limit_w
        # doesn't change at all) still opens/closes the block correctly.
        # `_current_floor_block` is in-memory-only and starts None on every
        # restart, so this also naturally re-opens a block already in
        # effect at startup — the case the old -1→25 special-case existed
        # to catch — without needing to special-case it.
        price_below_floor = export_price_raw <= min_export_price
        was_below_floor = self._current_floor_block is not None
        if price_below_floor and not was_below_floor:
            _LOGGER.info(
                "Solar floor activated: price %.3f ≤ floor %.2f DKK/kWh "
                "— solar export blocked",
                export_price_raw, min_export_price,
            )
            self._open_floor_block(datetime.now(timezone.utc), export_price_raw, min_export_price)
        elif was_below_floor and not price_below_floor:
            _LOGGER.info(
                "Solar floor deactivated: solar export resumed "
                "(price %.3f, floor %.2f)",
                export_price_raw, min_export_price,
            )
            self._close_floor_block(datetime.now(timezone.utc), export_price_raw)

        prev_limit = self._last_export_limit
        if limit_w == prev_limit:
            return  # no change — skip the write

        inverter_id = self.config.get("foxess_inverter_id", "")
        await self._set_export_limit(inverter_id, limit_w)
        self._last_export_limit = limit_w

        # ── Solar floor notifications (intentionally narrower) ───────────
        # Notifications fire only on direct 10000↔25 transitions — i.e. the
        # genuine "price crossed the floor" events. 0↔25 cases (grid-charge
        # start/stop while floor is active) are already covered by the
        # existing charge-start/stop notifications and would be noise here.
        if prev_limit == 10000 and limit_w == 25:
            if self._stored.get("notify_solar_floor_blocked", False):
                await self._send_mobile_notification(
                    self._msg("☀️ Solar AI: Solar export blocked", "☀️ Solar AI: Solareksport blokeret"),
                    self._msg(
                        f"Price {export_price_raw:.3f} DKK/kWh is below floor "
                        f"{min_export_price:.2f} — solar export stopped",
                        f"Pris {export_price_raw:.3f} DKK/kWh er under gulv "
                        f"{min_export_price:.2f} — solareksport stoppet",
                    ),
                )
        elif prev_limit == 25 and limit_w == 10000:
            if self._stored.get("notify_solar_floor_resumed", False):
                await self._send_mobile_notification(
                    self._msg("☀️ Solar AI: Solar export resumed", "☀️ Solar AI: Solareksport genoptaget"),
                    self._msg(
                        f"Price {export_price_raw:.3f} DKK/kWh is above floor "
                        f"{min_export_price:.2f} — export active again",
                        f"Pris {export_price_raw:.3f} DKK/kWh er over gulv "
                        f"{min_export_price:.2f} — eksport aktiv igen",
                    ),
                )

    async def _set_work_mode(self, mode: str) -> None:
        entity = self.config.get("foxess_work_mode_entity", "select.foxessmodbus_work_mode")
        try:
            await self.hass.services.async_call(
                "select", "select_option",
                {"entity_id": entity, "option": mode},
                blocking=True,
            )
            _LOGGER.debug("Battery Arbitrage: set work mode → %s", mode)
        except Exception as err:
            _LOGGER.error("Failed to set FoxESS work mode to %s: %s", mode, err)

    async def _read_pv_power_limited_flag(self, inverter_id: str) -> bool | None:
        """Read the FoxESS "PV Power Limited" holding register (49251).

        Returns True when the inverter reports it is actively curtailing PV
        (MPPT throttled), False when the inverter is delivering all
        available PV, or None if the read fails. Used by the EV controller
        as the curtailment trigger (v0.36.2 — replaces the v0.30.1
        forecast-substitution heuristic).
        """
        if not inverter_id:
            return None
        try:
            from .const import FOXESS_PV_POWER_LIMITED_FLAG_REGISTER  # noqa: PLC0415
            resp = await self.hass.services.async_call(
                "foxess_modbus", "read_registers",
                {
                    "inverter": inverter_id,
                    "start_address": FOXESS_PV_POWER_LIMITED_FLAG_REGISTER,
                    "count": 1,
                    "type": "holding",
                },
                blocking=True,
                return_response=True,
            )
            values = ((resp or {}).get("values")
                      or (resp or {}).get("response", {}).get("values")
                      or {})
            raw = values.get(FOXESS_PV_POWER_LIMITED_FLAG_REGISTER)
            if raw is None:
                # Some service responses key by stringified address
                raw = values.get(str(FOXESS_PV_POWER_LIMITED_FLAG_REGISTER))
            return bool(int(raw)) if raw is not None else None
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Read PV-limited flag (reg 49251) failed: %s", err)
            return None

    async def _set_export_limit(self, inverter_id: str, limit_watts: int) -> None:
        """Write the FoxESS export limit register (46616)."""
        try:
            high = limit_watts // 65536
            low = limit_watts % 65536
            await self.hass.services.async_call(
                "foxess_modbus", "write_registers",
                {
                    "inverter": inverter_id,
                    "start_address": FOXESS_EXPORT_LIMIT_REGISTER,
                    "values": f"{high}, {low}",
                },
                blocking=True,
            )
            _LOGGER.debug("Battery Arbitrage: export limit → %dW", limit_watts)
        except Exception as err:
            _LOGGER.error("Failed to set export limit: %s", err)

    async def _maintain_charge_power(
        self, capped_charge_rate_kw: float, current_mode: str,
    ) -> None:
        """Re-cap the grid-charge power to the live grid headroom each cycle while
        grid-charging (v0.65.0). The power was previously set only at the
        transition into GRID_CHARGING, so a mid-charge rise in house load could
        push total grid draw (house + charge) over the breaker. Only writes when
        the cap moves by more than the deadband, to bound register wear. When the
        headroom collapses below the minimum, the decision layer stops the charge
        on the next cycle (should_grid_charge requires headroom ≥ GRID_MIN)."""
        if current_mode != MODE_GRID_CHARGING:
            self._last_charge_cap_kw = None
            return
        prev = self._last_charge_cap_kw
        if prev is not None and abs(capped_charge_rate_kw - prev) < CHARGE_RECAP_DEADBAND_KW:
            return
        self._last_charge_cap_kw = capped_charge_rate_kw
        await self._set_charge_power(
            self.config.get("foxess_inverter_id", ""), max_kw=capped_charge_rate_kw)

    async def _set_charge_power(self, inverter_id: str, max_kw: float = 0.0) -> None:
        """Set the Force Charge power to the learned rate, capped to grid headroom."""
        rate_kw = self.get_current_charge_rate()
        if rate_kw <= 0:
            rate_kw = 1.0   # fallback if not yet calibrated
        if max_kw > 0:
            rate_kw = min(rate_kw, max_kw)
        if rate_kw < GRID_MIN_CHARGE_KW:
            _LOGGER.warning("Battery Arbitrage: charge rate %.2f kW below minimum — skipping", rate_kw)
            return
        entity = self.config.get("foxess_force_charge_entity", "number.foxessmodbus_force_charge_power")
        # v0.47.6 — the FoxESS force-charge-power entity is in kW (not W). The
        # previous `int(rate_kw * 1000)` wrote watts into a 0–10 kW field, so the
        # set silently failed (out of range) and the power stayed at its max,
        # ignoring the grid-headroom cap. Write kW, clamped to the entity range.
        st = self.hass.states.get(entity)
        ent_max = float(st.attributes.get("max", 10.0)) if st else 10.0
        value = round(max(0.0, min(rate_kw, ent_max)), 3)
        try:
            await self.hass.services.async_call(
                "number", "set_value",
                {"entity_id": entity, "value": value},
                blocking=True,
            )
            _LOGGER.debug("Battery Arbitrage: force charge power → %.3f kW", value)
        except Exception as err:
            _LOGGER.error("Failed to set force charge power: %s", err)

    async def _apply_export_floor_min_soc(self, floor_soc: float) -> None:
        """v0.65.0 — raise the FoxESS on-grid Min-SoC to the export floor while
        Force-Discharging, so the inverter HARDWARE stops the sell at the floor
        even if a Solar AI tick stalls. The user's original value is saved (in
        storage, so it survives a restart) and restored when export ends — the
        floor must never block overnight HOUSE self-use, only the sell."""
        entity = self.config.get(CONF_FOXESS_MIN_SOC_ENTITY, FOXESS_MIN_SOC_ON_GRID_ENTITY)
        st = self.hass.states.get(entity)
        if st is None or st.state in ("unknown", "unavailable"):
            return  # entity not present (e.g. non-Modbus install) — soft floor only
        try:
            current = float(st.state)
        except (ValueError, TypeError):
            return
        target = float(max(0, min(100, round(floor_soc))))
        # Only raise (never lower the user's setting) and only act on a real change.
        if target <= current:
            return
        if self._stored.get("export_min_soc_prev") is None:
            self._stored["export_min_soc_prev"] = current
        try:
            await self.hass.services.async_call(
                "number", "set_value", {"entity_id": entity, "value": target}, blocking=True)
            _LOGGER.info("Export floor backstop: on-grid Min-SoC %.0f%% → %.0f%%", current, target)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Could not raise on-grid Min-SoC for export floor: %s", err)
            self._stored.pop("export_min_soc_prev", None)

    async def _restore_export_min_soc(self) -> None:
        """Restore the on-grid Min-SoC to the user's saved value after export, so
        overnight house self-use is never blocked. No-op if we never raised it."""
        prev = self._stored.get("export_min_soc_prev")
        if prev is None:
            return
        entity = self.config.get(CONF_FOXESS_MIN_SOC_ENTITY, FOXESS_MIN_SOC_ON_GRID_ENTITY)
        try:
            await self.hass.services.async_call(
                "number", "set_value",
                {"entity_id": entity, "value": float(prev)}, blocking=True)
            _LOGGER.info("Export floor backstop: on-grid Min-SoC restored to %.0f%%", float(prev))
            self._stored.pop("export_min_soc_prev", None)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Could not restore on-grid Min-SoC after export: %s", err)

    async def _set_discharge_power(self, max_kw: float) -> None:
        """Set the Force Discharge power (kW). `max_kw <= 0` → full rate (the
        entity's max).

        v0.47.6 — the FoxESS force-discharge-power entity is in kW (not W); the
        previous `int(max_kw * 1000)` wrote watts into a 0–10 kW field and the
        set silently failed. Write kW, clamped to the entity range.
        """
        entity = self.config.get("foxess_force_discharge_entity", FOXESS_FORCE_DISCHARGE_ENTITY)
        st = self.hass.states.get(entity)
        ent_max = float(st.attributes.get("max", 10.0)) if st else 10.0
        value = round(ent_max if max_kw <= 0 else max(0.0, min(float(max_kw), ent_max)), 3)
        try:
            await self.hass.services.async_call(
                "number", "set_value",
                {"entity_id": entity, "value": value},
                blocking=True,
            )
            _LOGGER.debug("Battery Arbitrage: force discharge power → %.3f kW", value)
        except Exception as err:
            _LOGGER.error("Failed to set force discharge power: %s", err)

    async def _send_mode_notification(
        self, old_mode: str, new_mode: str, reason: str
    ) -> None:
        """Fire a persistent HA notification when the operating mode changes."""
        _MODE_NAMES = {
            MODE_NORMAL: "Self-use",
            MODE_EXPORTING: "Exporting",
            MODE_GRID_CHARGING: "Grid charging",
            MODE_DISABLED: "Disabled",
        }
        old_name = _MODE_NAMES.get(old_mode, old_mode)
        new_name = _MODE_NAMES.get(new_mode, new_mode)
        title = f"Solar AI: {new_name}"
        message = reason or f"Mode changed from {old_name} to {new_name}"
        try:
            await self.hass.services.async_call(
                "persistent_notification", "create",
                {
                    "title": title,
                    "message": message,
                    "notification_id": "battery_arbitrage_mode",
                },
                blocking=False,
            )
        except Exception as err:
            _LOGGER.warning("Failed to send mode notification: %s", err)

    async def _evcc_post(self, session: aiohttp.ClientSession, base_url: str, path: str) -> None:
        try:
            async with session.post(f"{base_url}{path}", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status >= 400:
                    _LOGGER.warning("EVCC POST %s returned %s", path, resp.status)
        except Exception as err:
            _LOGGER.error("EVCC POST %s failed: %s", path, err)

    # ------------------------------------------------------------------ #
    # Learning models                                                       #
    # ------------------------------------------------------------------ #

    def get_ev_charge_probability(self) -> float:
        """Return the learned EV charging probability for the current hour (0–1)."""
        hour = datetime.now().hour
        hourly = self._stored.get("ev_charge_hourly", [0.0] * 24)
        if len(hourly) < 24:
            return 0.0
        return hourly[hour]

    def get_season_mode(self) -> tuple[bool, float]:
        """Return (is_summer, solar_28d_avg_kwh_per_day).

        is_summer = True when 28-day avg daily solar >= SEASON_SOLAR_THRESHOLD_KWH.
        Defaults to winter (conservative) until 7 days of history are available.
        """
        daily = self._stored.get("solar_daily_kwh", [])
        if len(daily) < 7:
            return False, 0.0
        avg = round(statistics.mean(daily[-SOLAR_DAILY_SAMPLES_MAX:]), 2)
        return avg >= SEASON_SOLAR_THRESHOLD_KWH, avg

    def _update_ev_charge_learning(self, ev_charge_power_w: float) -> None:
        """Exponentially update the learned EV charging probability for the current hour."""
        is_charging = ev_charge_power_w > self._ev_charge_threshold_w()
        hour = datetime.now().hour
        hourly: list[float] = self._stored.setdefault("ev_charge_hourly", [0.0] * 24)
        while len(hourly) < 24:
            hourly.append(0.0)
        hourly[hour] = round(
            (1 - EV_LEARNING_ALPHA) * hourly[hour]
            + EV_LEARNING_ALPHA * (1.0 if is_charging else 0.0),
            4,
        )

    def _update_ev_max_kw(self, ev_charge_power_w: float) -> None:
        """Learn the EV's maximum AC charge rate from high-power sessions.

        Only updates when EVCC is delivering at ≥ EV_MAX_KW_HIGH_POWER_FRACTION of
        the current learned max — meaning the car or charger (not solar surplus) is
        the bottleneck.  Solar-throttled sessions are ignored, so the learned value
        stays valid year-round regardless of seasonal solar availability.

        Hard ceiling: grid_max_kw — physically impossible to charge faster than the
        breaker allows.
        """
        if ev_charge_power_w <= self._ev_charge_threshold_w():
            return
        rate_kw = ev_charge_power_w / 1000.0
        current_max = float(self._stored.get("ev_max_kw", 0.0))
        grid_max = float(self._stored.get("grid_max_kw", GRID_MAX_KW))

        # Only learn from sessions at or near full speed
        threshold_kw = current_max * EV_MAX_KW_HIGH_POWER_FRACTION
        if current_max > 0 and rate_kw < threshold_kw:
            return  # Solar-throttled session — skip

        # Hard physical ceiling
        clamped = min(rate_kw, grid_max)
        self._stored["ev_max_kw"] = round(
            (1 - EV_MAX_KW_LEARNING_ALPHA) * current_max + EV_MAX_KW_LEARNING_ALPHA * clamped,
            3,
        )

    def _update_house_load_hourly(self, base_load_kw: float) -> None:
        """Exponentially update the learned house load for the current hour of day.

        Builds a 24-slot daily load profile (kW per hour) that the day-ahead
        optimizer uses instead of the flat 24h average.  Uses the same EMA
        approach as EV charge learning so the profile adapts gradually to
        changes in usage habits over ~8 days per hour slot.

        Outlier guard (two layers):
        1. Hard ceiling: grid_max_kw — no real house load can exceed the breaker.
        2. Soft ceiling: once the model is warm, clamp to HOUSE_LOAD_OUTLIER_FACTOR ×
           the current estimate.  A 5× factor allows genuine large spikes (sauna,
           heat pump + oven simultaneously) while blocking sensor errors.
        """
        now = datetime.now()
        hour = now.hour
        # v0.46.0 — L1: update the profile for the current day type (weekday
        # Mon–Fri vs weekend Sat/Sun). Weekends have a different load shape
        # (later mornings, more daytime presence) that a single blended curve
        # smears out.
        key = "house_load_weekend" if now.weekday() >= 5 else "house_load_weekday"
        hourly: list[float] = self._stored.setdefault(key, [0.0] * 24)
        while len(hourly) < 24:
            hourly.append(0.0)
        current = hourly[hour]
        grid_max = float(self._stored.get("grid_max_kw", GRID_MAX_KW))
        # Layer 1 — hard physical ceiling
        clamped = max(0.0, min(base_load_kw, grid_max))
        # Layer 2 — soft outlier rejection (only when model is warm)
        if current >= HOUSE_LOAD_WARM_THRESHOLD_KW:
            clamped = min(clamped, current * HOUSE_LOAD_OUTLIER_FACTOR)
        hourly[hour] = round(
            (1 - HOUSE_LOAD_LEARNING_ALPHA) * current + HOUSE_LOAD_LEARNING_ALPHA * clamped,
            3,
        )

    def get_house_load_profile(self, weekend: bool | None = None) -> list[float]:
        """Return the learned per-hour house load profile (kW, 24 values) for
        the requested day type (v0.46.0 — L1).

        `weekend=None` selects today's type. Each hour falls back, in order, to:
        its own learned value → the legacy combined profile → the other day
        type → the short-term rolling average — so the optimizer always has a
        reasonable estimate even before the split profiles have warmed up.
        """
        if weekend is None:
            weekend = datetime.now().weekday() >= 5
        key = "house_load_weekend" if weekend else "house_load_weekday"
        other_key = "house_load_weekday" if weekend else "house_load_weekend"
        profile = list(self._stored.get(key, [0.0] * 24))
        legacy = list(self._stored.get("house_load_hourly", [0.0] * 24))
        other = list(self._stored.get(other_key, [0.0] * 24))
        for src in (profile, legacy, other):
            while len(src) < 24:
                src.append(0.0)
        load_history = self._stored.get("load_history", [])
        fallback = _rolling_mean(load_history, VACATION_SHORT_WINDOW) if load_history else 0.5
        out: list[float] = []
        for h in range(24):
            v = profile[h]
            if v <= 0.0:
                v = legacy[h] if legacy[h] > 0.0 else (other[h] if other[h] > 0.0 else fallback)
            out.append(round(v, 3))
        return out

    def _predict_house_load_window(
        self, now: datetime, hours: float, vacation_mode: bool, load_2h: float,
    ) -> float:
        """Predict house energy (kWh) over the next `hours` (v0.47.5).

        Uses the learned weekday/weekend **hourly profile** for the daily shape
        — so a short-term spike is not extrapolated across the whole day (the
        old `load_2h × 1.1 × 24` blew a 2-hour evening peak up into a ~22 kWh
        day). A bounded recent-activity scaler keeps it responsive: if the last
        two hours ran hotter than the profile expects for the current hour, the
        whole-day estimate is nudged up, clamped to ±, so genuine busy days
        still register without a single spike dominating.
        """
        if vacation_mode:
            # Away: the normal profile doesn't apply — track the (low) live load.
            return round(max(load_2h, 0.05) * hours, 3)
        total = 0.0
        cur = now.astimezone()
        remaining = float(hours)
        while remaining > 1e-6:
            step = min(1.0, remaining)
            total += self.get_house_load_profile(weekend=cur.weekday() >= 5)[cur.hour] * step
            cur = cur + timedelta(hours=step)
            remaining -= step
        # Bounded recent-activity scaler (last 2 h vs the profile's value for the
        # current hour) — responsive but a transient spike can't run away.
        local = now.astimezone()
        typical_now = self.get_house_load_profile(weekend=local.weekday() >= 5)[local.hour]
        if load_2h > 0 and typical_now > 0.05:
            total *= max(0.8, min(1.4, load_2h / typical_now))
        return round(total, 3)

    # ── Dynamic self-learning discharge floor (v0.47.0 — C) ───────────────
    def _compute_dynamic_floor_soc(
        self, *, now: datetime, capacity_kwh: float, efficiency: float,
        solar_slot_data: list, grid_charge_kw: float,
    ) -> float | None:
        """Discharge floor that reserves enough SoC to run the house through the
        next *dark bridge* — the upcoming stretch where solar doesn't cover the
        house — until solar covers it again, *net of* any grid-charge the
        optimiser has planned to put back during the bridge, times a learned
        safety margin. Returns SoC %, clamped to the health band, or None if
        inputs are thin.

        v0.47.1 fix: the reserve is computed for the *next bridge* (e.g.
        tonight's sunset→sunrise), NOT "from now". Otherwise, during the day or
        before sunset the next refill is ~now, the reserve collapses to ~0, and
        the floor clamps to the minimum — which would let the pre-sunset export
        over-deplete the battery before the night even starts. The reserve is
        added on top of the hardware minimum SoC (the battery only delivers down
        to that floor), so the returned floor = hardware_floor + reserve%.

        v0.53.0 fix: only *solar covering the house* ends the dark bridge. A
        planned grid-charge no longer counts as a "refill" that ends it — it is
        instead credited for the energy it actually puts back (charge power ×
        planned hours), so a token charge offsets almost nothing and the floor
        stays high enough to protect the night, while a genuine multi-hour cheap
        charge offsets a lot and lets more be exported. The old binary treatment
        let any planned charge — even a 10-minute one — dissolve the whole
        bridge, dropping the floor to the bare minimum and letting the evening
        export sell the SoC the house needed overnight (drain to ~11 %).
        """
        if capacity_kwh <= 0 or not solar_slot_data:
            return None

        onset = float(DYNAMIC_FLOOR_SOLAR_ONSET_FACTOR)

        # Planned grid-charge slot start times from the optimiser plan.
        planned_charge_dts: list = []
        for ps in (self._optimizer_plan or []):
            if ps.get("action") == "CHARGE":
                try:
                    planned_charge_dts.append(datetime.fromisoformat(ps["iso"]))
                except (ValueError, KeyError, TypeError):
                    pass

        # Build future slots: (start, house_kw, dur_h, solar_covers, charge_here).
        # solar_covers is the ONLY thing that ends the bridge; charge_here is
        # tracked separately so the planned-charge energy can be netted off.
        slots: list[tuple] = []
        for s in solar_slot_data:
            slot_start, dur_h = s[0], s[1]
            # include the slot currently in progress + all future ones
            if (slot_start - now).total_seconds() < -900:
                continue
            loc = slot_start.astimezone()
            house_kw = self.get_house_load_profile(weekend=loc.weekday() >= 5)[loc.hour]
            # v0.60.1 — correct the forecast by the learned per-hour accuracy
            # factor. Using the raw (often optimistic) forecast here made the
            # floor think solar covered the house earlier than it really
            # would, shortening the dark bridge and under-reserving for the
            # night.
            # v0.75.13 — now uses get_solar_confidence_factor_for_hour, the
            # same confidence-percentile mechanism _dp_solve's _slot_factor
            # already used (this comment used to claim the two matched
            # "exactly" — they hadn't, since v0.44.0 upgraded the DP's copy
            # and left this one on the plain median). At the default 50th
            # percentile this is numerically identical to before; lowering
            # solar_confidence_pct now makes the floor more conservative too,
            # not just the DP's own price plan.
            solar_kw = (s[4] / 1000.0) * self.get_solar_confidence_factor_for_hour(loc.hour)
            solar_covers = house_kw > 0 and solar_kw >= onset * house_kw
            slot_end = slot_start + timedelta(hours=float(dur_h))
            charge_here = any(slot_start <= pc < slot_end for pc in planned_charge_dts)
            slots.append((slot_start, house_kw, float(dur_h), solar_covers, charge_here, solar_kw))

        if not slots:
            return None

        # Next bridge = first upcoming slot where solar does NOT cover the house.
        start_idx = next((i for i, x in enumerate(slots) if not x[3]), None)
        if start_idx is None:
            # Solar covers the house across the whole horizon — no bridge.
            return float(DYNAMIC_FLOOR_MIN_SOC)

        # Across the dark bridge (until solar covers the house again, or the
        # horizon cap): sum the house energy consumed and the grid-charge hours
        # planned within it.
        #
        # v0.75.13 — house energy is now netted against that slot's own solar
        # (max(0, house_kw - solar_kw)) instead of reserving the full house
        # load for every slot until the onset threshold trips. Before, a slot
        # where solar was already covering 60% of house load — mid dawn-ramp,
        # not yet at the DYNAMIC_FLOOR_SOLAR_ONSET_FACTOR threshold that ends
        # the bridge — was reserved at 100% anyway, over-sizing the floor
        # exactly through the highest-value morning hours. This only changes
        # how much is reserved WITHIN the bridge; the onset threshold that
        # decides when the bridge ENDS (solar_covers, used for the break
        # below) is completely unchanged, so the specific past incident that
        # threshold was raised to fix (the bridge ending too early at first
        # light) isn't touched by this change. And solar_kw here is already
        # the confidence-percentile-corrected value (v0.75.13, see
        # get_solar_confidence_factor_for_hour above) — not the raw
        # forecast — so netting it stays exactly as conservative as the user
        # already set solar_confidence_pct to be.
        bridge_house_kwh = 0.0
        bridge_charge_h = 0.0
        bridge_h = 0.0
        for i in range(start_idx, len(slots)):
            _st, house_kw, dur_h, solar_covers, charge_here, solar_kw = slots[i]
            if i > start_idx and solar_covers:
                break
            if bridge_h >= DYNAMIC_FLOOR_REFILL_MAX_H:
                break
            bridge_house_kwh += max(0.0, house_kw - solar_kw) * dur_h
            if charge_here:
                bridge_charge_h += dur_h
            bridge_h += dur_h

        eff = max(efficiency, 0.5)
        # v0.61.0 — a safety factor on the deterministic reserve, NOT the old
        # self-learning integrator (which ratcheted on noise and was poisoned by
        # post-restart SoC=0 reads → pegged the floor at the 85% cap). v0.61.x
        # step 2: this is the empirical percentile (default 80, v0.75.14 —
        # user-configurable via 'Reserve percentile') of the overnight
        # house-load forecast error over clean nights once warm, clamped to a
        # sane band, falling back to the fixed factor until then — so it adapts
        # to this house's variance but can never leave
        # [RESERVE_FACTOR_MIN, RESERVE_FACTOR_MAX].
        margin = self._reserve_factor()
        # Battery energy the house will draw over the bridge (discharge losses in).
        house_need_kwh = bridge_house_kwh / eff
        # Energy a planned grid-charge actually returns to the battery over the
        # bridge (charge losses in). Credited in PROPORTION to how long it runs —
        # a token charge offsets almost nothing, a real multi-hour cheap charge
        # offsets a lot. grid_charge_kw is the continuously-learned *sustained*
        # charge rate (mean of real samples, not the p90 peak), so the credit
        # reflects what a planned charge realistically delivers. 0 → no credit,
        # which is the safe/conservative direction.
        charge_kwh = max(0.0, float(grid_charge_kw)) * bridge_charge_h * eff
        reserve_kwh = max(0.0, house_need_kwh - charge_kwh) * margin
        # The battery only delivers down to the hardware minimum SoC
        # (DYNAMIC_FLOOR_MIN_SOC), so the reserve must sit ON TOP of it: the
        # export floor = hardware_floor + reserve%. Otherwise only
        # (floor − hardware_floor) would actually be usable overnight.
        floor_soc = float(DYNAMIC_FLOOR_MIN_SOC) + reserve_kwh / capacity_kwh * 100.0
        return min(float(DYNAMIC_FLOOR_MAX_SOC), floor_soc)

    def _update_daily_solar(self, pv_power_w: float) -> None:
        """Accumulate today's solar production; push to daily log when day rolls over."""
        today = datetime.now().date().isoformat()
        prev_date = self._stored.get("solar_today_date", "")
        if prev_date != today:
            if prev_date:  # Don't push on very first run
                daily: list[float] = self._stored.setdefault("solar_daily_kwh", [])
                daily.append(round(self._stored.get("solar_today_kwh", 0.0), 3))
                if len(daily) > SOLAR_DAILY_SAMPLES_MAX:
                    del daily[: len(daily) - SOLAR_DAILY_SAMPLES_MAX]
            self._stored["solar_today_date"] = today
            self._stored["solar_today_kwh"] = 0.0
        kwh_this_tick = pv_power_w / 1000 * (LEARNING_TICK_INTERVAL_SECONDS / 3600)
        self._stored["solar_today_kwh"] = round(
            self._stored.get("solar_today_kwh", 0.0) + kwh_this_tick, 4
        )

    def _update_load_history(self, base_load_kw: float) -> None:
        history: list[float] = self._stored.setdefault("load_history", [])
        history.append(round(base_load_kw, 3))
        if len(history) > LOAD_HISTORY_MAX_SAMPLES:
            del history[: len(history) - LOAD_HISTORY_MAX_SAMPLES]

    # ── Overnight reserve-factor learning (v0.61.x step 2) ────────────────
    # Passively measures the overnight house-load forecast error (actual vs
    # profile-predicted core-night house energy) over CLEAN nights, then sizes
    # the reserve factor as a configurable percentile (default 80) of that
    # error — clamped, with the fixed factor as the fallback until warm.
    # Mirrors the _update_daily_solar
    # date-rollover pattern. base_load_kw already excludes the EV, so the EV
    # never contaminates the house-load measurement.
    def _overnight_window_key(self, now: datetime) -> str:
        """Return the night-id (date the evening started) when `now` is inside the
        core-night window, else "" (daytime). A night spanning midnight keeps one
        key so it accumulates as a single sample."""
        local = now.astimezone()
        h = local.hour
        if h >= OVERNIGHT_START_HOUR:
            return local.date().isoformat()
        if h < OVERNIGHT_END_HOUR:
            return (local.date() - timedelta(days=1)).isoformat()
        return ""

    def _update_overnight_reserve_learning(
        self, now: datetime, base_load_kw: float, soc_reliable: bool,
    ) -> None:
        cur_key = self._overnight_window_key(now)
        prev_key = self._stored.get("overnight_night_id", "")
        if prev_key != cur_key:
            if prev_key:  # a night just ended — finalize it
                self._finalize_overnight_sample()
            self._stored["overnight_night_id"] = cur_key
            self._stored["overnight_actual_kwh"] = 0.0
            self._stored["overnight_ticks"] = 0
            self._stored["overnight_dirty"] = False
        if not cur_key:
            return  # daytime — nothing to accumulate
        tick_h = LEARNING_TICK_INTERVAL_SECONDS / 3600.0
        self._stored["overnight_actual_kwh"] = round(
            self._stored.get("overnight_actual_kwh", 0.0) + max(0.0, base_load_kw) * tick_h, 4,
        )
        self._stored["overnight_ticks"] = self._stored.get("overnight_ticks", 0) + 1
        if not soc_reliable:
            self._stored["overnight_dirty"] = True

    def _finalize_overnight_sample(self) -> None:
        """Close the completed night: if it was clean and well-covered, append the
        actual/predicted house-energy ratio to the rolling window."""
        actual = float(self._stored.get("overnight_actual_kwh", 0.0))
        ticks = int(self._stored.get("overnight_ticks", 0))
        dirty = bool(self._stored.get("overnight_dirty", False))
        # Predicted core-night HOUSE energy from the learned hourly profile (kWh;
        # each profile entry is kW held for one hour). No efficiency term — both
        # sides are house-side energy, so it cancels in the ratio.
        profile = self.get_house_load_profile()
        hours = list(range(OVERNIGHT_START_HOUR, 24)) + list(range(0, OVERNIGHT_END_HOUR))
        predicted = sum(profile[h] for h in hours if 0 <= h < 24)
        if dirty or ticks < OVERNIGHT_MIN_TICKS or predicted < 0.5 or actual < 0.1:
            return  # not a clean, usable night
        ratio = actual / predicted
        if not (RESERVE_RATIO_SANE_LO <= ratio <= RESERVE_RATIO_SANE_HI):
            return  # wild outlier — drop
        samples: list[float] = self._stored.setdefault("overnight_ratio_samples", [])
        samples.append(round(ratio, 3))
        if len(samples) > OVERNIGHT_SAMPLES_MAX:
            del samples[: len(samples) - OVERNIGHT_SAMPLES_MAX]

    def _reserve_factor(self) -> float:
        """Effective reserve safety factor for the dynamic floor. Once warm, the
        empirical percentile (v0.75.14 — user-configurable via 'Reserve
        percentile', default 80) of clean-night forecast error, clamped to the
        safety band. Until then, the user-set 'Reserve safety factor' number
        (v0.66.0, default 1.3) — so the reserve can be tuned immediately (lower =
        sell more into peaks, higher = hold more for the night) before the data
        takes over."""
        samples: list[float] = self._stored.get("overnight_ratio_samples", [])
        if len(samples) < OVERNIGHT_MIN_NIGHTS:
            manual = float(self._stored.get(
                "reserve_factor_manual", DYNAMIC_FLOOR_RESERVE_FACTOR))
            return round(max(1.0, min(2.0, manual)), 3)
        pct = float(self._stored.get(
            "reserve_percentile_pct", DEFAULT_RESERVE_PERCENTILE_PCT)) / 100.0
        s = sorted(samples)
        k = (len(s) - 1) * pct
        lo = int(k)
        hi = min(lo + 1, len(s) - 1)
        p = s[lo] + (s[hi] - s[lo]) * (k - lo)
        return round(max(RESERVE_FACTOR_MIN, min(RESERVE_FACTOR_MAX, p)), 3)

    def _blocked_sell_hours(self) -> set[int]:
        """Parse the user's 'Blocked sell hours' text (comma-separated hours of
        day, e.g. "20,21") into a set of ints (v0.66.0). Robust to whitespace and
        garbage; values outside 0–23 are ignored."""
        raw = str(self._stored.get("blocked_sell_hours", "") or "")
        hours: set[int] = set()
        for tok in raw.replace(";", ",").split(","):
            tok = tok.strip()
            if not tok:
                continue
            try:
                h = int(tok)
            except ValueError:
                continue
            if 0 <= h <= 23:
                hours.add(h)
        return hours

    async def toggle_blocked_sell_hour(self, hour: int) -> None:
        """Toggle one hour-of-day in the blocked-sell-hours set (v0.66.1) — backs
        the clickable hour grid on the dashboard via the
        battery_arbitrage.toggle_blocked_sell_hour service."""
        if not (0 <= hour <= 23):
            return
        hours = self._blocked_sell_hours()
        hours.discard(hour) if hour in hours else hours.add(hour)
        self._stored["blocked_sell_hours"] = ",".join(str(h) for h in sorted(hours))
        if self.hass:
            await self._store.async_save(self._stored)
            await self.async_request_refresh()

    def _update_vacation_mode(self, load_2h: float, load_28d: float) -> bool:
        counter: int = self._stored.get("vacation_counter", 0)
        baseline = load_28d if load_28d > 0.05 else 0.2
        if load_2h < baseline * VACATION_THRESHOLD:
            counter = min(counter + 1, VACATION_MIN_DURATION + 1)
        else:
            counter = max(counter - 1, 0)
        self._stored["vacation_counter"] = counter
        return counter >= VACATION_MIN_DURATION

    def _calibrate_charge_rate(
        self, cell_temp: float, charge_kw: float, soc: float, work_mode: str
    ) -> None:
        if (
            work_mode != WORK_MODE_FORCE_CHARGE
            or charge_kw < CALIBRATION_MIN_CHARGE_KW
            or soc >= CALIBRATION_MAX_SOC
        ):
            return
        bucket = _temp_bucket(cell_temp)
        if bucket is None:
            return
        samples: list[float] = self._stored["charge_samples"].setdefault(bucket, [])
        samples.append(round(charge_kw, 3))
        if len(samples) > CALIBRATION_MAX_SAMPLES:
            del samples[: len(samples) - CALIBRATION_MAX_SAMPLES]
        if len(samples) >= 3:
            idx = int(0.90 * len(samples))
            learned = sorted(samples)[idx]
            self._stored["charge_rates"][bucket] = round(learned, 3)
            _LOGGER.debug(
                "Calibrated charge rate for %s: %.2f kW (%d samples)",
                bucket, learned, len(samples)
            )

    def _learn_capacity(self, battery_soc: float, battery_charge_kw: float) -> None:
        """Sample usable battery capacity from Force Charge ticks.

        During each charging tick we know energy_in and delta_SoC, giving:
            capacity = energy_in / (delta_SoC / 100)

        Samples are collected only when SoC is in the mid-range to avoid BMS
        edge effects near empty or full. The median of the rolling sample window
        is used as the learned value, which is robust to occasional outliers.
        """
        if self._prev_soc is None:
            self._prev_soc = battery_soc
            return

        delta_soc = battery_soc - self._prev_soc
        self._prev_soc = battery_soc

        if (
            self._current_mode == MODE_GRID_CHARGING
            and battery_charge_kw >= CAPACITY_MIN_CHARGE_KW
            and CAPACITY_MIN_SOC <= battery_soc <= CAPACITY_MAX_SOC
            and delta_soc >= CAPACITY_MIN_DELTA_SOC
        ):
            interval_h = LEARNING_TICK_INTERVAL_SECONDS / 3600
            energy_in_kwh = battery_charge_kw * interval_h
            capacity_sample = round(energy_in_kwh / (delta_soc / 100), 2)
            # Sanity-check: plausible battery size 3–30 kWh
            if 3.0 <= capacity_sample <= 30.0:
                samples: list[float] = self._stored.setdefault("capacity_samples", [])
                samples.append(capacity_sample)
                if len(samples) > CAPACITY_MAX_SAMPLES:
                    del samples[: len(samples) - CAPACITY_MAX_SAMPLES]

    def get_learned_capacity(self) -> float | None:
        """Return median of capacity samples, or None if not enough data yet."""
        samples: list[float] = self._stored.get("capacity_samples", [])
        if len(samples) < CAPACITY_MIN_SAMPLES:
            return None
        return round(statistics.median(samples), 2)

    def get_auto_efficiency(self) -> float | None:
        """Return round-trip efficiency from FoxESS lifetime energy totals.

        Uses the inverter's own cumulative charge/discharge counters, which
        are hardware-accurate and available immediately on any existing install.
        Returns None if there isn't enough lifetime data yet.
        """
        charge_total = self._get_float_state(self.config.get(CONF_BATTERY_CHARGE_TOTAL_ENTITY, FOXESS_BATTERY_CHARGE_TOTAL))
        discharge_total = self._get_float_state(self.config.get(CONF_BATTERY_DISCHARGE_TOTAL_ENTITY, FOXESS_BATTERY_DISCHARGE_TOTAL))
        if (
            charge_total is None
            or discharge_total is None
            or charge_total < EFFICIENCY_MIN_TOTAL_KWH
        ):
            return None
        eff = discharge_total / charge_total
        # Sanity check: round-trip efficiency should be between 70–99 %
        if not 0.70 <= eff <= 0.99:
            return None
        return round(eff, 4)

    def _update_savings(
        self,
        mode: str,
        should_export: bool,
        should_grid_charge: bool,
        export_price: float,
        grid_spread: float,
        battery_discharge_kw: float,
        battery_charge_kw: float,
        learned_rate_kw: float,
        exportable_kwh: float,
        importable_kwh: float,
        grid_import_kw: float = 0.0,
        buy_price_now: float = 0.0,
        home_power_kw: float = 0.0,
    ) -> None:
        """Accumulate actual and missed DKK savings into today's daily log entry."""
        interval_h = LEARNING_TICK_INTERVAL_SECONDS / 3600  # 5/60 h

        today = datetime.now().date().isoformat()
        log: list[dict] = self._stored.setdefault("savings_log", [])

        # Roll to a new day entry when needed
        if not log or log[-1]["date"] != today:
            log.append({"date": today, "actual_dkk": 0.0, "missed_dkk": 0.0})
            if len(log) > SAVINGS_LOG_MAX_DAYS:
                del log[: len(log) - SAVINGS_LOG_MAX_DAYS]

        entry = log[-1]

        # v0.42.0 — cumulative income from ALL exported energy (solar excess +
        # battery-to-grid arbitrage), independent of mode. `feed_in` is the live
        # grid-export power; income ≈ feed_in × interval × net export price.
        # Kept as a running total (for the TOTAL_INCREASING sensor / HA
        # statistics / Energy dashboard) plus a daily log (for period totals).
        from .const import CONF_FOXESS_GRID_EXPORT_ENTITY, FOXESS_FEED_IN  # noqa: PLC0415
        feed_in_kw = self._get_float_state(
            self.config.get(CONF_FOXESS_GRID_EXPORT_ENTITY, FOXESS_FEED_IN), 0.0,
        ) or 0.0
        if feed_in_kw > 0 and export_price > 0:
            inc = feed_in_kw * interval_h * export_price
            self._stored["export_income_total"] = round(
                self._stored.get("export_income_total", 0.0) + inc, 4,
            )
            ilog: list[dict] = self._stored.setdefault("export_income_log", [])
            if not ilog or ilog[-1]["date"] != today:
                ilog.append({"date": today, "dkk": 0.0})
                if len(ilog) > 400:        # ~13 months of daily history
                    del ilog[: len(ilog) - 400]
            ilog[-1]["dkk"] = round(ilog[-1]["dkk"] + inc, 4)

        # v0.48.0 — cumulative cost of ALL grid import (house load + battery
        # grid-charging), for the net grid-balance figure. cost ≈ grid_import_kw
        # × interval × full buy price. Mirrors export_income; capped daily log.
        if grid_import_kw > 0 and buy_price_now > 0:
            cost = grid_import_kw * interval_h * buy_price_now
            self._stored["import_cost_total"] = round(
                self._stored.get("import_cost_total", 0.0) + cost, 4,
            )
            clog: list[dict] = self._stored.setdefault("import_cost_log", [])
            if not clog or clog[-1]["date"] != today:
                clog.append({"date": today, "dkk": 0.0})
                if len(clog) > 400:
                    del clog[: len(clog) - 400]
            clog[-1]["dkk"] = round(clog[-1]["dkk"] + cost, 4)

        # v0.67.0 — baseline "no solar / no battery" house cost: what running the
        # house from the grid would have cost this tick (full house consumption ×
        # buy price). The true total saving the system delivers is then
        #   savings = baseline_cost − import_cost + export_income
        # which automatically captures solar self-consumption, battery savings,
        # arbitrage AND the cost of grid-charging — all at the meter level.
        if home_power_kw > 0 and buy_price_now > 0:
            base = home_power_kw * interval_h * buy_price_now
            self._stored["baseline_cost_total"] = round(
                self._stored.get("baseline_cost_total", 0.0) + base, 4,
            )
            blog: list[dict] = self._stored.setdefault("baseline_cost_log", [])
            if not blog or blog[-1]["date"] != today:
                blog.append({"date": today, "dkk": 0.0})
                if len(blog) > 400:
                    del blog[: len(blog) - 400]
            blog[-1]["dkk"] = round(blog[-1]["dkk"] + base, 4)

        if mode == MODE_EXPORTING and battery_discharge_kw > 0 and export_price > 0:
            # Actual export revenue from the battery portion
            entry["actual_dkk"] = round(
                entry["actual_dkk"] + battery_discharge_kw * interval_h * export_price, 4
            )
        elif mode == MODE_GRID_CHARGING and battery_charge_kw > 0 and grid_spread > 0:
            # Estimated future value: cheap kWh bought × arbitrage spread
            entry["actual_dkk"] = round(
                entry["actual_dkk"] + battery_charge_kw * interval_h * grid_spread, 4
            )
        elif mode == MODE_DISABLED:
            # Estimate what we *would* have done — use learned rate as proxy for discharge/charge speed
            fallback_kw = max(learned_rate_kw, 1.0)  # min 1 kW if not yet calibrated
            if should_export and export_price > 0 and exportable_kwh > 0:
                # Cap at what's physically available in this interval
                rate_kw = min(fallback_kw, exportable_kwh / interval_h)
                entry["missed_dkk"] = round(
                    entry["missed_dkk"] + rate_kw * interval_h * export_price, 4
                )
            elif should_grid_charge and grid_spread > 0 and importable_kwh > 0:
                rate_kw = min(fallback_kw, importable_kwh / interval_h)
                entry["missed_dkk"] = round(
                    entry["missed_dkk"] + rate_kw * interval_h * grid_spread, 4
                )

    def _update_solar_accuracy(
        self, forecast_w: float, actual_w: float, *, curtailed: bool = False,
    ) -> None:
        """Append a (forecast, actual) PV power pair to the rolling sample buffer
        AND to the per-hour bucket for the current local hour.

        The per-hour buckets let the optimizer learn the *shape* of real output
        vs forecast — orientation effects (east panels over-forecast in afternoon,
        etc.) without the user telling us anything about the panels.

        v0.30.1: when `curtailed` is True (the solar export floor is currently
        active and the FoxESS MPPT is throttling the panels to match local
        consumption), the sample is dropped instead of recorded — comparing
        forecast against deliberately-throttled production would skew the
        learning toward "panels always under-perform".
        """
        if curtailed:
            return
        sample = {"f": round(forecast_w, 0), "a": round(actual_w, 0)}
        # Global rolling buffer (existing behaviour, used as fallback)
        samples: list[dict] = self._stored.setdefault("solar_accuracy_samples", [])
        samples.append(sample)
        if len(samples) > SOLAR_ACCURACY_MAX_SAMPLES:
            del samples[: len(samples) - SOLAR_ACCURACY_MAX_SAMPLES]
        # Per-hour bucket
        hour_key = str(datetime.now().hour)
        by_hour: dict = self._stored.setdefault("solar_accuracy_by_hour", {})
        bucket: list[dict] = by_hour.setdefault(hour_key, [])
        bucket.append(sample)
        if len(bucket) > SOLAR_ACCURACY_HOUR_BUCKET_MAX:
            del bucket[: len(bucket) - SOLAR_ACCURACY_HOUR_BUCKET_MAX]

    # ── Short-term solar correction (v0.28.6) ─────────────────────────────
    def _update_short_term_solar_correction(
        self,
        now: datetime,
        pv_power_w: float,
        solar_rates: list,
    ) -> None:
        """Track actual PV vs Solcast in 15-min slots and update the
        rolling short-term multiplier.

        Called every coordinator tick. Behaviour:
          1. Quantise `now` to the current 15-min slot.
          2. Accumulate live PV (W) into the slot's running mean.
          3. Accumulate the slot's forecasted W (from cached Solcast rates).
          4. On slot rollover, compute actual_mean / forecast_mean if both
             are above the daylight floor, append to the ring buffer
             (capped at 8 = 2 h), and recompute
             `_st_solar_factor = mean(ratio of last 4 closed slots)`.
        """
        slot_start = now.replace(
            minute=(now.minute // 15) * 15, second=0, microsecond=0,
        )

        # First call: initialise to current slot
        if self._st_solar_slot_start is None:
            self._st_solar_slot_start = slot_start
            self._st_solar_pv_sum_w = 0.0
            self._st_solar_pv_count = 0
            self._st_solar_forecast_sum_w = 0.0
            self._st_solar_forecast_count = 0

        # Slot rollover
        if slot_start > self._st_solar_slot_start:
            prev_start = self._st_solar_slot_start
            actual_mean_w = (
                self._st_solar_pv_sum_w / self._st_solar_pv_count
                if self._st_solar_pv_count > 0 else 0.0
            )
            forecast_mean_w = (
                self._st_solar_forecast_sum_w / self._st_solar_forecast_count
                if self._st_solar_forecast_count > 0 else 0.0
            )
            # v0.38.4 — Discard the slot if the export floor was active at
            # any tick during it. The actual PV reading was clipped by the
            # export-limit register, so the actual/forecast ratio is
            # artificially small. Letting it through corrupts
            # `_st_solar_factor` for up to 2 hours after the floor closes.
            if self._st_solar_floor_seen_during_slot:
                self._st_solar_last_curtailed_skip_iso = (
                    prev_start + timedelta(minutes=15)
                ).isoformat()
                _LOGGER.info(
                    "Short-term solar correction: skipping slot %s — solar "
                    "export floor was active (actual=%.0fW forecast=%.0fW). "
                    "Sample dropped to prevent ratio corruption.",
                    prev_start.strftime("%H:%M"),
                    actual_mean_w, forecast_mean_w,
                )
            # Only emit a residual when there's meaningful sun in BOTH
            # readings (avoids dawn/dusk noise and night divide-by-zero)
            # AND the slot wasn't curtailed.
            elif (
                actual_mean_w >= self._st_solar_min_w
                and forecast_mean_w >= self._st_solar_min_w
            ):
                ratio = actual_mean_w / forecast_mean_w
                ratio = max(0.1, min(3.0, ratio))   # clamp pathological values
                self._st_solar_residuals.append({
                    "slot_end": (prev_start + timedelta(minutes=15)).isoformat(),
                    "actual_w": round(actual_mean_w, 1),
                    "forecast_w": round(forecast_mean_w, 1),
                    "ratio": round(ratio, 3),
                })
                # Cap at last 8 slots (= 2 h history)
                if len(self._st_solar_residuals) > 8:
                    self._st_solar_residuals = self._st_solar_residuals[-8:]
                # Recompute rolling factor over the last 4 closed slots
                recent = [r["ratio"] for r in self._st_solar_residuals[-4:]]
                if recent:
                    self._st_solar_factor = max(0.3, min(2.0, sum(recent) / len(recent)))
                _LOGGER.debug(
                    "Short-term solar correction: slot %s actual=%.0fW "
                    "forecast=%.0fW ratio=%.3f → factor=%.3f (n=%d)",
                    prev_start.strftime("%H:%M"), actual_mean_w,
                    forecast_mean_w, ratio, self._st_solar_factor,
                    len(self._st_solar_residuals),
                )
            # Reset accumulators for the new slot
            self._st_solar_slot_start = slot_start
            self._st_solar_pv_sum_w = 0.0
            self._st_solar_pv_count = 0
            self._st_solar_forecast_sum_w = 0.0
            self._st_solar_forecast_count = 0
            self._st_solar_floor_seen_during_slot = False   # v0.38.4

        # v0.38.4 — Mark this slot as curtailed if the floor block is open
        # at this tick. Sticky for the whole slot — even a single curtailed
        # tick poisons the slot's actual/forecast ratio, so we play it safe.
        if self._current_floor_block is not None:
            self._st_solar_floor_seen_during_slot = True

        # Always accumulate the live readings for the current slot
        if pv_power_w is not None and pv_power_w >= 0:
            self._st_solar_pv_sum_w += float(pv_power_w)
            self._st_solar_pv_count += 1
        slot_forecast_w = _current_slot_forecast(solar_rates or [], now)
        if slot_forecast_w is not None and slot_forecast_w >= 0:
            self._st_solar_forecast_sum_w += float(slot_forecast_w)
            self._st_solar_forecast_count += 1

    def get_short_term_solar_factor(self, hours_ahead: float = 0.0) -> float:
        """Return the short-term multiplier with linear decay toward 1.0
        over `_st_solar_decay_hours` (default 2 h).

        At hours_ahead = 0 → full short-term factor.
        At hours_ahead = decay window → 1.0 (no influence).
        """
        if not self._st_solar_residuals:
            return 1.0
        if hours_ahead <= 0:
            return self._st_solar_factor
        if hours_ahead >= self._st_solar_decay_hours:
            return 1.0
        # Linear decay
        weight = 1.0 - (hours_ahead / self._st_solar_decay_hours)
        return 1.0 + weight * (self._st_solar_factor - 1.0)

    def get_solar_accuracy_factor_for_hour(self, hour: int) -> float:
        """Per-hour accuracy correction. Falls back to the global factor if the
        hour bucket hasn't warmed up yet.

        Result is clamped to [0.3, 1.5] so a single bad sample can't push the
        optimizer into pathological behaviour.
        """
        by_hour: dict = self._stored.get("solar_accuracy_by_hour", {})
        bucket: list[dict] = by_hour.get(str(hour), [])
        ratios: list[float] = []
        for s in bucket:
            f = s.get("f", 0)
            a = s.get("a", 0)
            if f >= SOLAR_ACCURACY_COMPARISON_W:
                ratios.append(a / f)
        if len(ratios) >= SOLAR_ACCURACY_HOUR_MIN_SAMPLES:
            return round(max(0.3, min(1.5, statistics.median(ratios))), 3)
        return self.get_solar_accuracy_factor()

    def get_solar_hourly_accuracy_profile(self) -> list[float]:
        """Return 24 hourly accuracy factors. Hours without enough data fall
        back to the global factor. Used for diagnostics + the dashboard sensor."""
        return [self.get_solar_accuracy_factor_for_hour(h) for h in range(24)]

    def get_solar_confidence_factor_for_hour(self, hour: int) -> float:
        """Per-hour solar accuracy factor at the user's configured confidence
        percentile (`solar_confidence_pct`, v0.44.0), falling back to the
        plain per-hour median (`get_solar_accuracy_factor_for_hour`, itself
        falling back further to the global rolling factor) when that hour's
        percentile bucket hasn't warmed up yet. At the default confidence of
        50 this IS the median — numerically identical to calling
        `get_solar_accuracy_factor_for_hour` directly.

        v0.75.13 — the DP optimiser's own price plan (`_dp_solve`'s
        `_slot_factor`) has used this confidence-percentile mechanism since
        v0.44.0; the dynamic discharge floor (`_compute_dynamic_floor_soc`)
        was still on the plain median only. So lowering `solar_confidence_pct`
        to make the PROFIT side more conservative about optimistic solar had
        no effect on the SAFETY side at all — this gives the floor the same
        knob, sourced from the same underlying data.
        """
        confidence = float(self._stored.get(
            "solar_confidence_pct", DEFAULT_SOLAR_CONFIDENCE_PCT,
        ))
        pct = self.get_solar_hour_percentile(hour, confidence)
        return pct if pct is not None else self.get_solar_accuracy_factor_for_hour(hour)

    def get_solar_hourly_sample_counts(self) -> list[int]:
        """Return 24 sample counts (only samples where forecast ≥ comparison
        threshold, i.e. only daylight samples that contribute to the median).
        Useful as a warm-up progress indicator on the dashboard.
        """
        by_hour: dict = self._stored.get("solar_accuracy_by_hour", {})
        counts: list[int] = []
        for h in range(24):
            bucket = by_hour.get(str(h), [])
            counts.append(sum(
                1 for s in bucket
                if s.get("f", 0) >= SOLAR_ACCURACY_COMPARISON_W
            ))
        return counts

    # ── Solar forecast percentiles (v0.43.0 — S1 groundwork) ──────────────
    # The per-hour buckets already hold the raw (forecast, actual) pairs. The
    # existing factor collapses each bucket to a median; these expose the
    # spread (P10/P50/P90 of the actual/forecast ratio). NOT yet consumed by
    # the optimiser — observability only, so a later release can switch the DP
    # to a conservative percentile once the scorecard confirms the spread.
    def get_solar_hour_percentile(self, hour: int, p: float) -> float | None:
        """Percentile `p` (0–100) of the actual/forecast ratio for `hour`'s
        bucket, clamped to [0.3, 1.5] like the median factor. Returns None when
        the bucket hasn't reached the minimum sample count."""
        by_hour: dict = self._stored.get("solar_accuracy_by_hour", {})
        bucket: list[dict] = by_hour.get(str(hour), [])
        ratios: list[float] = []
        for s in bucket:
            f = s.get("f", 0)
            a = s.get("a", 0)
            if f >= SOLAR_ACCURACY_COMPARISON_W:
                ratios.append(a / f)
        if len(ratios) < SOLAR_ACCURACY_HOUR_MIN_SAMPLES:
            return None
        ratios.sort()
        # Linear-interpolation percentile (no numpy dependency).
        k = (len(ratios) - 1) * (max(0.0, min(100.0, p)) / 100.0)
        lo = int(k)
        hi = min(lo + 1, len(ratios) - 1)
        val = ratios[lo] + (ratios[hi] - ratios[lo]) * (k - lo)
        return round(max(0.3, min(1.5, val)), 3)

    def get_solar_hourly_percentile_profile(self, p: float) -> list[float | None]:
        """24-length list of the hour-bucket percentile `p`; None where cold."""
        return [self.get_solar_hour_percentile(h, p) for h in range(24)]

    # ── Prediction scorecard (v0.43.0 — M1) ───────────────────────────────
    def _update_prediction_scorecard(
        self, now: datetime, battery_soc: float,
    ) -> None:
        """On each 15-min slot rollover, record the optimiser plan's predicted
        SoC for the slot vs the realised SoC. Pure observability — never
        influences a decision. Lets accuracy be measured before any logic
        change is allowed to claim it improved precision."""
        # v0.46.1 — skip the post-restart warm-up window. The optimiser plan is
        # cold for the first few minutes after a restart and emits garbage
        # predicted SoC; logging it would inflate the MAE for the next 7 days.
        try:
            if (now - self._started_at).total_seconds() < PREDICTION_WARMUP_SECONDS:
                return
        except Exception:  # noqa: BLE001
            pass
        try:
            local = now.astimezone()
            slot_start = local.replace(
                minute=(local.minute // 15) * 15, second=0, microsecond=0,
            )
        except Exception:  # noqa: BLE001
            return
        # Same slot we already recorded → nothing to do.
        if self._sc_slot_start is not None and slot_start <= self._sc_slot_start:
            return
        # Skip implausible SoC reads (0 / unavailable). Common in the first
        # ticks after a restart before FoxESS live state populates — and the
        # battery never legitimately sits at 0 % (floor is well above it).
        # Recording one would poison the MAE. Don't advance the tracked slot,
        # so a valid read later in the same slot still gets recorded.
        if battery_soc is None or battery_soc <= 0:
            return
        self._sc_slot_start = slot_start
        # Find the plan's prediction for this slot (hour + 15-min bucket).
        h = slot_start.hour
        mb = (slot_start.minute // 15) * 15
        pred_soc = None
        pred_action = None
        for s in self._optimizer_plan:
            if s.get("hour") == h and ((s.get("minute", 0) // 15) * 15) == mb:
                pred_soc = s.get("soc")
                pred_action = s.get("action")
                break
        if pred_soc is None:
            return  # plan doesn't cover this slot (cold start / no day-ahead)
        log: list[dict] = self._stored.setdefault("prediction_log", [])
        log.append({
            "slot": slot_start.isoformat(),
            "hour": h,
            "pred_soc": int(round(float(pred_soc))),
            "act_soc": round(float(battery_soc), 1),
            "pred_action": pred_action,
        })
        if len(log) > PREDICTION_LOG_MAX:
            del log[: len(log) - PREDICTION_LOG_MAX]

    def get_prediction_accuracy_summary(self) -> dict:
        """Rolling prediction-accuracy metrics for the scorecard sensor.

        - SoC MAE (mean absolute error, % points) over 7 d / 30 d windows.
        - Solar forecast MAPE (%) from the per-hour buckets.
        - Action mix the plan asked for over the recent window.
        Count-based windows (96 slots/day) avoid timezone-string comparisons.
        """
        log: list[dict] = self._stored.get("prediction_log", [])

        def _soc_mae(n_slots: int) -> float:
            # Ignore any implausible-SoC samples (act_soc <= 0) that may have
            # been logged before the act_soc>0 guard existed, so a single
            # post-restart glitch can't pin the MAE.
            recent = [
                e for e in log[-n_slots:]
                if "pred_soc" in e and e.get("act_soc", 0) > 0
            ]
            if not recent:
                return 0.0
            errs = [abs(e["pred_soc"] - e["act_soc"]) for e in recent]
            return round(sum(errs) / len(errs), 2)

        # Solar MAPE from the per-hour (forecast, actual) buckets.
        by_hour: dict = self._stored.get("solar_accuracy_by_hour", {})
        sol_errs: list[float] = []
        for bucket in by_hour.values():
            for s in bucket:
                f = s.get("f", 0)
                a = s.get("a", 0)
                if f >= SOLAR_ACCURACY_COMPARISON_W:
                    sol_errs.append(abs(a - f) / f)
        solar_mape = round(100.0 * sum(sol_errs) / len(sol_errs), 1) if sol_errs else 0.0

        # Predicted-action mix over the 7-day window.
        recent = log[-PREDICTION_MAE_WINDOW_SLOTS:]
        action_mix = {"CHARGE": 0, "EXPORT": 0, "IDLE": 0}
        for e in recent:
            a = e.get("pred_action")
            if a in action_mix:
                action_mix[a] += 1

        return {
            "prediction_soc_mae_7d": _soc_mae(PREDICTION_MAE_WINDOW_SLOTS),
            "prediction_soc_mae_30d": _soc_mae(PREDICTION_MAE_WINDOW_SLOTS_LONG),
            "prediction_solar_mape": solar_mape,
            "prediction_samples": len(log),
            "prediction_action_mix": action_mix,
            "prediction_log": log[-96:],  # last 24 h for charting
        }

    # ── Tier-1 model-health monitor (v0.64.0) ─────────────────────────────
    def _check_model_health(self) -> tuple[list[str], list[str]]:
        """Detect a learned model that has drifted, pinned at a safety clamp, or
        whose predictions are persistently wrong, and return
        (issues, notes) as human-readable strings. Detection + surfacing
        ONLY — it never changes a model itself (that boundary is what keeps
        the self-correction stable). Would have caught both bugs hit in this
        development cycle: the capacity learner drifting to ~16.9 vs the real
        12.1, and the reserve margin pinning at its cap. Cheap enough to call
        on the 5-min learning tick.

        v0.75.13 — `issues` (drives the "Problem" binary_sensor and the
        attention-needed notification) is now reserved for conditions that
        actually need a look. `notes` is for genuinely different conditions
        that are only worth surfacing, not alarming on — reserve factor
        pinned at its MINIMUM is the first of these: pinning at MAXIMUM means
        the learned overnight need exceeds the safety cap, a real thing to
        check; pinning at MINIMUM plausibly just means this house is unusually
        predictable and barely any margin is needed, or at most that the
        clamp itself (not a data problem) is now the binding constraint.
        Treating both edges identically as "Problem" was misleading — this
        was flagging live on a real system the night this was written.
        """
        issues: list[str] = []
        notes: list[str] = []
        # 1. Battery-capacity learner drift vs the authoritative (GUI/config) value.
        configured = float(self._stored.get(
            "battery_capacity", self.config.get("battery_capacity", DEFAULT_BATTERY_CAPACITY)))
        learned = self.get_learned_capacity()
        if learned is not None and configured > 0:
            drift = abs(learned - configured) / configured
            if drift > MODEL_HEALTH_CAPACITY_DRIFT_FRAC:
                issues.append(
                    f"Capacity learner drift: BMS-learned {learned:.1f} kWh vs set "
                    f"{configured:.1f} kWh ({drift * 100:.0f}%)")
        # 2. Reserve factor pinned at a safety clamp (only meaningful once warm).
        if len(self._stored.get("overnight_ratio_samples", [])) >= OVERNIGHT_MIN_NIGHTS:
            rf = self._reserve_factor()
            if rf >= RESERVE_FACTOR_MAX - 1e-6:
                issues.append(
                    f"Reserve factor pinned at max ({RESERVE_FACTOR_MAX}): overnight need "
                    f"exceeds the cap — consider raising it")
            elif rf <= RESERVE_FACTOR_MIN + 1e-6:
                notes.append(
                    f"Reserve factor pinned at min ({RESERVE_FACTOR_MIN}) — this house's "
                    f"overnight need is consistently low relative to the deterministic "
                    f"prediction; not necessarily a problem")
        # 3. Auto round-trip efficiency at a clamp edge (implausible learned value).
        eff = self.get_auto_efficiency()
        if eff is not None and (eff <= MODEL_HEALTH_EFFICIENCY_LO or eff >= MODEL_HEALTH_EFFICIENCY_HI):
            issues.append(f"Round-trip efficiency at clamp edge ({eff:.3f})")
        # 4. Solar accuracy factor persistently extreme (forecast badly biased).
        saf = self.get_solar_accuracy_factor()
        if saf <= MODEL_HEALTH_SOLAR_LO:
            issues.append(f"Solar forecast persistently optimistic (factor {saf:.2f})")
        elif saf >= MODEL_HEALTH_SOLAR_HI:
            issues.append(f"Solar forecast persistently pessimistic (factor {saf:.2f})")
        # 5. Prediction accuracy degraded (7-day predicted-vs-actual SoC error).
        try:
            mae = float(self.get_prediction_accuracy_summary().get("prediction_soc_mae_7d", 0.0))
            if mae > MODEL_HEALTH_SOC_MAE_PCT:
                issues.append(f"Prediction accuracy degraded: 7-day SoC error {mae:.0f}%")
        except Exception:  # noqa: BLE001 — observability must never break the loop
            pass
        return issues, notes

    # ------------------------------------------------------------------ #
    # Action log (export / grid-charge session tracking)                  #
    # ------------------------------------------------------------------ #

    async def _open_action_session(
        self, now: datetime, action_type: str, soc: float, price: float
    ) -> None:
        """Open a new export or grid-charge session in the action log."""
        local_now = now.astimezone(_CPH_TZ)
        self._open_action = {
            "type": action_type,   # "export" | "charge"
            "start_ts": local_now.strftime("%Y-%m-%dT%H:%M"),
            "soc_start": round(soc, 1),
            "price": round(price, 4),
        }
        _LOGGER.info(
            "Action log: opening %s session at %s (SoC %.1f%%, price %.4f DKK/kWh)",
            action_type, local_now.strftime("%H:%M"), soc, price,
        )
        # Mobile push notification — export start
        if action_type == "export" and self._stored.get("notify_export_start", False):
            await self._send_mobile_notification(
                self._msg("☀️ Solar AI: Export started", "☀️ Solar AI: Eksport startet"),
                self._msg(
                    f"Battery exporting to grid · SoC {soc:.0f}% · {price:.2f} DKK/kWh",
                    f"Batteri eksporterer til nettet · SoC {soc:.0f}% · {price:.2f} DKK/kWh",
                ),
            )
        # Mobile push notification — charge start
        elif action_type == "charge" and self._stored.get("notify_charge_start", False):
            await self._send_mobile_notification(
                self._msg("⚡ Solar AI: Charging started", "⚡ Solar AI: Opladning startet"),
                self._msg(
                    f"Battery charging from grid · SoC {soc:.0f}% · {price:.2f} DKK/kWh",
                    f"Batteri oplades fra nettet · SoC {soc:.0f}% · {price:.2f} DKK/kWh",
                ),
            )

    async def _close_action_session(
        self, now: datetime, soc_end: float, capacity_kwh: float
    ) -> None:
        """Close the current open session and append the completed entry to action_log."""
        if self._open_action is None:
            return
        local_now = now.astimezone(_CPH_TZ)
        start_ts: str = self._open_action["start_ts"]
        soc_start: float = self._open_action["soc_start"]
        price: float = self._open_action["price"]
        action_type: str = self._open_action["type"]

        # Duration in minutes
        try:
            start_dt = datetime.fromisoformat(start_ts).replace(tzinfo=_CPH_TZ)
            duration_min = int((local_now - start_dt).total_seconds() / 60)
        except Exception:
            duration_min = 0

        # kWh ≈ |ΔSoC| / 100 × capacity
        soc_delta = abs(soc_end - soc_start)
        kwh = round(soc_delta / 100.0 * capacity_kwh, 2)
        dkk = round(kwh * price, 2)

        entry: dict = {
            "type": action_type,
            "start_ts": start_ts,
            "end_ts": local_now.strftime("%Y-%m-%dT%H:%M"),
            "soc_start": soc_start,
            "soc_end": round(soc_end, 1),
            "duration_min": duration_min,
            "price": price,
            "kwh": kwh,
            "dkk": dkk,
        }
        log: list[dict] = self._stored.setdefault("action_log", [])
        log.append(entry)
        if len(log) > 500:
            del log[: len(log) - 500]
        self._open_action = None
        _LOGGER.info(
            "Action log: closed %s session — SoC %.1f%%→%.1f%%, %d min, %.2f kWh, %.2f DKK",
            action_type, soc_start, soc_end, duration_min, kwh, dkk,
        )
        # Mobile push notification — export stop
        if action_type == "export" and self._stored.get("notify_export_stop", False):
            await self._send_mobile_notification(
                self._msg("☀️ Solar AI: Export finished", "☀️ Solar AI: Eksport afsluttet"),
                f"SoC {soc_start:.0f}%→{soc_end:.0f}% · {duration_min} min · {kwh} kWh · {dkk} DKK",
            )
        # Mobile push notification — charge stop
        elif action_type == "charge" and self._stored.get("notify_charge_stop", False):
            await self._send_mobile_notification(
                self._msg("⚡ Solar AI: Charging finished", "⚡ Solar AI: Opladning afsluttet"),
                f"SoC {soc_start:.0f}%→{soc_end:.0f}% · {duration_min} min · {kwh} kWh · {dkk} DKK",
            )

    async def _async_disk_usage(self) -> dict[str, Any]:
        """Free/used space on the partition Home Assistant runs on.

        Uses the config directory as the probe path — that is where the
        recorder DB and .storage live, i.e. the disk that actually fills up
        on a Pi/SD-card install. shutil.disk_usage is a blocking stat, so it
        runs in the executor. Returns {} on error.
        """
        path = self.hass.config.config_dir

        def _usage() -> dict[str, Any]:
            try:
                total, used, free = shutil.disk_usage(path)
            except OSError:
                return {}
            return {
                "total_gb": round(total / 1_000_000_000, 1),
                "used_gb": round(used / 1_000_000_000, 1),
                "free_gb": round(free / 1_000_000_000, 2),
                "pct_free": round(100 * free / total, 1) if total else 0.0,
                "path": path,
            }

        try:
            return await self.hass.async_add_executor_job(_usage)
        except Exception:  # noqa: BLE001
            return {}

    async def _check_disk_alarm(self) -> None:
        """Latch the low-disk alarm and fire one push when it first trips.

        Edge-triggered with a recovery hysteresis so a reading that hovers at
        the threshold doesn't spam notifications. The alarm state itself
        (self._disk_low) drives the binary_sensor regardless of push config.
        """
        du = self._disk_usage
        pct = du.get("pct_free")
        if pct is None:
            return
        threshold = float(self._stored.get(
            "disk_alarm_threshold_pct", DEFAULT_DISK_ALARM_THRESHOLD_PCT))

        if not self._disk_low and pct < threshold:
            self._disk_low = True
            _LOGGER.warning(
                "Low disk space: %.1f%% (%s GB) free on %s — below %.0f%% threshold",
                pct, du.get("free_gb"), du.get("path"), threshold,
            )
            if (self._stored.get("notifications_enabled", False)
                    and self._stored.get("notify_disk_low", True)):
                await self._send_mobile_notification(
                    self._msg("⚠️ Solar AI: Low disk space",
                              "⚠️ Solar AI: Lav diskplads"),
                    self._msg(
                        f"Only {du.get('free_gb')} GB ({pct:.0f}%) free on "
                        f"{du.get('path')} — below the {threshold:.0f}% alarm threshold",
                        f"Kun {du.get('free_gb')} GB ({pct:.0f}%) ledig på "
                        f"{du.get('path')} — under {threshold:.0f}%-alarmgrænsen",
                    ),
                )
        elif self._disk_low and pct >= threshold + DISK_ALARM_RECOVERY_HYSTERESIS_PCT:
            self._disk_low = False
            _LOGGER.info("Disk space recovered: %.1f%% free on %s", pct, du.get("path"))

    async def _send_mobile_notification(self, title: str, message: str) -> None:
        """Send a push notification to all user-selected HA Companion mobile apps.

        Targets are stored as full service strings, e.g. "notify.mobile_app_my_phone".
        If no targets are configured the notification is silently skipped.
        """
        targets: list[str] = self._stored.get("notify_targets", [])
        if not targets:
            _LOGGER.debug("Mobile notification skipped — no targets configured")
            return
        for target in targets:
            parts = target.split(".", 1)
            domain, service = (parts[0], parts[1]) if len(parts) == 2 else ("notify", target)
            try:
                await self.hass.services.async_call(
                    domain, service,
                    {"title": title, "message": message},
                    blocking=False,
                )
            except Exception as err:
                _LOGGER.warning("Push notification to %s.%s failed: %s", domain, service, err)

    def get_action_log(self, n: int = 20) -> list[dict]:
        """Return last n action log entries, newest first."""
        log: list[dict] = self._stored.get("action_log", [])
        return list(reversed(log[-n:]))

    # ── Solar export floor log (block / resume events) ────────────────────
    # Mirrors the action-log pattern: a session is opened when the live sell
    # price drops below the floor and solar export gets capped at 25 W; closed
    # when the price rises back above the floor and full export resumes.

    def _open_floor_block(
        self, now: datetime, price: float, floor: float,
    ) -> None:
        local_now = now.astimezone(_CPH_TZ)
        # v0.36.0: writes to `_current_floor_block` (was `_open_floor_block`
        # — name clashed with this method).
        self._current_floor_block = {
            "start_ts": local_now.strftime("%Y-%m-%dT%H:%M"),
            "price_at_start": round(price, 4),
            "floor": round(floor, 4),
        }
        _LOGGER.info(
            "Solar floor log: opening block at %s (price %.4f ≤ floor %.2f DKK/kWh)",
            local_now.strftime("%H:%M"), price, floor,
        )

    def _close_floor_block(self, now: datetime, price: float) -> None:
        if self._current_floor_block is None:
            return
        local_now = now.astimezone(_CPH_TZ)
        start_ts: str = self._current_floor_block["start_ts"]
        try:
            start_dt = datetime.fromisoformat(start_ts).replace(tzinfo=_CPH_TZ)
            duration_min = int((local_now - start_dt).total_seconds() / 60)
        except Exception:
            duration_min = 0

        entry: dict = {
            "start_ts": start_ts,
            "end_ts": local_now.strftime("%Y-%m-%dT%H:%M"),
            "duration_min": duration_min,
            "price_at_start": self._current_floor_block.get("price_at_start", 0.0),
            "price_at_end":   round(price, 4),
            "floor":          self._current_floor_block.get("floor", 0.0),
        }
        log: list[dict] = self._stored.setdefault("solar_floor_log", [])
        log.append(entry)
        if len(log) > 500:
            del log[: len(log) - 500]
        self._current_floor_block = None
        _LOGGER.info(
            "Solar floor log: closed block — %d min "
            "(price %.3f → %.3f, floor %.2f)",
            duration_min, entry["price_at_start"], entry["price_at_end"], entry["floor"],
        )

    def get_solar_floor_log(self, n: int = 20) -> list[dict]:
        """Return last n solar-floor block entries, newest first."""
        log: list[dict] = self._stored.get("solar_floor_log", [])
        return list(reversed(log[-n:]))

    # ------------------------------------------------------------------ #
    # EV charge controller (Phase B1 — OCPP-driven dynamic surplus tracker) #
    # ------------------------------------------------------------------ #

    async def _run_ev_controller(
        self,
        evcc_state: dict,
        battery_soc: float,
        floor_soc: float,
    ) -> dict:
        """Run the 4-mode EV charge controller for one tick.

        Reads live solar / load / battery state, computes the target charge
        rate from the active mode, applies hysteresis + rate-of-change limits,
        and writes via the OCPP integration's service call. Returns a dict of
        telemetry keys merged into the coordinator result for the visibility
        sensors to consume.
        """
        # Master gate — feature is opt-in. Existing installs default OFF.
        if not self.config.get(CONF_EV_CONTROLLER_ENABLED, DEFAULT_EV_CONTROLLER_ENABLED):
            return {"ev_enabled": False, "ev_reason": "EV controller disabled"}

        # Backend dispatch (v0.57.0). The FoxESS Modbus backend has its own
        # simpler control path (single-phase solar following); the OCPP path
        # below is unchanged.
        from .const import (  # noqa: PLC0415
            CONF_EV_CHARGER_BACKEND, DEFAULT_EV_CHARGER_BACKEND, EV_BACKEND_FOXESS_MODBUS,
        )
        # Read via _setting so the dashboard select (Advanced pane) overrides
        # the config-entry value and applies on the next cycle without a reload.
        if (self._setting(CONF_EV_CHARGER_BACKEND, DEFAULT_EV_CHARGER_BACKEND)
                == EV_BACKEND_FOXESS_MODBUS):
            return await self._run_ev_controller_modbus(
                evcc_state, battery_soc, floor_soc,
            )

        charger_id = self.config.get(CONF_EV_OCPP_CHARGE_POINT_ID, "")
        if not charger_id:
            return {"ev_enabled": False, "ev_reason": "No OCPP charge point ID configured"}

        # Detect plug-in event and reset active mode to user's default
        ocpp_status = self._get_ocpp_status(charger_id)
        ev_connected = ocpp_status in (
            "Preparing", "Charging", "SuspendedEV", "SuspendedEVSE", "Finishing",
        )
        if ev_connected and not self._ev_prev_connected:
            # Default mode: prefer live override stored via the dashboard
            # select entity (v0.27.0), fall back to config-entry value.
            default_mode = self._stored.get(
                "ev_default_mode",
                self.config.get(CONF_EV_DEFAULT_MODE, DEFAULT_EV_DEFAULT_MODE),
            )
            self._ev_active_mode = default_mode
            self._stored["ev_active_mode"] = default_mode
            self._ev_above_start_count = 0
            self._ev_below_stop_count = 0
            self._ev_surplus_above_min_since_ts = None
            self._ev_surplus_below_min_since_ts = None
            self._ev_arm_drop_since_ts = None              # v0.38.5
            self._ev_cool_entry_ts = None                  # v0.39.11
            _LOGGER.info("EV plugged in (%s) — resetting mode to %s", charger_id, default_mode)
        self._ev_prev_connected = ev_connected

        if not ev_connected:
            self._ev_last_amps = 0
            self._ev_last_reason = f"EV not connected (status: {ocpp_status})"
            # v0.38.1 — clear any pending probe/override cool-down on
            # disconnect so the next car plug-in is a fresh start.
            # v0.39.17 — `_ev_probe_started_at` removed; cool-down field
            # remains for the battery-full override.
            # v0.39.18 — also clear the session-override marker.
            if self._ev_probe_cooldown_until is not None:
                self._ev_probe_cooldown_until = None
            self._ev_session_was_override_induced = False
            self._reset_override_ramp()  # v0.39.21
            return self._ev_telemetry(0.0, 0, 0.0, ocpp_status)

        # ── Compute target ────────────────────────────────────────────────
        home_power_w = evcc_state.get("homePower", 0) or 0
        pv_power_w   = evcc_state.get("pvPower", 0) or 0
        # v0.39.19 — gridPower: positive = import, negative = export.
        # Used below to decide whether to bypass the battery-priority
        # gate when the grid is actively absorbing surplus PV.
        grid_power_w = evcc_state.get("gridPower", 0) or 0
        grid_export_kw = max(0.0, -grid_power_w / 1000.0)
        ev_current_kw = self._get_ocpp_power_kw(charger_id)
        house_load_kw = home_power_w / 1000.0
        solar_kw      = pv_power_w / 1000.0

        # v0.39.17 — Battery-full override replaces the v0.36.2 → v0.39.15
        # curtailment probe.
        #
        # The probe depended on the FoxESS PV-limited flag (reg 49251)
        # reading True when MPPT throttles. Live observation on 2026-05-27:
        # battery at 100 %, export-stop active, PV throttled from a forecast
        # 5 kW down to 0.36 kW actual — and reg 49251 still reading False.
        # The probe never fires in this scenario, which is the exact case
        # users want it to handle. Reg 49251 is unreliable for battery-full
        # curtailment on this inverter; the probe strategy was building on
        # a signal that doesn't fire when it needs to.
        #
        # New strategy: when the user-controllable conditions for
        # "definitely want EV to absorb otherwise-wasted PV" all hold,
        # just command the EV to draw min. No state machine, no synthesis,
        # no reg 49251. The inverter responds to a new sink on the AC bus
        # by lifting MPPT — that's the inverter's job, not Solar AI's to
        # anticipate.
        #
        # Conditions (ALL required):
        #   1. effective_mode in (EV_MODE_PV, EV_MODE_PV_BATTERY) (checked at
        #      override apply site below, after _resolve_effective_ev_mode;
        #      v0.75.14 — PV_BATTERY added, see that site's comment)
        #   2. battery_soc >= max_soc - 2 (battery has no headroom)
        #   3. floor_active (price-floor block open — export is blocked)
        #   4. solar_kw > 0.1 (PV is actually producing something — even if
        #      curtailed; prevents trying at night or in deep cloud cover)
        #   5. cool-down not active (last attempt didn't fail recently)
        #
        # What stops the EV after a successful override start:
        #   - Real surplus tracking takes over once MPPT lifts (normal
        #     v0.26.0 surplus-based target). Override stays "active"; the
        #     target follows actual surplus.
        #   - If MPPT doesn't lift, the EV draws min (4.14 kW) from grid.
        #     stop_window (180 s default) catches it within ~3 minutes,
        #     then EV_CURTAILMENT_PROBE_COOLDOWN_SECONDS (15 min) blocks
        #     retries. Worst-case grid import per failed cycle ≈ 0.21 kWh.
        #
        # Cool-down reuses the existing `_ev_probe_cooldown_until` field
        # for backwards compatibility with state stored across restarts;
        # the field is still about preventing retry storms after failed
        # MPPT-lift attempts, just triggered by stop_window confirmation
        # instead of the v0.36.2 60-second window.
        now_ts = datetime.now(timezone.utc)
        floor_active = self._current_floor_block is not None
        max_soc = int(self._stored.get(
            "battery_max_soc",
            self.config.get("battery_max_soc", DEFAULT_BATTERY_MAX_SOC),
        ))
        battery_near_full = battery_soc >= (max_soc - 2)
        override_cooldown_active = (
            self._ev_probe_cooldown_until is not None
            and now_ts < self._ev_probe_cooldown_until
        )
        # Compute the override condition (mode check happens at apply
        # site below where effective_mode is in scope).
        override_preconditions_ok = (
            floor_active
            and battery_near_full
            and solar_kw > 0.1
            and not override_cooldown_active
        )

        # Surplus = solar minus non-EV portion of house load
        non_ev_load_kw   = max(0.0, house_load_kw - ev_current_kw)
        solar_surplus_kw = max(0.0, solar_kw - non_ev_load_kw)

        # NET surplus available to the EV (v0.27.5): the physical solar
        # surplus minus what the house battery is currently absorbing.
        # When the battery is below the priority threshold it's actively
        # taking everything left over, so the EV-available surplus is 0
        # even though there's a positive physical surplus.
        # Charge and discharge are reported on separate sensors (each ≥ 0): the
        # charge sensor reads 0 while the battery is discharging, and vice versa.
        from .const import (  # noqa: PLC0415
            CONF_BATTERY_CHARGE_ENTITY, FOXESS_BATTERY_CHARGE_POWER,
            CONF_BATTERY_DISCHARGE_ENTITY, FOXESS_BATTERY_DISCHARGE_POWER,
        )
        battery_charge_kw = max(0.0, float(self._get_float_state(
            self.config.get(CONF_BATTERY_CHARGE_ENTITY, FOXESS_BATTERY_CHARGE_POWER),
            0.0,
        ) or 0.0))
        # Charge and discharge are reported on separate sensors (the charge
        # sensor sits at 0 while the battery discharges), so read discharge from
        # its own sensor — not as the negative of charge.
        battery_discharge_kw = max(0.0, float(self._get_float_state(
            self.config.get(CONF_BATTERY_DISCHARGE_ENTITY, FOXESS_BATTERY_DISCHARGE_POWER),
            0.0,
        ) or 0.0))
        net_surplus_for_ev_kw = max(0.0, solar_surplus_kw - battery_charge_kw)

        min_kw = float(self._stored.get("ev_min_charge_kw", DEFAULT_EV_MIN_CHARGE_KW))
        max_kw = float(self._stored.get("ev_max_charge_kw", DEFAULT_EV_MAX_CHARGE_KW))
        # Battery-priority threshold (v0.26.4): EV waits while battery_soc <
        # priority_soc in PV / PV+battery modes. Live slider, defaults 80 %.
        priority_soc = float(self._stored.get(
            "ev_battery_priority_soc",
            self.config.get(CONF_EV_BATTERY_PRIORITY_SOC, DEFAULT_EV_BATTERY_PRIORITY_SOC),
        ))

        # v0.36.0 — resolve SCHEDULED → concrete mode for this tick. For
        # non-scheduled modes this is a no-op (effective == active).
        effective_mode, active_link = self._resolve_effective_ev_mode(self._ev_active_mode)
        self._ev_effective_mode = effective_mode
        self._ev_active_schedule_link = active_link

        target_kw, reason = self._compute_ev_target_kw(
            effective_mode, solar_surplus_kw, battery_soc, floor_soc,
            min_kw, max_kw, priority_soc,
            grid_export_kw=grid_export_kw,
            ev_last_amps=self._ev_last_amps,
            mode_just_changed=self._ev_mode_change_pending,
        )

        # v0.39.17 — Battery-full override.
        # v0.39.18 — Two behavioural refinements:
        #   1. Floor, not cap. The override only forces target up to
        #      `min_kw` if `_compute_ev_target_kw` returned a value
        #      BELOW min. When real surplus is already ≥ min, normal
        #      surplus tracking returns the right (higher) target —
        #      no need to clamp it down to min.
        #   2. Session marker. Whenever the override is forcing this
        #      tick, mark `_ev_session_was_override_induced = True`.
        #      The marker is cleared when EV goes IDLE between sessions
        #      (handled here) and on disconnect. Used below to decide
        #      whether the session that just ended deserves a soft
        #      cool-down (10 min) — preventing rapid on/off cycling
        #      during partly-cloudy periods.
        if self._ev_last_amps == 0:
            # Fresh session about to begin (or no session in progress).
            # Reset the marker so we only flag actually-override-induced
            # sessions for the soft cool-down.
            self._ev_session_was_override_induced = False
        # v0.75.14 — extended to PV_BATTERY alongside plain PV. PV_BATTERY's own
        # gap-filling logic will happily drain the house battery to cover the
        # EV once surplus reads low — exactly the MPPT-throttled reading this
        # override exists to see through. The `battery_covering_ev` check right
        # below already yields the override the moment real discharge appears,
        # regardless of which mode triggered it, so PV_BATTERY gets the same
        # backoff plain PV always had.
        battery_full_override = (
            override_preconditions_ok
            and effective_mode in (EV_MODE_PV, EV_MODE_PV_BATTERY)
        )
        # v0.39.21 — Active ramp. In the override regime (battery full +
        # export blocked) MPPT self-throttles to match whatever the AC bus
        # draws, so the measured surplus never exceeds the EV's own draw —
        # surplus tracking alone stays pinned at min and never finds spare
        # PV. The ramp actively commands progressively more current and
        # watches the grid meter: while grid import stays low MPPT is
        # keeping up, so keep climbing; when it can't, back off. The ramp
        # value is the floor; if surplus tracking ever returns higher
        # (genuine surplus), the higher value wins and the override yields.
        # v0.54.0 — if the house battery is discharging to cover the EV, there
        # is no curtailed PV for the override to harvest (a full battery would
        # be absorbing, not discharging). The override's premise is false, so
        # don't fire it — otherwise it silently drains the battery into the car,
        # which grid-import feedback can't detect (grid stays ~0; the battery,
        # not the grid, covers the draw). Yield so PV-mode's stop takes over.
        battery_covering_ev = (
            battery_discharge_kw > EV_OVERRIDE_RAMP_BATTERY_DISCHARGE_THRESHOLD_KW
        )
        if battery_full_override and battery_covering_ev:
            battery_full_override = False
            self._reset_override_ramp()
        if battery_full_override:
            grid_import_kw = max(0.0, grid_power_w / 1000.0)
            min_amps = self._kw_to_amps(min_kw)
            max_amps = self._kw_to_amps(max_kw)
            ramp_amps = self._update_override_ramp(
                now_ts, grid_import_kw, battery_discharge_kw, min_amps, max_amps,
            )
            ramp_kw = self._amps_to_kw(ramp_amps)
            override_forcing = target_kw <= ramp_kw
            if override_forcing:
                target_kw = ramp_kw
                reason = self._msg(
                    f"Override ramp: battery full ({battery_soc:.0f}% / max {max_soc}%) "
                    f"+ export-stop active — EV draws {ramp_amps} A "
                    f"({ramp_kw:.2f} kW), grid import {grid_import_kw:.2f} kW "
                    f"(raw PV: {solar_kw:.2f} kW, house load: {house_load_kw:.2f} kW)",
                    f"Override ramp: batteri fuld ({battery_soc:.0f}% / max {max_soc}%) "
                    f"+ eksport-stop aktiv — EV trækker {ramp_amps} A "
                    f"({ramp_kw:.2f} kW), net-import {grid_import_kw:.2f} kW "
                    f"(rå PV: {solar_kw:.2f} kW, husforbrug: {house_load_kw:.2f} kW)",
                )
                self._ev_session_was_override_induced = True
        else:
            override_forcing = False
            self._reset_override_ramp()

        target_amps = self._kw_to_amps(target_kw)

        # ── Anti-flap window (time-based, v0.26.0) ────────────────────────
        # v0.39.12 — pass `probing=True` to bypass start_window from IDLE
        # when a confidence signal (battery-full override) is active.
        # Without the bypass the EV would have to wait the full
        # start_window (60 s default) before charging, losing curtailed
        # PV during that window.
        final_amps = self._apply_ev_time_window(
            target_amps, probing=override_forcing,
        )

        # v0.39.18 — soft cool-down on override-induced session end.
        # Whenever an override-induced session ends (ev_last_amps > 0
        # → final_amps == 0 AND the session marker is set), arm a
        # 10-min cool-down before the override is allowed to fire
        # again. This catches both cases the v0.39.17 narrow detection
        # missed:
        #   • Override stopped forcing because conditions changed (e.g.,
        #     battery dropped below 98 %), then the natural stop_window
        #     eventually confirmed a stop.
        #   • Override was still forcing when the stop_window confirmed
        #     (the original v0.39.17 case).
        # Either way, attempting to restart immediately would just cause
        # thrashing.
        if (self._ev_session_was_override_induced
                and self._ev_last_amps > 0
                and final_amps == 0):
            self._ev_probe_cooldown_until = now_ts + timedelta(
                seconds=EV_OVERRIDE_SOFT_COOLDOWN_SECONDS,
            )
            self._ev_session_was_override_induced = False
            _LOGGER.info(
                "EV controller: override-induced session ended — "
                "soft cool-down %d s engaged to prevent rapid restart.",
                EV_OVERRIDE_SOFT_COOLDOWN_SECONDS,
            )

        # ── Rate-of-change limit (smooth ramp) ────────────────────────────
        if final_amps > 0 and self._ev_last_amps > 0:
            step = EV_MAX_AMP_STEP_PER_TICK
            if final_amps > self._ev_last_amps + step:
                final_amps = self._ev_last_amps + step
            elif final_amps < self._ev_last_amps - step:
                final_amps = self._ev_last_amps - step

        # ── Send OCPP write only when the change is meaningful ────────────
        send = False
        if final_amps == 0 and self._ev_last_amps > 0:
            send = True  # stopping
        elif final_amps > 0 and self._ev_last_amps == 0:
            send = True  # starting
        elif abs(final_amps - self._ev_last_amps) >= EV_MIN_AMP_CHANGE:
            send = True  # significant change

        # v0.40.2 — periodic re-assert. A charger can silently drop its
        # charging profile (reconnect, reboot, new transaction) and revert
        # to its built-in default (full current) while our cached state still
        # reads "already at N A", so nothing re-sends and the EV free-runs
        # at max — pulling from the house battery in PV/PV+battery modes.
        # Re-send the active limit at least every EV_RATE_REASSERT_SECONDS
        # while charging, forcing past both dedupe layers, so a reset charger
        # is pulled back to the commanded rate within ~1 minute.
        reassert = (
            final_amps > 0
            and not send
            and (
                self._ev_last_rate_assert_ts is None
                or (now_ts - self._ev_last_rate_assert_ts).total_seconds()
                >= EV_RATE_REASSERT_SECONDS
            )
        )

        if send or reassert:
            await self._set_ocpp_charge_rate(charger_id, final_amps, force=reassert)
            self._ev_last_amps = final_amps
            self._ev_last_rate_assert_ts = now_ts

        # v0.39.21 — when the EV is idle (no session), the override ramp has
        # nothing to track; reset it so the next override session starts at
        # min and re-probes from scratch.
        if final_amps == 0:
            self._reset_override_ramp()

        # ── Initiate / terminate OCPP transaction (v0.27.1) ────────────────
        # SetChargingProfile sets the LIMIT but doesn't start a session.
        # When the charger sits in Preparing/SuspendedEV/SuspendedEVSE
        # (cable plugged, no transaction), the CSMS must send
        # RemoteStartTransaction to begin energy delivery. Likewise, when we
        # want to stop and a session is active, we send RemoteStopTransaction.
        # State-based (not transition-based) so reloads / mid-cycle deploys
        # don't get stuck. The OCPP server's own 30-s cooldown prevents
        # spamming RemoteStartTransaction while the charger thinks about it.
        # ── Per-session grid/solar energy split (v0.28.4) ─────────────────
        # Integrate per-tick: how much of the EV's current draw came from
        # locally-available solar surplus vs the grid. Stored on the
        # ChargePoint and emitted as part of last_session_summary on stop.
        use_embedded = self.config.get(CONF_OCPP_EMBEDDED, True)
        if use_embedded and self.ocpp_server is not None:
            cp_split = self.ocpp_server.get(charger_id)
            if cp_split is not None:
                if cp_split.session_active and ev_current_kw > 0:
                    now_split = datetime.now(timezone.utc)
                    last_ts = cp_split._session_split_last_ts
                    if last_ts is None:
                        elapsed_h = 0.0
                    else:
                        elapsed_s = (now_split - last_ts).total_seconds()
                        # Sanity cap: 5-min max tick (HA restart / pause)
                        elapsed_h = max(0.0, min(elapsed_s, 300.0)) / 3600.0
                    cp_split._session_split_last_ts = now_split
                    if elapsed_h > 0:
                        # surplus already accounts for non-EV house load
                        solar_to_ev_kw = max(0.0, min(ev_current_kw, solar_surplus_kw))
                        grid_to_ev_kw = max(0.0, ev_current_kw - solar_to_ev_kw)
                        cp_split.session_solar_wh += solar_to_ev_kw * 1000.0 * elapsed_h
                        cp_split.session_grid_wh += grid_to_ev_kw * 1000.0 * elapsed_h
                elif not cp_split.session_active:
                    cp_split._session_split_last_ts = None

        use_embedded = self.config.get(CONF_OCPP_EMBEDDED, True)
        if use_embedded and self.ocpp_server is not None:
            cp = self.ocpp_server.get(charger_id)
            if cp is not None:
                want_charging = final_amps > 0
                # v0.28.1 fix, v0.28.7 made configurable: the "cable
                # plugged" state set for RemoteStartTransaction. Lenient
                # (default) includes Charging and Finishing in addition
                # to the OCPP 1.6 spec set (Preparing, SuspendedEV,
                # SuspendedEVSE) because the FoxESS L11PMC lingers in
                # Finishing after a cool-down stop and in Charging with
                # a 0 A profile applied. Strict restricts to the spec
                # set for spec-compliant chargers.
                if self.config.get(CONF_OCPP_RESTART_STRICT, False):
                    cable_plugged = cp.status in (
                        "Preparing", "SuspendedEV", "SuspendedEVSE",
                    )
                else:
                    cable_plugged = cp.status in (
                        "Preparing", "Charging", "SuspendedEV", "SuspendedEVSE", "Finishing",
                    )
                if want_charging and cable_plugged and not cp.session_active:
                    await cp.remote_start_transaction(id_tag="solar_ai")
                elif (not want_charging) and cp.session_active and cp.session_transaction_id:
                    await cp.remote_stop_transaction(cp.session_transaction_id)

                # v0.40.5 — desync watchdog / auto-heal.
                delivering = ev_current_kw > EV_STUCK_DELIVERING_KW
                await self._ev_charge_watchdog(cp, want_charging, delivering, now_ts)

        # Battery-lock (v0.27.2, refined v0.30.1): in FULL mode, lock the
        # house battery only while the EV is *actually* drawing power, not
        # from the moment FULL mode was selected. This is the difference
        # that matters when the car has its own internal scheduled-charge
        # timer (e.g. user sets FULL at 22:00 but the car is scheduled to
        # charge 02:00–06:00): the lock now engages at 02:00 when current
        # actually flows, not at 22:00 the moment FULL was selected. Lock
        # releases automatically when draw drops back below the threshold.
        want_lock = (
            self._ev_effective_mode == EV_MODE_FULL
            and ev_current_kw > EV_BATTERY_LOCK_POWER_THRESHOLD_KW
        )
        if want_lock != self._ev_battery_locked:
            await self._set_battery_lock(want_lock)

        # v0.38.3 — honest telemetry during COOLING. When the controller
        # wants to stop (target_kw == 0) but the anti-flap window is still
        # holding the last-commanded amps at the charger, the user-facing
        # `reason` and `target_kw` should reflect reality: charging *is*
        # continuing at minimum during the cool-down, not "stopped".
        # Without this override the dashboard reads target=0 / "stoppet"
        # while the charger is drawing 3.9 kW — confusing.
        reported_target_kw = target_kw
        if final_amps > 0 and target_kw <= 0.0:
            # The hysteresis held us in charging-at-minimum mode.
            reported_target_kw = round(
                final_amps * EV_VOLTAGE * EV_PHASES / 1000.0, 2,
            )
            cooling_left_s: int | None = None
            if self._ev_surplus_below_min_since_ts is not None:
                stop_window = int(self.config.get(
                    CONF_EV_STOP_WINDOW_SECONDS, DEFAULT_EV_STOP_WINDOW_SECONDS,
                ))
                elapsed = (datetime.now() - self._ev_surplus_below_min_since_ts).total_seconds()
                cooling_left_s = max(0, int(stop_window - elapsed))
            if cooling_left_s is not None:
                reason = self._msg(
                    f"PV: surplus {net_surplus_for_ev_kw:.1f} kW < min — "
                    f"charging continues at minimum ({reported_target_kw:.1f} kW) "
                    f"cooling down ({cooling_left_s}s)",
                    f"PV: overskud {net_surplus_for_ev_kw:.1f} kW < min — "
                    f"oplader fortsætter ved minimum ({reported_target_kw:.1f} kW) "
                    f"i nedkøling ({cooling_left_s}s)",
                )
            else:
                reason = self._msg(
                    f"PV: surplus {net_surplus_for_ev_kw:.1f} kW < min — "
                    f"charging continues at minimum ({reported_target_kw:.1f} kW)",
                    f"PV: overskud {net_surplus_for_ev_kw:.1f} kW < min — "
                    f"oplader fortsætter ved minimum ({reported_target_kw:.1f} kW)",
                )

        self._ev_last_reason = reason
        # v0.27.5: show NET surplus on the dashboard (after battery's current
        # absorption), not the raw PV-minus-house-load number. Below the
        # priority threshold this will show 0 because the battery is
        # consuming everything.
        return self._ev_telemetry(reported_target_kw, final_amps, net_surplus_for_ev_kw, reason)

    async def _get_modbus_backend(self):
        """Lazily build (and cache) the FoxESS Modbus charger backend.

        Returns None when no charger host is configured. The backend is rebuilt
        if the configured host/port/unit changes (config changes trigger an
        entry reload, which recreates the coordinator, so in practice this is
        created once per backend selection).
        """
        from .const import (  # noqa: PLC0415
            CONF_FOXESS_CHARGER_HOST, CONF_FOXESS_CHARGER_PORT, CONF_FOXESS_CHARGER_UNIT,
            DEFAULT_FOXESS_CHARGER_PORT, DEFAULT_FOXESS_CHARGER_UNIT,
            EV_MODBUS_SINGLE_PHASE_CAP_KW, EV_MODBUS_THREE_PHASE_CAP_KW,
            EV_MODBUS_MIN_AMPS, EV_MODBUS_MAX_AMPS, EV_MODBUS_SUSPEND_INTERVAL_MIN,
        )
        # Read via _setting so the dashboard host text + port/unit override the
        # config-entry values; rebuild the connection if any of them change.
        host = (self._setting(CONF_FOXESS_CHARGER_HOST, "") or "").strip()
        if not host:
            return None
        port = int(self._setting(CONF_FOXESS_CHARGER_PORT, DEFAULT_FOXESS_CHARGER_PORT))
        unit = int(self._setting(CONF_FOXESS_CHARGER_UNIT, DEFAULT_FOXESS_CHARGER_UNIT))
        key = (host, port, unit)
        if self._ev_modbus_backend is not None and self._ev_modbus_backend_key != key:
            await self.async_close_ev_backend()  # connection params changed
        if self._ev_modbus_backend is None:
            from .foxess_charger import FoxessModbusCharger  # noqa: PLC0415
            self._ev_modbus_backend = FoxessModbusCharger(
                host, port, unit,
                single_phase_cap_kw=EV_MODBUS_SINGLE_PHASE_CAP_KW,
                three_phase_cap_kw=EV_MODBUS_THREE_PHASE_CAP_KW,
                min_amps=EV_MODBUS_MIN_AMPS,
                max_amps=EV_MODBUS_MAX_AMPS,
                suspend_interval_min=EV_MODBUS_SUSPEND_INTERVAL_MIN,
            )
            self._ev_modbus_backend_key = key
        return self._ev_modbus_backend

    async def async_close_ev_backend(self) -> None:
        """Close the Modbus charger connection on unload (best-effort)."""
        if self._ev_modbus_backend is not None:
            try:
                await self._ev_modbus_backend.async_close()
            except Exception:  # noqa: BLE001
                pass
            self._ev_modbus_backend = None
            self._ev_modbus_backend_key = None

    @staticmethod
    def _ev_available_surplus_kw(
        ev_draw_kw: float, grid_export_kw: float, grid_import_kw: float,
        battery_charge_kw: float, battery_discharge_kw: float,
        battery_soc: float, priority_soc: float,
    ) -> float:
        """Export-aware available surplus for the EV (v0.59.0).

        The *solar* power the car could use right now:
          car draw + grid export − grid import − battery discharge
          (+ battery charge when the battery is at/above the EV priority SoC).

        - Subtracting battery discharge is essential: when the battery is
          covering part of the car's draw, that part is NOT solar, so without
          this the signal over-reads and the car over-commits (e.g. upshifts to
          three-phase on insufficient sun and drains the battery).
        - Adding battery charge above the priority SoC lets the car claim the
          surplus that would otherwise top off an already-high battery.
        Conserved as the car ramps (draw up, export down), so it doesn't
        oscillate. Clamped at >= 0.
        """
        extra = battery_charge_kw if battery_soc >= priority_soc else 0.0
        return max(
            0.0,
            ev_draw_kw + grid_export_kw - grid_import_kw - battery_discharge_kw + extra,
        )

    async def _run_ev_controller_modbus(
        self, evcc_state: dict, battery_soc: float, floor_soc: float,
    ) -> dict:
        """EV controller for the FoxESS Modbus backend — single-phase (v0.57.0).

        A simpler sibling of `_run_ev_controller`. Reuses the shared mode→target
        math, the anti-flap window, and the telemetry builder, but drives the
        charger over Modbus in single-phase: the power cap holds the charger in
        single-phase and the current modulates the rate (~1.4-3.7 kW), so the
        car follows much smaller solar surpluses than the 3-phase OCPP path.

        The setpoint is re-asserted every tick (heartbeat) because the charger
        reverts to full three-phase ~180 s after its last command. On a Modbus
        comms error the tick reports the charger unreachable and commands
        nothing — note this is the one drain risk the wire cannot cover: a dead
        link means we also cannot stop the charger before it self-reverts.
        """
        from .const import (  # noqa: PLC0415
            CONF_BATTERY_CHARGE_ENTITY, FOXESS_BATTERY_CHARGE_POWER,
            CONF_BATTERY_DISCHARGE_ENTITY, FOXESS_BATTERY_DISCHARGE_POWER,
            EV_MODBUS_MIN_AMPS, EV_MODBUS_MAX_AMPS,
            EV_MODBUS_UPSHIFT_KW, EV_MODBUS_DOWNSHIFT_KW, EV_MODBUS_SUSPEND_INTERVAL_MIN,
            EV_MODBUS_PHASE_AVG_WINDOW_SECONDS, EV_MODBUS_IMPORT_DOWNSHIFT_KW,
            EV_MODBUS_DOWNSHIFT_DWELL_SECONDS, EV_MODBUS_IMPORT_SUSTAINED_SECONDS,
            EV_MODBUS_MIN_DEADBAND_KW,
            CONF_EV_MODBUS_CURRENT_STEP, DEFAULT_EV_MODBUS_CURRENT_STEP,
        )

        backend = await self._get_modbus_backend()
        if backend is None:
            return {"ev_enabled": False, "ev_reason": "FoxESS Modbus charger host not configured"}

        # Read live charger state. Fail-safe: on comms error, command nothing.
        try:
            state = await backend.read_state()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("FoxESS Modbus charger unreachable: %s", err)
            self._ev_last_amps = 0
            self._ev_last_reason = self._msg(
                f"Modbus charger unreachable: {err}",
                f"Modbus-lader ikke tilgængelig: {err}",
            )
            return {**self._ev_telemetry(0.0, 0, 0.0, self._ev_last_reason),
                    "ev_backend": "foxess_modbus", "ev_charger_online": False,
                    "charger_power_kw": 0.0}

        ev_connected = state["connected"]

        # Plug-in detection → reset to the default-on-connect mode (mirror OCPP).
        if ev_connected and not self._ev_prev_connected:
            default_mode = self._stored.get(
                "ev_default_mode",
                self.config.get(CONF_EV_DEFAULT_MODE, DEFAULT_EV_DEFAULT_MODE),
            )
            self._ev_active_mode = default_mode
            self._stored["ev_active_mode"] = default_mode
            self._ev_surplus_above_min_since_ts = None
            self._ev_surplus_below_min_since_ts = None
            self._ev_arm_drop_since_ts = None
            self._ev_cool_entry_ts = None
            # Fresh session starts single-phase; let hysteresis upshift later.
            self._ev_modbus_phase = 1
            self._ev_modbus_phase_since_ts = None
            self._ev_modbus_avail_hist = []
            self._ev_modbus_phase_avg_hist = []
            self._ev_modbus_import_since_ts = None
            self._ev_modbus_override_fail_since_ts = None
            self._ev_modbus_override_3ph_blocked_until = None
            self._ev_session_was_override_induced = False
            self._reset_override_ramp()
            _LOGGER.info("EV plugged in (Modbus) — resetting mode to %s", default_mode)
        self._ev_prev_connected = ev_connected

        if not ev_connected:
            self._ev_last_amps = 0
            self._ev_last_reason = self._msg(
                f"EV not connected (status: {state['status_label']})",
                f"EV ikke tilsluttet (status: {state['status_label']})",
            )
            return {**self._ev_telemetry(0.0, 0, 0.0, self._ev_last_reason),
                    "ev_backend": "foxess_modbus", "ev_charger_online": True,
                    "ev_status_label": state["status_label"],
                    "charger_power_kw": 0.0, "charger_status": state["status_label"]}

        # ── Available surplus for the EV (export-aware, stable) — v0.59.0 ────
        # Drive the target off actual grid flow, not solar-minus-load: the
        # FoxESS load CT includes the car, so solar−load oscillates as the car
        # ramps (the estimate chased itself across the phase thresholds and the
        # car ended up stopping while solar was exported). The car's true
        # headroom is what it already draws PLUS what is spilling to grid, minus
        # any grid import — a quantity conserved as the car ramps (draw up,
        # export down by the same amount), so it doesn't thrash, and it credits
        # exported power so a full battery feeds the car instead of the grid.
        home_power_w = evcc_state.get("homePower", 0) or 0
        pv_power_w   = evcc_state.get("pvPower", 0) or 0
        grid_power_w = evcc_state.get("gridPower", 0) or 0
        grid_export_kw = max(0.0, -grid_power_w / 1000.0)
        grid_import_kw = max(0.0, grid_power_w / 1000.0)
        ev_current_kw  = state["power_kw"]
        house_load_kw  = home_power_w / 1000.0
        solar_kw       = pv_power_w / 1000.0
        battery_charge_kw = max(0.0, float(self._get_float_state(
            self.config.get(CONF_BATTERY_CHARGE_ENTITY, FOXESS_BATTERY_CHARGE_POWER), 0.0,
        ) or 0.0))
        battery_discharge_kw = max(0.0, float(self._get_float_state(
            self.config.get(CONF_BATTERY_DISCHARGE_ENTITY, FOXESS_BATTERY_DISCHARGE_POWER), 0.0,
        ) or 0.0))
        priority_soc = float(self._stored.get(
            "ev_battery_priority_soc",
            self.config.get(CONF_EV_BATTERY_PRIORITY_SOC, DEFAULT_EV_BATTERY_PRIORITY_SOC),
        ))
        # Above the EV battery-priority SoC, power going INTO the house battery
        # also counts as available, so the car takes priority over topping the
        # battery past that point (your "prioritise the car above 80%").
        available_kw = self._ev_available_surplus_kw(
            ev_current_kw, grid_export_kw, grid_import_kw,
            battery_charge_kw, battery_discharge_kw, battery_soc, priority_soc,
        )
        # Fallback to the solar-minus-load estimate only if the grid-flow signal
        # is unusable (no draw, no export and no import — e.g. grid sensors
        # missing), so the controller still works without grid sensors.
        if available_kw <= 0.0 and grid_export_kw <= 0.0 and grid_import_kw <= 0.0:
            non_ev_load_kw = max(0.0, house_load_kw - ev_current_kw)
            available_kw = max(0.0, solar_kw - non_ev_load_kw)
        # Median-of-3 spike filter: the export/draw/discharge sensors briefly
        # disagree during a phase switch or ramp (one tick can read near-zero
        # while the car is actually pulling kW), which would otherwise trigger a
        # false stop → re-arm thrash. The median rejects a single bad tick
        # without lagging genuine trend changes.
        self._ev_modbus_avail_hist.append(available_kw)
        self._ev_modbus_avail_hist = self._ev_modbus_avail_hist[-3:]
        available_kw = sorted(self._ev_modbus_avail_hist)[len(self._ev_modbus_avail_hist) // 2]

        # Resolve the active mode (needed by the phase decision + anti-flap).
        effective_mode, active_link = self._resolve_effective_ev_mode(self._ev_active_mode)
        self._ev_effective_mode = effective_mode
        self._ev_active_schedule_link = active_link

        # ── Phase decision: single vs three-phase ────────────────────────────
        # Hysteresis on a ROLLING AVERAGE of the available surplus (v0.59.6),
        # gated by the hardware suspend interval. The averaging window is the
        # dwell: it rides out brief clouds (no spurious downshift) and brief sun
        # peaks (no spurious upshift). Crucially — unlike the v0.59.5 countdown
        # timers — a single sample above/below the threshold cannot reset it, so
        # a choppy day whose instantaneous surplus oscillates across the line no
        # longer strands the charger on three-phase below its 4.14 kW floor.
        now_ts = datetime.now(timezone.utc)
        # Phase-switch / suspend interval — dashboard-adjustable (v0.59.13). The
        # L11PMC was verified to accept a 1-min value on reg 0x300B (the
        # documented 5-min "minimum" is not hardware-enforced), so switches can
        # be far snappier. The hardware write is held at the floor; this gates
        # only the controller's anti-thrash window.
        suspend_interval_min = max(1, int(float(self._stored.get(
            "ev_modbus_suspend_interval_min", EV_MODBUS_SUSPEND_INTERVAL_MIN))))
        interval_s = suspend_interval_min * 60
        since_switch = (
            (now_ts - self._ev_modbus_phase_since_ts).total_seconds()
            if self._ev_modbus_phase_since_ts is not None else interval_s + 1
        )
        # Append this tick's surplus and drop samples older than the window.
        # Window is dashboard-adjustable (v0.71.0); shorter = snappier upshift, the
        # downshift stays sticky via its own dwell. Floored at 60 s.
        phase_avg_window_s = max(60, int(60 * float(self._stored.get(
            "ev_modbus_phase_avg_window_min",
            EV_MODBUS_PHASE_AVG_WINDOW_SECONDS / 60))))
        self._ev_modbus_phase_avg_hist.append((now_ts, available_kw))
        cutoff = now_ts - timedelta(seconds=phase_avg_window_s)
        self._ev_modbus_phase_avg_hist = [
            (t, v) for (t, v) in self._ev_modbus_phase_avg_hist if t >= cutoff
        ]
        avg_avail_kw = (
            sum(v for _, v in self._ev_modbus_phase_avg_hist)
            / len(self._ev_modbus_phase_avg_hist)
        )
        # Upshift threshold is dashboard-adjustable (v0.59.8); falls back to the
        # const default. v0.70.0 — clamp it at least EV_MODBUS_MIN_DEADBAND_KW above
        # the downshift line so the hysteresis band can never be made pathologically
        # thin (the slider's 4.3 floor vs the 4.2 downshift gave a 0.1 kW band that
        # flapped on any noise).
        upshift_kw = max(
            EV_MODBUS_DOWNSHIFT_KW + EV_MODBUS_MIN_DEADBAND_KW,
            float(self._stored.get("ev_modbus_upshift_kw", EV_MODBUS_UPSHIFT_KW)),
        )
        # ── Battery-full override → three-phase escalation (v0.59.13) ─────────
        # When the override is active (battery full + export blocked + sun) the
        # surplus signal is pinned ~0, so the rolling-average decision would keep
        # us single-phase — capping the car at ~3.7 kW while the inverter can
        # produce far more (measured 7.2 kW curtailed). Force three-phase to
        # reach the curtailed PV. If three-phase can't be sustained (grid imports
        # at the 6 A floor → PV < 4.14 kW), the grid-drain guard sets
        # `_ev_modbus_override_3ph_blocked_until` and we fall back to single.
        ovr_max_soc = int(self._stored.get(
            "battery_max_soc", self.config.get("battery_max_soc", DEFAULT_BATTERY_MAX_SOC)))
        override_cooldown_active = (
            self._ev_probe_cooldown_until is not None
            and now_ts < self._ev_probe_cooldown_until)
        # Regime A — "solar would be wasted" → bump the car to three-phase to
        # absorb it. Fires when the inverter is actively curtailing PV (reg 49251:
        # export-limited with nowhere to store the surplus — covers a full battery,
        # a physical export cap, AND installs with no battery / an empty one), OR
        # the legacy case of a price export-block with the battery near full. The
        # flag path carries no SoC gate, so battery-less installs still grab
        # curtailed solar instead of clipping it.
        #
        # v0.75.3 — the near-full gate used `battery_max_soc - 2` (98% with the
        # default 100% max), which missed a confirmed real case at 97% SoC on
        # 2026-07-12: export blocked (price floor active), PV suppressed to
        # ~1-2.7 kW despite clear evidence it could do 5-6 kW, battery genuinely
        # tapering. Switched to a fixed EV_OVERRIDE_NEAR_FULL_SOC (96%), measured
        # directly against this battery's actual charge-taper onset rather than
        # derived from the configurable max-SoC setting.
        #
        # v0.75.14 — extended from EV_MODE_PV-only to also cover PV_BATTERY.
        # PV_BATTERY mode's own gap-filling logic (below, in
        # _compute_ev_target_kw) will happily drain the house battery to cover
        # the EV once solar surplus reads low — exactly the MPPT-throttled
        # reading this override exists to see through. The
        # `battery_discharge_kw <= ...THRESHOLD_KW` gate immediately below is
        # the backoff: it already requires the battery to NOT be discharging
        # before the override activates at all, and `_update_override_ramp`
        # re-checks live discharge on every subsequent tick. So the moment
        # PV_BATTERY's own logic starts genuinely draining the battery to cover
        # the gap, this override backs off on its own — it can only ever force
        # three-phase and ramp current while the battery stays idle, i.e. while
        # what's being harvested really is otherwise-wasted curtailed PV, not
        # battery power dressed up as solar.
        override_active = (
            effective_mode in (EV_MODE_PV, EV_MODE_PV_BATTERY)
            and solar_kw > 0.1
            and not override_cooldown_active
            and battery_discharge_kw <= EV_OVERRIDE_RAMP_BATTERY_DISCHARGE_THRESHOLD_KW
            and (
                self._pv_power_limited_flag
                or (self._current_floor_block is not None
                    and battery_soc >= EV_OVERRIDE_NEAR_FULL_SOC)
            ))
        override_3ph_blocked = (
            self._ev_modbus_override_3ph_blocked_until is not None
            and now_ts < self._ev_modbus_override_3ph_blocked_until)
        if effective_mode == EV_MODE_FULL:
            phase_pref = 3
        elif override_active and not override_3ph_blocked:
            phase_pref = 3   # escalate to three-phase to harvest curtailed PV
        elif avg_avail_kw >= upshift_kw:
            phase_pref = 3
        elif avg_avail_kw < EV_MODBUS_DOWNSHIFT_KW:
            phase_pref = 1
        else:
            phase_pref = self._ev_modbus_phase   # within the hysteresis band — hold
        override_3ph = override_active and not override_3ph_blocked
        # Grid-import guard (v0.70.0 — now SUSTAINED). On 3φ and not curtailing, drop
        # to 1φ when the car is genuinely buying from the grid (no battery, or an
        # empty one, can't cover the shortfall). A full battery does brief
        # charge/discharge balancing pulses that flip the meter to import for ~15 s
        # even under steady sun, so an instantaneous check bounced the phase on those
        # blips. Require the import to be CONTINUOUS for EV_MODBUS_IMPORT_SUSTAINED_
        # SECONDS: the balancing blips reset the timer on each zero-import tick and
        # never accumulate, while a real shortfall (continuous import) trips it.
        # v0.72.0 — exempt EV_MODE_FULL: that mode's entire purpose is to charge at
        # max rate regardless of solar, so sustained grid import is intentional, not
        # a shortfall. Without this exemption the guard tripped ~90 s into every
        # full-power session (verified live: continuous ~11 kW import from 04:19:52,
        # guard fired at 04:21:35, dropping the car to 1φ/~2.9 kW for ~50 s before
        # Full mode forced it back to 3φ — a repeating ramp-up/drop-back cycle).
        # PV_BATTERY is NOT exempt: it only draws the house battery to cover a
        # shortfall, never the grid, so sustained import there still means the
        # protection should fire.
        import_sustained_s = max(0, int(float(self._stored.get(
            "ev_modbus_import_sustained_sec", EV_MODBUS_IMPORT_SUSTAINED_SECONDS))))
        if (self._ev_modbus_phase == 3 and not override_3ph
                and effective_mode != EV_MODE_FULL
                and grid_import_kw > EV_MODBUS_IMPORT_DOWNSHIFT_KW):
            if self._ev_modbus_import_since_ts is None:
                self._ev_modbus_import_since_ts = now_ts
            importing_on_3ph = (
                (now_ts - self._ev_modbus_import_since_ts).total_seconds()
                >= import_sustained_s)
        else:
            self._ev_modbus_import_since_ts = None
            importing_on_3ph = False
        if importing_on_3ph:
            phase_pref = 1
        # v0.69.0 — Asymmetric anti-flap dwell. UPSHIFT (→3φ) stays fast: only the
        # rolling average gates it, so the car grabs solar immediately. DOWNSHIFT
        # (→1φ) must see the low surplus persist this long since the last switch —
        # because the surplus signal subtracts battery discharge, a passing cloud
        # the battery harmlessly covers still collapses the signal below the
        # downshift line; without the dwell that bounces 1φ↔3φ. Holding 3φ rides the
        # dip out on battery cover. Exempt: the import guard (drop at once when truly
        # buying) and the curtailment override (Regime A bump-up never delayed).
        going_down = phase_pref < self._ev_modbus_phase
        if going_down and not importing_on_3ph:
            required_dwell = max(interval_s, int(60 * float(self._stored.get(
                "ev_modbus_downshift_dwell_min",
                EV_MODBUS_DOWNSHIFT_DWELL_SECONDS / 60))))
        else:
            required_dwell = interval_s
        if phase_pref != self._ev_modbus_phase and since_switch >= required_dwell:
            _LOGGER.info(
                "EV Modbus phase switch %dφ → %dφ (avg surplus %.2f kW, now %.2f kW, "
                "import %.2f kW, dwell %ds)",
                self._ev_modbus_phase, phase_pref, avg_avail_kw, available_kw,
                grid_import_kw, required_dwell,
            )
            self._ev_modbus_phase = phase_pref
            self._ev_modbus_phase_since_ts = now_ts
        PHASES = self._ev_modbus_phase

        # Per-phase amp bounds from the min/max dropdowns (stored on a 3-phase
        # basis): recover the amps the user picked and apply to the ACTIVE phase.
        sel_min_amps = self._kw_to_amps(
            float(self._stored.get("ev_min_charge_kw", DEFAULT_EV_MIN_CHARGE_KW)))
        sel_max_amps = self._kw_to_amps(
            float(self._stored.get("ev_max_charge_kw", DEFAULT_EV_MAX_CHARGE_KW)))
        min_amps_sel = max(EV_MODBUS_MIN_AMPS, min(EV_MODBUS_MAX_AMPS, sel_min_amps))
        max_amps_sel = max(min_amps_sel, min(EV_MODBUS_MAX_AMPS, sel_max_amps))
        min_kw = self._amps_to_kw(min_amps_sel, PHASES)
        max_kw = self._amps_to_kw(max_amps_sel, PHASES)

        # Charging-current step (v0.59.9). The Modbus current register has 0.1 A
        # resolution; the default 1.0 A reproduces the prior whole-amp behaviour,
        # finer steps track the solar surplus more closely. The step is applied
        # inside _compute_ev_target_kw (where the surplus is floored to a step),
        # so the returned target_kw is already step-aligned.
        try:
            current_step = float(self._stored.get(
                CONF_EV_MODBUS_CURRENT_STEP, DEFAULT_EV_MODBUS_CURRENT_STEP))
        except (TypeError, ValueError):
            current_step = 1.0
        if current_step <= 0:
            current_step = 1.0

        target_kw, reason = self._compute_ev_target_kw(
            effective_mode, available_kw, battery_soc, floor_soc,
            min_kw, max_kw, priority_soc,
            grid_export_kw=grid_export_kw, ev_last_amps=self._ev_last_amps,
            phases=PHASES, current_step=current_step,
            mode_just_changed=self._ev_mode_change_pending,
        )
        # Convert the (already step-aligned) target to per-phase amps at the
        # register's native 0.1 A resolution, clamped to the user's envelope.
        if target_kw <= 0:
            target_amps = 0
        else:
            raw_amps = target_kw * 1000.0 / (EV_VOLTAGE * PHASES)
            target_amps = round(
                max(min_amps_sel, min(max_amps_sel, raw_amps)), 2)

        # No separate battery-discharge hard-stop here (unlike the v0.54.0 OCPP
        # fix): `available_kw` already subtracts battery discharge, so by energy
        # balance it equals the true solar surplus. The target therefore tracks
        # the solar exactly and the car ramps down to match rather than draining
        # the battery — a hard stop would just cause stop/export/restart cycling.

        # ── Battery-full override (v0.59.10) ──────────────────────────────────
        # Ported from the OCPP controller, which the Modbus path never reaches
        # (_run_ev_controller hands off to this method before the override code).
        # Breaks the export-blocked + battery-full curtailment deadlock: when the
        # price-floor block is open (export blocked on a low/negative price), the
        # house battery is full, and PV is producing, the inverter throttles MPPT
        # to the AC load — so the export-aware surplus reads ~0, the car never
        # starts, and PV stays curtailed. Actively ramp the EV draw while watching
        # grid import / battery discharge so it harvests only the otherwise-wasted
        # PV; once MPPT lifts and real surplus appears, normal tracking returns a
        # higher target and the override yields.
        override_forcing = False
        # Fresh session about to begin → clear the override session marker so
        # only genuinely override-induced sessions get the soft cool-down.
        if self._ev_last_amps == 0:
            self._ev_session_was_override_induced = False
        # `override_active` was computed in the phase decision above (it also
        # drives the three-phase escalation). PHASES is already 3 here when the
        # override escalated, so the ramp climbs on three-phase to harvest the
        # curtailed PV the single-phase wall couldn't reach.
        if override_active:
            ramp_amps = self._update_override_ramp(
                now_ts, grid_import_kw, battery_discharge_kw,
                min_amps_sel, max_amps_sel,
            )
            ramp_kw = self._amps_to_kw(ramp_amps, PHASES)
            if target_amps <= ramp_amps:
                target_amps = ramp_amps
                override_forcing = True
                self._ev_session_was_override_induced = True
                reason = self._msg(
                    f"Override: battery full ({battery_soc:.0f}%/{ovr_max_soc}%) + export "
                    f"blocked — EV draws {ramp_amps:g} A {PHASES}φ ({ramp_kw:.2f} kW), "
                    f"grid import {grid_import_kw:.2f} kW (raw PV {solar_kw:.2f} kW)",
                    f"Override: batteri fuldt ({battery_soc:.0f}%/{ovr_max_soc}%) + eksport "
                    f"blokeret — EV trækker {ramp_amps:g} A {PHASES}φ ({ramp_kw:.2f} kW), "
                    f"net-import {grid_import_kw:.2f} kW (rå PV {solar_kw:.2f} kW)",
                )
            # Drain guard: ramp pinned at min but still importing for a sustained
            # stretch → MPPT can't cover even the minimum draw from PV at this
            # phase.
            if (ramp_amps <= min_amps_sel
                    and grid_import_kw > EV_OVERRIDE_RAMP_GRID_IMPORT_THRESHOLD_KW):
                if self._ev_modbus_override_fail_since_ts is None:
                    self._ev_modbus_override_fail_since_ts = now_ts
                elif (now_ts - self._ev_modbus_override_fail_since_ts).total_seconds() >= 120:
                    self._ev_modbus_override_fail_since_ts = None
                    self._reset_override_ramp()
                    if PHASES == 3:
                        # Three-phase needs ≥4.14 kW and the sun can't supply it.
                        # Block 3φ briefly and fall back to single-phase (which
                        # harvests down to ~1.4 kW); retry 3φ later in case the
                        # sun strengthens.
                        self._ev_modbus_override_3ph_blocked_until = (
                            now_ts + timedelta(seconds=EV_OVERRIDE_3PH_RETRY_SECONDS))
                        reason = self._msg(
                            "Override: 3-phase can't be sustained — falling back to single-phase",
                            "Override: trefaset kan ikke holdes — falder tilbage til enfaset",
                        )
                    else:
                        # Single-phase override also can't cover its minimum from
                        # PV → nothing to harvest; cool down before retrying.
                        self._ev_probe_cooldown_until = (
                            now_ts + timedelta(seconds=EV_CURTAILMENT_PROBE_COOLDOWN_SECONDS))
                        target_amps = 0
                        override_forcing = False
                        reason = self._msg(
                            "Override paused: MPPT not lifting (grid import at minimum) "
                            "— cooling down before retry",
                            "Override pause: MPPT løfter ikke (net-import ved minimum) "
                            "— afkøling før nyt forsøg",
                        )
            else:
                self._ev_modbus_override_fail_since_ts = None
        else:
            self._ev_modbus_override_fail_since_ts = None
            self._reset_override_ramp()

        # Brief-dip hold (v0.59.6): on three-phase, if the instantaneous surplus
        # can't meet the 3φ floor (target 0) but the rolling average still favors
        # three-phase (we are still PHASES==3), hold at the 3φ minimum rather
        # than stopping — so a passing cloud doesn't interrupt a genuinely sunny
        # session. This draws a small amount from the battery for those moments.
        # It is bounded: a sustained dip drops the rolling average below the
        # downshift threshold, the phase decision falls to single-phase (which
        # charges from solar only), and at most one suspend interval (~5 min)
        # elapses before that downshift takes effect. Replaces the old guard that
        # stopped the car cleanly (which on a choppy day meant long stalls).
        # v0.75.5 — skip the brief-dip hold on the tick right after a mode
        # change. The hold's premise is "this is a momentary cloud dip inside
        # an already-established 3-phase session", which doesn't apply the
        # instant the mode itself just changed — `_ev_modbus_phase` can still
        # read 3 from whatever mode was active a moment ago (e.g. Full),
        # forcing the new mode's correctly-computed 0 target back up to the
        # 3-phase minimum and defeating the same-version mode-change bypass
        # in _apply_ev_time_window below.
        if PHASES == 3 and target_amps == 0 and not self._ev_mode_change_pending:
            target_amps = min_amps_sel
            reason = self._msg(
                f"PV: surplus {available_kw:.1f} kW < 3φ floor — "
                f"holding at three-phase minimum (brief dip)",
                f"PV: overskud {available_kw:.1f} kW < 3φ-grænse — "
                f"holder ved trefaset minimum (kortvarigt dyk)",
            )

        final_amps = self._apply_ev_time_window(target_amps, probing=override_forcing)

        # Soft cool-down on override-induced session end (v0.59.10, mirror of the
        # OCPP path): when an override-induced session ends (was drawing, now
        # stopping), arm a cool-down before the override may fire again, so it
        # can't thrash on/off as surplus oscillates under partly-cloudy skies.
        if (self._ev_session_was_override_induced
                and self._ev_last_amps > 0
                and final_amps == 0):
            self._ev_probe_cooldown_until = now_ts + timedelta(
                seconds=EV_OVERRIDE_SOFT_COOLDOWN_SECONDS)
            self._ev_session_was_override_induced = False

        # No 2 A/tick ramp clamp on the Modbus path (v0.59.2): the target is
        # already the median-smoothed true solar surplus, so let the current go
        # straight to it. The old slow ramp lagged behind rising PV and exported
        # the difference during the climb; the charger/EV ramp their own draw
        # smoothly regardless, and the export-aware signal self-corrects any
        # momentary overshoot on the next tick.

        # Heartbeat: ALWAYS apply (unlike OCPP's dedup) so the setpoint never
        # expires. amps<=0 stops; amps>0 holds the chosen phase + sets current.
        try:
            await backend.async_apply(
                final_amps, phases=PHASES, status=state["status"],
                drawing=state["live_phases"] > 0,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("FoxESS Modbus apply failed: %s", err)
        self._ev_last_amps = final_amps
        self._ev_last_rate_assert_ts = now_ts

        # Battery-lock (v0.59.10 — ported from the OCPP path): in FULL ("hurtig")
        # mode, lock the house battery while the car is actually drawing, so the
        # car's demand is met from solar + grid and never by raiding the house
        # battery. Releases automatically when the draw stops or the mode leaves
        # FULL. (PV-mode never needs this — its target tracks solar surplus and
        # the battery-full override yields if the battery is discharging.)
        want_lock = (
            effective_mode == EV_MODE_FULL
            and ev_current_kw > EV_BATTERY_LOCK_POWER_THRESHOLD_KW
        )
        if want_lock != self._ev_battery_locked:
            await self._set_battery_lock(want_lock)

        # Honest COOLING telemetry: holding at minimum while target is 0.
        reported_target_kw = target_kw
        if final_amps > 0 and target_kw <= 0.0:
            reported_target_kw = round(self._amps_to_kw(final_amps, PHASES), 2)

        self._ev_last_reason = reason
        return {
            **self._ev_telemetry(reported_target_kw, final_amps, available_kw, reason),
            "ev_backend": "foxess_modbus",
            "ev_charger_online": True,
            "ev_status_label": state["status_label"],
            # Surface to the existing charger sensors so they reflect Modbus —
            # the OCPP power/status sources are dead in Modbus mode.
            "charger_power_kw": ev_current_kw,
            "charger_status": state["status_label"],
            "charger_phase_currents": [state["l1"], state["l2"], state["l3"]],
            "charger_live_phases": state["live_phases"],
            "charger_target_phases": PHASES,
            # v0.59.12 TEST — actual 0x300B value the charger holds (1=accepted sub-5, 5=clamped).
            "charger_suspend_interval": state.get("suspend_interval"),
        }

    def _msg(self, en: str, da: str) -> str:
        """Return a user-facing string in the integration's resolved language (v0.41.0).

        Both arguments are already-formatted strings; this just picks one.
        Danish HA → `da`, anything else → `en`.
        """
        return da if self._lang == "da" else en

    @staticmethod
    def _ev_session_demand_kw(
        *,
        connected: bool,
        charging_now: bool,
        effective_mode: str,
        requested_mode: str,
        live_kw: float,
        max_kw: float,
    ) -> float:
        """Live EV demand the optimiser should treat as near-certain (v0.45.0, E1).

        Returns 0.0 unless the EV is plugged in AND in a forced-draw situation —
        actively charging, the controller's effective mode is pv+battery or full
        (fast), or the requested EVCC mode is now/minpv. Pure-PV charging returns
        0.0 because the solar→EV idle dynamics already account for it. When a
        session is forced, prefer the live charge power, else the learned max."""
        forced = bool(connected) and (
            bool(charging_now)
            or effective_mode in (EV_MODE_PV_BATTERY, EV_MODE_FULL)
            or requested_mode in (EV_MODE_NOW, EV_MODE_MIN_PV)
        )
        if not forced:
            return 0.0
        return live_kw if live_kw > 0.0 else max(0.0, float(max_kw))

    def _compute_ev_target_kw(
        self, mode: str, solar_surplus: float, battery_soc: float,
        floor_soc: float, min_kw: float, max_kw: float,
        priority_soc: float = 80.0,
        grid_export_kw: float = 0.0,
        ev_last_amps: int = 0,
        phases: int = EV_PHASES,
        current_step: float = 1.0,
        mode_just_changed: bool = False,
    ) -> tuple[float, str]:
        """Pure mode→target translation. Returns (target_kw, human-readable reason).

        Battery-priority threshold (v0.26.4): in PV and PV+battery modes, EV
        charging is held off until `battery_soc >= priority_soc`. The inverter
        naturally diverts solar surplus to the battery while the EV target is
        0, so the battery fills first; once the threshold is reached, EV
        resumes normal surplus tracking. FULL mode ignores this (user wants
        max charge regardless of battery state).

        v0.39.19 — `grid_export_kw` bypasses the priority gate. When the
        inverter is actively exporting more than `min_kw` to the grid,
        the priority gate's "fill battery first" purpose is moot: PV
        already exceeds battery + house combined, the excess is being
        given away to the grid at sell price. Releasing the gate lets
        the EV consume the export at buy-price savings (typically a
        0.5-1.0 DKK/kWh net win per diverted kWh).

        v0.39.20 — `ev_last_amps` further narrows the gate to apply only
        when the EV is IDLE (`ev_last_amps == 0`). Once the EV is
        already charging, the gate's purpose ("don't start the EV mid-
        battery-fill") is moot — the start has already happened. Re-
        applying the gate during charging caused thrashing in v0.39.19:
        the EV's own draw would consume the export → grid_export drops
        to 0 → gate re-activates → target = 0 → stop_window → EV stops
        → export resumes → gate releases → cycle every ~4 min. Letting
        surplus tracking alone govern the running EV (it returns 0 when
        surplus < min, triggering the natural stop_window) eliminates
        the oscillation.

        v0.75.12 — `mode_just_changed` also opens the gate (in addition to
        `ev_last_amps == 0`). `ev_last_amps` is the raw last-commanded current
        from WHATEVER mode was active a moment ago, not specific to PV mode's
        own decision history — switching Full → PV mid-session leaves it
        non-zero (Full was just commanding max_kw), which made the gate treat
        a car that was charging for a completely different reason as "already
        legitimately charging under PV mode, don't interrupt it" and skip the
        battery-priority check entirely. A user reported exactly this: Full
        mode charging, switched to solar-only, and the EV kept charging past
        the priority SoC threshold instead of waiting for the battery to
        fill. The v0.39.20 anti-thrash reasoning still holds for an ONGOING
        pv-mode session — this only re-opens the gate for the single tick
        right after a deliberate mode switch, same scope as the other
        mode-change fixes tonight.
        """
        if mode == EV_MODE_LOCKED:
            return 0.0, self._msg("Mode: Locked — no charging", "Mode: Låst — ingen opladning")

        if mode == EV_MODE_FULL:
            return max_kw, self._msg(f"Mode: Full power — {max_kw:.1f} kW", f"Mode: Fuld kraft — {max_kw:.1f} kW")

        # Battery-priority gate (applies to PV mode only — v0.27.2 fix).
        # v0.39.19 — bypass when grid_export_kw > min_kw.
        # v0.39.20 — bypass when EV is already charging (the gate is
        # an IDLE→start gate, not a stop-the-running-EV gate).
        # v0.75.12 — also apply the gate (not bypass) on the tick right after
        # a mode change, even if ev_last_amps is stale-nonzero from whatever
        # mode was active before. See docstring.
        if (mode == EV_MODE_PV
                and battery_soc < priority_soc
                and grid_export_kw <= min_kw
                and (ev_last_amps == 0 or mode_just_changed)):
            return 0.0, self._msg(
                f"Battery prioritised: {battery_soc:.0f}% / {priority_soc:.0f}% "
                f"— EV waits until the battery is full",
                f"Batteri prioriteret: {battery_soc:.0f}% / {priority_soc:.0f}% "
                f"— EV venter til batteri er fyldt",
            )

        if mode == EV_MODE_PV:
            if solar_surplus >= min_kw:
                # Floor to the current step (v0.27.2 / v0.59.9): when surplus
                # falls *between* two steps, command the LOWER step so the
                # fractional surplus flows into the house battery instead of
                # being waste-exported or pulled from grid. The step defaults to
                # 1 A (whole amps), but the FoxESS Modbus backend can pass a
                # finer step (0.5 / 0.1 A) for tighter solar tracking. Example
                # at 1 A: 5.4 kW surplus → 7 A (4.83 kW to EV), 0.57 kW to battery.
                import math
                line_voltage_kw = EV_VOLTAGE * phases / 1000.0  # 0.69 kW/A (3φ), 0.23 (1φ)
                step = current_step if current_step > 0 else 1.0
                raw_amps = math.floor((solar_surplus / line_voltage_kw) / step) * step
                max_amps = max(EV_OCPP_MIN_AMPS, int(round(max_kw / line_voltage_kw)))
                amps = max(EV_OCPP_MIN_AMPS, min(max_amps, raw_amps))
                target = amps * line_voltage_kw
                excess = max(0.0, solar_surplus - target)
                if excess > 0.05:  # only show "til batteri" if meaningful
                    return target, self._msg(
                        f"PV: {solar_surplus:.2f} kW surplus → {target:.2f} kW "
                        f"({amps:g} A), {excess:.2f} kW to battery",
                        f"PV: {solar_surplus:.2f} kW overskud → {target:.2f} kW "
                        f"({amps:g} A), {excess:.2f} kW til batteri",
                    )
                return target, self._msg(
                    f"PV: {solar_surplus:.2f} kW surplus → {target:.2f} kW ({amps:g} A)",
                    f"PV: {solar_surplus:.2f} kW overskud → {target:.2f} kW ({amps:g} A)",
                )
            return 0.0, self._msg(
                f"PV: surplus {solar_surplus:.1f} kW < min {min_kw:.1f} kW — stopped",
                f"PV: overskud {solar_surplus:.1f} kW < min {min_kw:.1f} kW — stoppet",
            )

        if mode == EV_MODE_PV_BATTERY:
            if solar_surplus >= min_kw:
                target = min(solar_surplus, max_kw)
                return target, self._msg(
                    f"PV+battery: {solar_surplus:.1f} kW surplus → {target:.1f} kW",
                    f"PV+batteri: {solar_surplus:.1f} kW overskud → {target:.1f} kW",
                )
            # Solar can't reach min — can the battery help?
            if battery_soc > floor_soc:
                return min_kw, self._msg(
                    f"PV+battery: solar {solar_surplus:.1f} kW insufficient, "
                    f"battery covers the gap → {min_kw:.1f} kW",
                    f"PV+batteri: sol {solar_surplus:.1f} kW utilstrækkelig, "
                    f"batteri dækker forskel → {min_kw:.1f} kW",
                )
            return 0.0, self._msg(
                f"PV+battery: solar {solar_surplus:.1f} kW < min and battery at floor — stopped",
                f"PV+batteri: sol {solar_surplus:.1f} kW < min og batteri ved gulv — stoppet",
            )

        return 0.0, self._msg(f"Unknown mode: {mode}", f"Ukendt mode: {mode}")

    @staticmethod
    def _kw_to_amps(kw: float, phases: int = EV_PHASES) -> int:
        """Convert target kW to per-phase line current (A), clamped to limits.

        Danish wye system: P = phases × V_phase × I (cos φ ≈ 1 for EVs), with
        V_phase = 230 V. Defaults to 3-phase (the OCPP path); the Modbus
        single-phase backend passes `phases=1`.

        Verification (3-phase): 6 A → 4.14 kW (DEFAULT_EV_MIN_CHARGE_KW),
                     16 A → 11.04 kW (DEFAULT_EV_MAX_CHARGE_KW).
        Single-phase: 6 A → 1.38 kW, 16 A → 3.68 kW.
        """
        if kw <= 0:
            return 0
        amps = int(round(kw * 1000.0 / (EV_VOLTAGE * phases)))
        return max(EV_OCPP_MIN_AMPS, min(EV_OCPP_MAX_AMPS, amps))

    @staticmethod
    def _amps_to_kw(amps: int, phases: int = EV_PHASES) -> float:
        """Convert per-phase line current (A) back to kW. Inverse of _kw_to_amps."""
        return amps * EV_VOLTAGE * phases / 1000.0

    def _reset_override_ramp(self) -> None:
        """Clear the active-ramp state (v0.39.21).

        Called when the override deactivates, the EV goes idle, or it
        disconnects, so the next override session re-probes from min.
        """
        self._ev_override_ramp_amps = 0
        self._ev_override_ramp_last_step_ts = None
        self._ev_override_ramp_freeze_until = None

    def _update_override_ramp(
        self,
        now_ts: datetime,
        grid_import_kw: float,
        battery_discharge_kw: float,
        min_amps: int,
        max_amps: int,
    ) -> int:
        """Advance the battery-full override ramp by at most one step (v0.39.21).

        Returns the amps the override should command this tick:
          - First override tick of a session → initialise to ``min_amps``.
          - Grid import OR house-battery discharge above threshold → the EV
            draw is not being covered by curtailed PV (MPPT isn't keeping up, or
            the battery is making up the gap), so step down 1 A and freeze
            further up-steps for ``EV_OVERRIDE_RAMP_FREEZE_SECONDS`` (v0.54.0
            adds the battery-discharge signal; grid import alone misses the case
            where the battery silently covers the draw).
          - Otherwise, once the EV is actually charging and the step
            interval has elapsed and we're not frozen and below ``max_amps``
            → step up 1 A.
          - Else hold.
        """
        # Initialise on the first override tick of a session.
        if self._ev_override_ramp_amps < min_amps:
            self._ev_override_ramp_amps = min_amps
            self._ev_override_ramp_last_step_ts = now_ts
            self._ev_override_ramp_freeze_until = None
            return self._ev_override_ramp_amps

        # Over-commit: grid importing or battery discharging → the last step
        # isn't being covered by curtailed PV.
        if (grid_import_kw > EV_OVERRIDE_RAMP_GRID_IMPORT_THRESHOLD_KW
                or battery_discharge_kw > EV_OVERRIDE_RAMP_BATTERY_DISCHARGE_THRESHOLD_KW):
            if self._ev_override_ramp_amps > min_amps:
                self._ev_override_ramp_amps -= 1
            self._ev_override_ramp_freeze_until = (
                now_ts + timedelta(seconds=EV_OVERRIDE_RAMP_FREEZE_SECONDS)
            )
            self._ev_override_ramp_last_step_ts = now_ts
            return self._ev_override_ramp_amps

        # Headroom available: ramp up if eligible.
        frozen = (
            self._ev_override_ramp_freeze_until is not None
            and now_ts < self._ev_override_ramp_freeze_until
        )
        # Step interval is dashboard-adjustable (v0.59.13); falls back to the
        # const default. Floor at 3 s so it can't busy-step.
        ramp_interval_s = max(3.0, float(self._stored.get(
            "ev_override_ramp_interval_s", EV_OVERRIDE_RAMP_INTERVAL_SECONDS)))
        interval_ok = (
            self._ev_override_ramp_last_step_ts is None
            or (now_ts - self._ev_override_ramp_last_step_ts).total_seconds()
            >= ramp_interval_s
        )
        if (
            not frozen
            and interval_ok
            and self._ev_override_ramp_amps < max_amps
            and self._ev_last_amps > 0  # only climb once actually charging
        ):
            self._ev_override_ramp_amps += 1
            self._ev_override_ramp_last_step_ts = now_ts
        return self._ev_override_ramp_amps

    def _ev_charge_threshold_w(self) -> float:
        """Return the configured 'EV is truly charging' threshold in watts."""
        return float(self.config.get(
            CONF_EV_CHARGE_THRESHOLD_W, DEFAULT_EV_CHARGE_THRESHOLD_W,
        ))

    # ────────────────────────────────────────────────────────────────────
    # Battery-lock helper (v0.27.2) — prevents house battery discharge
    # while EV is in FULL mode (so EV's grid demand isn't satisfied by
    # raiding the house battery). Battery may still charge from solar.
    # ────────────────────────────────────────────────────────────────────

    FOXESS_MAX_DISCHARGE_ENTITY = "number.foxessmodbus_max_discharge_current"

    async def _set_battery_lock(self, locked: bool) -> None:
        """Apply or release the house-battery discharge lock (v0.27.4 hardened).

        v0.27.2 wrote 0 to max_discharge_current with `blocking=False` — which
        silently swallowed failures. Battery still drained because the call
        failed but we didn't notice.

        v0.27.4 uses defence-in-depth:
          1. Write 0 to `number.foxessmodbus_max_discharge_current` with
             `blocking=True` (raises on failure → logged at WARNING level
             so it surfaces in system_log).
          2. Verify entity exists before writing — log a clear error if not.
          3. If running on EVCC live-data, ALSO POST `batteryMode=hold` to
             EVCC's API. EVCC controls the inverter battery mode directly
             via its own Modbus integration, so this is a redundant but
             different code path.

        Either mechanism alone should suffice; together they should reliably
        prevent house-battery discharge while EV charges from grid.
        """
        if locked == self._ev_battery_locked:
            return

        # ─── ENGAGE LOCK ──────────────────────────────────────────────
        if locked:
            mechanisms_ok = []
            mechanisms_failed = []

            # Mechanism 1: max_discharge_current → 0
            entity_state = self.hass.states.get(self.FOXESS_MAX_DISCHARGE_ENTITY)
            if entity_state is None:
                _LOGGER.error(
                    "Battery lock: entity %s not found — cannot apply "
                    "max_discharge_current mechanism. Verify FoxESS Modbus is loaded.",
                    self.FOXESS_MAX_DISCHARGE_ENTITY,
                )
                mechanisms_failed.append("max_discharge_current (entity missing)")
            else:
                try:
                    prev = float(entity_state.state) if entity_state.state not in (None, "unknown", "unavailable") else 50.0
                    if prev > 0:
                        self._ev_battery_lock_prev_a = prev
                    await self.hass.services.async_call(
                        "number", "set_value",
                        {"entity_id": self.FOXESS_MAX_DISCHARGE_ENTITY, "value": 0},
                        blocking=True,
                    )
                    mechanisms_ok.append(
                        f"max_discharge_current 0 A (was {self._ev_battery_lock_prev_a})"
                    )
                except Exception as err:  # noqa: BLE001
                    mechanisms_failed.append(f"max_discharge_current ({err})")

            # Mechanism 2: EVCC battery mode → hold (if on EVCC live-data)
            if self._setting(CONF_LIVE_DATA_SOURCE, "evcc") in ("evcc", "hybrid"):
                try:
                    evcc_url = self.config.get("evcc_url", "")
                    if not evcc_url:
                        raise RuntimeError("No EVCC URL configured")
                    session = async_get_clientsession(self.hass)
                    await self._evcc_post(
                        session, evcc_url,
                        f"{EVCC_API_BATTERY_MODE}/{EVCC_BATTERY_HOLD}",
                    )
                    self._we_set_evcc_mode = True
                    mechanisms_ok.append("EVCC batteryMode=hold")
                except Exception as err:  # noqa: BLE001
                    mechanisms_failed.append(f"EVCC batteryMode ({err})")

            if mechanisms_ok:
                _LOGGER.info(
                    "EV controller: house battery LOCKED via [%s]%s",
                    "; ".join(mechanisms_ok),
                    f" — failures: {'; '.join(mechanisms_failed)}" if mechanisms_failed else "",
                )
                self._ev_battery_locked = True
            else:
                _LOGGER.error(
                    "EV controller: house battery LOCK FAILED on all mechanisms: %s",
                    "; ".join(mechanisms_failed),
                )
                # Don't set the flag — we'll retry on next tick

        # ─── RELEASE LOCK ─────────────────────────────────────────────
        else:
            mechanisms_ok = []
            mechanisms_failed = []

            restore_a = self._ev_battery_lock_prev_a or 50.0
            entity_state = self.hass.states.get(self.FOXESS_MAX_DISCHARGE_ENTITY)
            if entity_state is not None:
                try:
                    await self.hass.services.async_call(
                        "number", "set_value",
                        {"entity_id": self.FOXESS_MAX_DISCHARGE_ENTITY, "value": restore_a},
                        blocking=True,
                    )
                    mechanisms_ok.append(f"max_discharge_current → {restore_a:.1f} A")
                except Exception as err:  # noqa: BLE001
                    mechanisms_failed.append(f"max_discharge_current ({err})")

            if (self._setting(CONF_LIVE_DATA_SOURCE, "evcc") in ("evcc", "hybrid")
                and self._we_set_evcc_mode):
                try:
                    evcc_url = self.config.get("evcc_url", "")
                    if not evcc_url:
                        raise RuntimeError("No EVCC URL configured")
                    session = async_get_clientsession(self.hass)
                    await self._evcc_post(
                        session, evcc_url,
                        f"{EVCC_API_BATTERY_MODE}/{EVCC_BATTERY_NORMAL}",
                    )
                    self._we_set_evcc_mode = False
                    mechanisms_ok.append("EVCC batteryMode=normal")
                except Exception as err:  # noqa: BLE001
                    mechanisms_failed.append(f"EVCC batteryMode ({err})")

            _LOGGER.info(
                "EV controller: house battery UNLOCKED via [%s]%s",
                "; ".join(mechanisms_ok) if mechanisms_ok else "no-op",
                f" — failures: {'; '.join(mechanisms_failed)}" if mechanisms_failed else "",
            )
            self._ev_battery_lock_prev_a = None
            self._ev_battery_locked = False

    def set_ev_battery_priority_soc(self, value: float) -> None:
        """Public setter for the battery-priority SoC slider (v0.26.4).

        Clamped to 50–100 %. Persists via storage so it survives HA restarts.
        """
        clamped = max(50.0, min(100.0, float(value)))
        self._stored["ev_battery_priority_soc"] = clamped
        if self.hass:
            self.hass.async_create_task(self._store.async_save(self._stored))

    # ────────────────────────────────────────────────────────────────────
    # OCPP session-log harvester (v0.27.0)
    # ────────────────────────────────────────────────────────────────────

    OCPP_SESSION_LOG_MAX = 500    # storage cap — same as solar_floor_log

    def _persist_charger_metadata(self) -> None:
        """Snapshot each connected ChargePoint's identity into storage (v0.27.3).

        Runs every main update tick. Lets the data survive HA restarts so
        sensors don't go blank between the moment Solar AI starts up and
        the moment the charger sends a fresh BootNotification (which
        usually doesn't happen on a transport reconnect).

        The dict is shared by-reference with `OcppServer.persisted_metadata`,
        so the server uses these values to pre-populate a new ChargePoint
        instance the moment it accepts the WebSocket connection.

        Storage write happens on the learning tick (not every fast tick) —
        in-memory dict mutations are cheap.
        """
        if self.ocpp_server is None:
            return
        md_root = self._stored.setdefault("charger_metadata", {})
        for cp_id, cp in self.ocpp_server.charge_points.items():
            if cp.vendor or cp.model or cp.serial or cp.energy_wh_total > 0:
                md_root[cp_id] = {
                    "vendor": cp.vendor,
                    "model": cp.model,
                    "firmware": cp.firmware,
                    "serial": cp.serial,
                    "last_energy_wh_total": cp.energy_wh_total,
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                    # v0.37.0 — session-tracking snapshot. Persisting these
                    # alongside vendor/model lets a HA restart preserve the
                    # transaction id, which RemoteStopTransaction needs to
                    # target a runaway session. Without this, today's
                    # observed runaway (Item 5) repeats: charger keeps
                    # drawing, Solar AI's stop commands have nothing to
                    # target. Fields are restored in OcppServer._handle_connection.
                    "session_active": cp.session_active,
                    "session_transaction_id": cp.session_transaction_id,
                    "session_start_ts": (
                        cp.session_start_ts.isoformat()
                        if cp.session_start_ts is not None else None
                    ),
                    "session_start_energy_wh": cp.session_start_energy_wh,
                    "session_energy_wh": cp.session_energy_wh,
                    "session_solar_wh": cp.session_solar_wh,
                    "session_grid_wh": cp.session_grid_wh,
                }

    def _harvest_ocpp_sessions(self) -> None:
        """Pick up any completed sessions from the embedded OCPP server.

        Each ChargePoint sets `last_session_summary` to a dict when a
        StopTransaction arrives. We append it to `_stored["charger_session_log"]`
        (capped at 500), bump the lifetime energy counter, and clear the
        summary so the same session isn't appended twice.

        Pattern matches `_open_floor_block` / `solar_floor_log` from v0.25.x.
        """
        if self.ocpp_server is None:
            return
        log = self._stored.setdefault("charger_session_log", [])
        lifetime_kwh = float(self._stored.get("charger_lifetime_energy_kwh", 0.0))
        changed = False
        for cp in self.ocpp_server.charge_points.values():
            if cp.last_session_summary is None:
                continue
            log.append(cp.last_session_summary)
            lifetime_kwh += cp.last_session_summary.get("energy_kwh", 0.0)
            cp.last_session_summary = None
            changed = True
        if changed:
            # Cap at OCPP_SESSION_LOG_MAX (drop oldest)
            if len(log) > self.OCPP_SESSION_LOG_MAX:
                self._stored["charger_session_log"] = log[-self.OCPP_SESSION_LOG_MAX:]
            self._stored["charger_lifetime_energy_kwh"] = round(lifetime_kwh, 3)

    def get_charger_session_log(self, n: int = 20) -> list[dict]:
        """Return the last N completed charger sessions, newest first."""
        log = self._stored.get("charger_session_log", [])
        return list(reversed(log[-n:]))

    def get_charger_lifetime_energy_kwh(self) -> float:
        """Total kWh delivered by the charger over its lifetime (under our watch)."""
        return float(self._stored.get("charger_lifetime_energy_kwh", 0.0))

    async def _ev_charge_watchdog(
        self, cp, want_charging: bool, delivering: bool, now_ts: datetime,
    ) -> None:
        """Auto-heal a charger that won't deliver when charging is wanted (v0.40.5).

        If the controller wants charging but the charger isn't actually
        delivering power for a sustained period, escalate recovery instead of
        waiting for a manual replug/reboot:
          Stage 1 (>= EV_STUCK_RESYNC_SECONDS): TriggerMessage state re-sync.
          Stage 2 (>= EV_STUCK_RECOVER_SECONDS, rate-limited): cycle connector
                  availability — only for charger-side wedged states, never a
                  live Charging session or a car-side SuspendedEV.
        """
        if not want_charging or delivering:
            self._ev_stuck_since_ts = None
            return
        if self._ev_stuck_since_ts is None:
            self._ev_stuck_since_ts = now_ts
            return
        stuck_s = (now_ts - self._ev_stuck_since_ts).total_seconds()
        status = cp.status

        # Stage 1 — re-sync state (low risk), rate-limited.
        if stuck_s >= EV_STUCK_RESYNC_SECONDS and (
            self._ev_last_resync_ts is None
            or (now_ts - self._ev_last_resync_ts).total_seconds() >= EV_STUCK_RESYNC_SECONDS
        ):
            self._ev_last_resync_ts = now_ts
            cp.last_recovery_action = f"resync ({status}, {int(stuck_s)}s)"
            cp.last_recovery_ts = now_ts
            cp._log_event("watchdog", f"stage1 resync ({status}, {int(stuck_s)}s)")
            _LOGGER.warning(
                "EV watchdog: charger %s wanted charging but not delivering (%s) "
                "for %ds — re-syncing via TriggerMessage.",
                cp.id, status, int(stuck_s),
            )
            await cp.request_status_refresh()
            await cp.verify_applied_limit()  # v0.40.6 — log applied vs commanded

        # Stage 2 — connector availability cycle (conservative, rate-limited).
        # Only for charger-side wedged states; never a live Charging session or
        # a car-side SuspendedEV (cycling won't help and could be disruptive).
        if (
            stuck_s >= EV_STUCK_RECOVER_SECONDS
            and status in ("Preparing", "SuspendedEVSE", "Finishing")
            and (
                self._ev_last_recover_ts is None
                or (now_ts - self._ev_last_recover_ts).total_seconds()
                >= EV_STUCK_RECOVER_COOLDOWN_SECONDS
            )
        ):
            self._ev_last_recover_ts = now_ts
            cp.last_recovery_action = f"availability-cycle ({status}, {int(stuck_s)}s)"
            cp.last_recovery_ts = now_ts
            cp._log_event("watchdog", f"stage2 availability-cycle ({status}, {int(stuck_s)}s)")
            _LOGGER.warning(
                "EV watchdog: charger %s stuck in %s for %ds — cycling connector "
                "availability (Inoperative → Operative) to force a clean restart.",
                cp.id, status, int(stuck_s),
            )
            await cp.change_availability(False)
            await asyncio.sleep(3)
            await cp.change_availability(True)

    def get_charger_telemetry(self) -> dict:
        """Build a dict of OCPP charger fields for the result dict / sensors.

        Live ChargePoint instance values are primary. Persisted metadata
        from `_stored["charger_metadata"]` is used as fallback for empty
        fields (v0.27.3 — survives HA restarts so sensors don't go blank).
        """
        charger_id = self.config.get(CONF_EV_OCPP_CHARGE_POINT_ID, "")
        session_log = self._stored.get("charger_session_log", [])
        md = self._stored.get("charger_metadata", {}).get(charger_id, {})

        if (
            self.ocpp_server is None
            or not charger_id
            or charger_id not in self.ocpp_server.charge_points
        ):
            # No live ChargePoint — fall back to persisted snapshot if any
            return {
                "charger_status": "Disconnected" if md else "Unavailable",
                "charger_power_kw": 0.0,
                "charger_voltage_v": None,
                "charger_session_active": False,
                "charger_session_energy_kwh": 0.0,
                "charger_session_duration_min": 0.0,
                "charger_lifetime_energy_kwh": self.get_charger_lifetime_energy_kwh(),
                "charger_session_count": len(session_log),
                "charger_last_session": session_log[-1] if session_log else None,
                "charger_session_log_list": self.get_charger_session_log(20),
                "charger_session_solar_kwh": 0.0,
                "charger_session_grid_kwh": 0.0,
                "charger_vendor": md.get("vendor", ""),
                "charger_model": md.get("model", ""),
                "charger_firmware": md.get("firmware", ""),
                "charger_serial": md.get("serial", ""),
                "charger_seconds_since_seen": None,
                "charger_protocol_errors": 0,
                "charger_last_protocol_error": "",
                # v0.40.4 — command/telemetry observability
                "charger_transaction_id": None,
                "charger_commanded_amps": None,
                "charger_last_set_profile_status": None,
                "charger_last_set_profile_age_s": None,
                "charger_last_remote_start_status": None,
                "charger_last_remote_start_age_s": None,
                "charger_metervalues_age_s": None,
                "charger_stuck_seconds": 0.0,
                "charger_last_recovery_action": None,
                "charger_last_recovery_age_s": None,
                "charger_events": [],
            }
        cp = self.ocpp_server.charge_points[charger_id]
        now = datetime.now(timezone.utc)
        return {
            "charger_status": cp.effective_status(),
            "charger_power_kw": round(cp.power_w / 1000.0, 3),
            "charger_voltage_v": cp.voltage_v,
            "charger_session_active": cp.session_active,
            "charger_session_energy_kwh": round(cp.session_energy_wh / 1000.0, 3),
            "charger_session_duration_min": round(cp.session_duration_min(), 1),
            "charger_lifetime_energy_kwh": self.get_charger_lifetime_energy_kwh(),
            "charger_session_count": len(session_log),
            "charger_last_session": session_log[-1] if session_log else None,
            # v0.28.4: expose last 20 sessions newest-first for the Logs tab
            "charger_session_log_list": self.get_charger_session_log(20),
            # Live in-progress split (visible during charging on EV tab)
            "charger_session_solar_kwh": round(cp.session_solar_wh / 1000.0, 3),
            "charger_session_grid_kwh": round(cp.session_grid_wh / 1000.0, 3),
            # Live cp fields with persisted-metadata fallback for empties
            "charger_vendor": cp.vendor or md.get("vendor", ""),
            "charger_model": cp.model or md.get("model", ""),
            "charger_firmware": cp.firmware or md.get("firmware", ""),
            "charger_serial": cp.serial or md.get("serial", ""),
            "charger_seconds_since_seen": round(cp.seconds_since_seen, 1),
            "charger_protocol_errors": cp.protocol_errors,
            "charger_last_protocol_error": cp.last_protocol_error,
            # v0.40.4 — command/telemetry observability (OCPP diagnostics sensor)
            "charger_transaction_id": cp.session_transaction_id,
            "charger_commanded_amps": cp.last_commanded_amps,
            "charger_last_set_profile_status": cp.last_set_profile_status,
            "charger_last_set_profile_age_s": (
                round((now - cp.last_set_profile_ts).total_seconds(), 1)
                if cp.last_set_profile_ts else None
            ),
            "charger_last_remote_start_status": cp.last_remote_start_status,
            "charger_last_remote_start_age_s": (
                round((now - cp.last_remote_start_ts).total_seconds(), 1)
                if cp.last_remote_start_ts else None
            ),
            "charger_metervalues_age_s": (
                round((now - cp.last_metervalues_ts).total_seconds(), 1)
                if cp.last_metervalues_ts else None
            ),
            # v0.40.5 — desync watchdog observability
            "charger_stuck_seconds": (
                round((now - self._ev_stuck_since_ts).total_seconds(), 1)
                if self._ev_stuck_since_ts else 0.0
            ),
            "charger_last_recovery_action": cp.last_recovery_action,
            "charger_last_recovery_age_s": (
                round((now - cp.last_recovery_ts).total_seconds(), 1)
                if cp.last_recovery_ts else None
            ),
            "charger_events": list(cp.events),  # v0.40.6 rolling event log
        }

    def _apply_ev_time_window(self, target_amps: int, *, probing: bool = False) -> int:
        """Time-based anti-flap (v0.26.0, narrowed in v0.27.4 to PV-only).

        Anti-flap windows are ONLY needed for `pv` mode — they exist to absorb
        cloud-flicker on the solar surplus signal. In any other mode
        (LOCKED, FULL, PV+battery) the target is deterministic and changes
        only via user action, so we should respond immediately.

        For PV mode: surplus must hold ≥ min for `start_window` seconds
        before charging starts, and < min for `stop_window` seconds before
        charging stops.

        v0.39.12 — `probing` kwarg (renamed semantically in v0.39.17 but
        kept as `probing` for backwards-compat with the call site). When
        a confidence signal is active — historically the v0.36.2 probe,
        now the v0.39.17 battery-full override — `_run_ev_controller`
        passes `probing=True` here to bypass the start_window. The
        confidence signal is the inverter explicitly reporting PV
        throttling (reg 49251) AND a Solar AI
        price-floor block is open. Forcing the EV to wait the full
        start_window (default 60 s) before starting creates a race with
        EV_CURTAILMENT_PROBE_SECONDS (also 60 s): the probe almost always
        expires before the start_window completes and the EV never starts,
        and the controller then enters its 15-minute probe cool-down. To
        break the race, `probing=True` bypasses start_window from IDLE.
        Stop-window and v0.39.11 entry-debounce are still applied (probe
        ends, surplus drops, normal stop sequence runs).
        """
        # v0.27.4: non-PV modes bypass time-windows entirely. Clear any
        # half-armed timers so they don't carry stale state if the user
        # switches back to PV later.
        # v0.36.0: uses effective mode so scheduled-resolved PV mode still
        # gets the anti-flap windows.
        if self._ev_effective_mode != EV_MODE_PV:
            self._ev_surplus_above_min_since_ts = None
            self._ev_surplus_below_min_since_ts = None
            self._ev_arm_drop_since_ts = None              # v0.38.5
            self._ev_cool_entry_ts = None                  # v0.39.11
            return target_amps
        # v0.75.4 — a mode change just landed (see set_ev_mode). One-shot
        # bypass of every anti-flap timer so the new mode's target applies
        # immediately instead of riding out a stop_window/start_window meant
        # for cloud-flicker, not a deliberate switch. Also applies to a
        # switch INTO pv mode specifically, which the branch above doesn't
        # cover (that one only fires for switches OUT of pv mode).
        if self._ev_mode_change_pending:
            self._ev_mode_change_pending = False
            self._ev_surplus_above_min_since_ts = None
            self._ev_surplus_below_min_since_ts = None
            self._ev_arm_drop_since_ts = None
            self._ev_cool_entry_ts = None
            return target_amps
        now = datetime.now()
        start_window = int(self.config.get(
            CONF_EV_START_WINDOW_SECONDS, DEFAULT_EV_START_WINDOW_SECONDS,
        ))
        stop_window = int(self.config.get(
            CONF_EV_STOP_WINDOW_SECONDS, DEFAULT_EV_STOP_WINDOW_SECONDS,
        ))
        # v0.40.7 — during the COOLING hold (surplus < min, waiting out the
        # stop-window) charge at the *minimum* rate, not the last-commanded
        # rate. In PV mode the deficit is covered by battery/grid, so holding
        # the higher last rate (e.g. 8 A) needlessly drains the battery; drop
        # to the floor so as little non-solar power as possible is used.
        min_amps = self._kw_to_amps(
            float(self._stored.get("ev_min_charge_kw", DEFAULT_EV_MIN_CHARGE_KW))
        )

        if target_amps == 0:
            # Want to stop ── arm the stop timer when currently charging
            if self._ev_last_amps > 0:
                # v0.39.11 — entry debounce. Before setting
                # `_ev_surplus_below_min_since_ts` (which flips the
                # state name to COOLING), require EV_COOL_ENTRY_SECONDS
                # of sustained below-min. This dampens the cosmetic
                # flap when surplus oscillates by 50-100 W around the
                # min threshold under variable cloud cover. The EV
                # keeps drawing during the debounce — only the state
                # name (and the stop timer) is delayed.
                if self._ev_surplus_below_min_since_ts is None:
                    if self._ev_cool_entry_ts is None:
                        self._ev_cool_entry_ts = now
                    elapsed_entry = (now - self._ev_cool_entry_ts).total_seconds()
                    if elapsed_entry < EV_COOL_ENTRY_SECONDS:
                        # Still in entry debounce — stay CHARGING, but ease to min.
                        self._ev_surplus_above_min_since_ts = None
                        self._ev_arm_drop_since_ts = None
                        return min(self._ev_last_amps, min_amps)
                    # Sustained below-min — formally enter COOLING.
                    self._ev_surplus_below_min_since_ts = now
                    self._ev_cool_entry_ts = None
                self._ev_surplus_above_min_since_ts = None  # reset start timer
                self._ev_arm_drop_since_ts = None          # not in ARMING path
                elapsed = (now - self._ev_surplus_below_min_since_ts).total_seconds()
                if elapsed >= stop_window:
                    self._ev_surplus_below_min_since_ts = None
                    return 0                              # confirmed stop
                return min(self._ev_last_amps, min_amps)   # hold at minimum until confirmed
            # IDLE AND target dropped to 0.
            # v0.28.5: stale ARMING timestamps render as "Starter om -178s"
            # on the dashboard. Need to clear them.
            # v0.38.5: but a SINGLE TICK of surplus dipping below min should
            # NOT immediately nuke a partially-accumulated start timer. On
            # borderline surplus (e.g. cloudy 4.0 kW with noise), the start
            # timer would reset every few ticks and the EV would never
            # start even though average surplus exceeded min. Require
            # sustained below-min for EV_START_DROP_TIMEOUT_SECONDS before
            # clearing the start timer — mirror of the v0.38.3 stop-recovery
            # logic.
            if self._ev_surplus_above_min_since_ts is not None:
                # Start timer was running. Track how long this drop has lasted.
                if self._ev_arm_drop_since_ts is None:
                    self._ev_arm_drop_since_ts = now
                elapsed_below = (now - self._ev_arm_drop_since_ts).total_seconds()
                if elapsed_below < EV_START_DROP_TIMEOUT_SECONDS:
                    # Brief blip — keep start timer accumulating.
                    return 0
                # Sustained drop — clear the start timer for real.
                self._ev_surplus_above_min_since_ts = None
            self._ev_arm_drop_since_ts = None
            return 0

        # Want to charge ── arm the start timer when currently idle
        if self._ev_last_amps == 0:
            # v0.39.12 — curtailment probe bypass. See docstring.
            if probing:
                self._ev_surplus_above_min_since_ts = None
                self._ev_surplus_below_min_since_ts = None
                self._ev_arm_drop_since_ts = None
                self._ev_cool_entry_ts = None
                return target_amps
            if self._ev_surplus_above_min_since_ts is None:
                self._ev_surplus_above_min_since_ts = now
            self._ev_surplus_below_min_since_ts = None     # reset stop timer
            self._ev_arm_drop_since_ts = None              # v0.38.5: recovered from any blip-below
            self._ev_cool_entry_ts = None                  # v0.39.11
            elapsed = (now - self._ev_surplus_above_min_since_ts).total_seconds()
            if elapsed >= start_window:
                self._ev_surplus_above_min_since_ts = None
                return target_amps                         # confirmed start
            return 0                                       # not enough sustained surplus yet

        # Already charging — two sub-cases.
        if self._ev_surplus_below_min_since_ts is not None:
            # v0.38.3 — We're in COOLING (stop pending). A momentary blip of
            # surplus above min should NOT reset the stop timer — that's the
            # cause of the "stuck in COOLING for 30 minutes while the charger
            # keeps drawing" symptom. Require EV_STOP_RECOVERY_SECONDS of
            # sustained recovery before clearing the stop timer.
            if self._ev_surplus_above_min_since_ts is None:
                self._ev_surplus_above_min_since_ts = now
            elapsed_above = (now - self._ev_surplus_above_min_since_ts).total_seconds()
            if elapsed_above < EV_STOP_RECOVERY_SECONDS:
                # Brief blip — keep the stop timer running, hold at minimum.
                return min(self._ev_last_amps, min_amps)
            # Sustained recovery — surplus has held above min long enough.
            self._ev_surplus_above_min_since_ts = None
            self._ev_surplus_below_min_since_ts = None
            self._ev_cool_entry_ts = None                  # v0.39.11
            return target_amps

        # Already charging, no pending stop — normal live ramp.
        self._ev_surplus_above_min_since_ts = None
        self._ev_surplus_below_min_since_ts = None
        self._ev_cool_entry_ts = None                      # v0.39.11
        return target_amps

    async def _set_ocpp_charge_rate(self, charger_id: str, amps: int, force: bool = False) -> None:
        """Send the target current to the charger.

        Routes through Solar AI's embedded OCPP server if the embedded toggle
        is on (v0.27.0+ default), else falls back to the legacy lbbrhzn/ocpp
        HA service for users who haven't migrated.

        `force=True` re-asserts the limit even if it matches the last
        commanded value (used by the periodic re-assert below).
        """
        use_embedded = self.config.get(CONF_OCPP_EMBEDDED, True)
        if use_embedded and self.ocpp_server is not None:
            cp = self.ocpp_server.get(charger_id)
            if cp is None:
                _LOGGER.debug(
                    "Embedded OCPP: charger %s not connected — skipping write",
                    charger_id,
                )
                return
            ok = await cp.set_current(amps, force=force)
            if ok:
                _LOGGER.info(
                    "EV controller: set %s to %d A (%.1f kW target)",
                    charger_id, amps, amps * EV_VOLTAGE * EV_PHASES / 1000.0,
                )
            return
        # Legacy path: call lbbrhzn/ocpp's service
        try:
            await self.hass.services.async_call(
                "ocpp", "set_charge_rate",
                {"devid": charger_id, "limit_amps": amps},
                blocking=False,
            )
            _LOGGER.info(
                "EV controller (legacy ocpp service): set %s to %d A (%.1f kW)",
                charger_id, amps, amps * EV_VOLTAGE * EV_PHASES / 1000.0,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Legacy OCPP set_charge_rate failed for %s: %s", charger_id, err)

    def _resolve_ocpp_entity(
        self, charger_id: str, override_key: str, default_suffix: str,
    ) -> str:
        """Pick the OCPP entity to read for a given purpose.

        Priority: user-set override (if the entity actually exists), else
        auto-derive `sensor.<charger_id-lowercase><default_suffix>`.

        Self-healing: if the configured override points to an entity that
        doesn't exist in HA's state registry (stale value left over from a
        previous CPID, for example), the override is silently ignored and
        we fall back to the auto-derived name.  This avoids requiring the
        user to manually clear the override fields after changing CPID —
        v0.26.x OptionsFlow has a known UX bug where empty fields don't get
        persisted as deletions; this self-heal makes that bug harmless.
        """
        override = self.config.get(override_key)
        if override:
            if self.hass.states.get(override) is not None:
                return override          # override exists — use it
            # Override points at a non-existent entity (probably a stale
            # auto-derived value from a previous CPID). Ignore it.
            _LOGGER.debug(
                "OCPP override %s = %r not in HA registry — auto-deriving",
                override_key, override,
            )
        return f"sensor.{charger_id.lower()}{default_suffix}"

    def _get_ocpp_status(self, charger_id: str) -> str:
        """Get the current OCPP status for the configured charger.

        v0.27.0+: reads from Solar AI's embedded OCPP server (in-memory state
        on the ChargePoint instance). Falls back to the legacy
        `sensor.<cpid>_status` HA entity lookup if the embedded server is
        off (for users still running lbbrhzn/ocpp alongside).
        """
        use_embedded = self.config.get(CONF_OCPP_EMBEDDED, True)
        if use_embedded and self.ocpp_server is not None:
            cp = self.ocpp_server.get(charger_id)
            if cp is None:
                return "Unavailable"
            return cp.effective_status()
        # Legacy: read HA entity owned by lbbrhzn/ocpp
        eid = self._resolve_ocpp_entity(
            charger_id, CONF_EV_OCPP_STATUS_ENTITY, "_status",
        )
        state = self.hass.states.get(eid)
        return state.state if state and state.state not in ("unknown", "unavailable") else "Unavailable"

    def _get_ocpp_power_kw(self, charger_id: str) -> float:
        """Get the live charge power for the configured charger (kW).

        v0.27.0+: reads from the embedded OCPP server's MeterValues stream.
        Falls back to the legacy HA entity for non-embedded setups.
        """
        use_embedded = self.config.get(CONF_OCPP_EMBEDDED, True)
        if use_embedded and self.ocpp_server is not None:
            cp = self.ocpp_server.get(charger_id)
            if cp is None:
                return 0.0
            return cp.power_w / 1000.0
        # Legacy: read HA entity owned by lbbrhzn/ocpp
        eid = self._resolve_ocpp_entity(
            charger_id, CONF_EV_OCPP_POWER_ENTITY, "_power_active_import",
        )
        return self._get_float_state(eid, 0.0) / 1000.0

    def _ev_telemetry(
        self, target_kw: float, target_amps: int, surplus_kw: float, reason: str,
    ) -> dict:
        """Build the telemetry dict consumed by the visibility sensors.

        Includes the time-based anti-flap state (v0.26.0):
          - ev_state                  IDLE | ARMING | CHARGING | COOLING
          - ev_arming_seconds_left    seconds remaining until a start fires (0 if not arming)
          - ev_cooling_seconds_left   seconds remaining until a stop fires (0 if not cooling)
        Dashboard can render these as "PV: starter om 23 sek" / "stopper om 142 sek".
        """
        now = datetime.now()
        start_window = int(self.config.get(
            CONF_EV_START_WINDOW_SECONDS, DEFAULT_EV_START_WINDOW_SECONDS,
        ))
        stop_window = int(self.config.get(
            CONF_EV_STOP_WINDOW_SECONDS, DEFAULT_EV_STOP_WINDOW_SECONDS,
        ))
        arming_left = 0
        cooling_left = 0
        # v0.28.1: expose ISO timestamps for the dashboard to render a LIVE
        # per-second countdown. Static `*_seconds_left` only refreshes on
        # each coordinator tick (every 30 s by default), so the dashboard
        # number would jump in 30-s steps. With a fixed target timestamp
        # the dashboard can subtract `now()` every second.
        arming_until_iso = None
        cooling_until_iso = None
        # ARMING/COOLING only meaningful in PV mode where the time-windows apply (v0.27.4)
        # v0.36.0: uses effective mode so scheduled-PV also gets the countdown
        in_pv = (self._ev_effective_mode == EV_MODE_PV)
        if self._ev_last_amps > 0:
            state = "CHARGING"
            if in_pv and self._ev_surplus_below_min_since_ts is not None:
                state = "COOLING"
                elapsed = (now - self._ev_surplus_below_min_since_ts).total_seconds()
                cooling_left = max(0, int(stop_window - elapsed))
                cooling_until_iso = (
                    self._ev_surplus_below_min_since_ts
                    + timedelta(seconds=stop_window)
                ).isoformat()
        else:
            state = "IDLE"
            if in_pv and self._ev_surplus_above_min_since_ts is not None:
                state = "ARMING"
                elapsed = (now - self._ev_surplus_above_min_since_ts).total_seconds()
                arming_left = max(0, int(start_window - elapsed))
                arming_until_iso = (
                    self._ev_surplus_above_min_since_ts
                    + timedelta(seconds=start_window)
                ).isoformat()
        return {
            "ev_enabled": True,
            "ev_active_mode": self._ev_active_mode,
            # v0.36.0 — when ev_active_mode is "scheduled", these expose
            # the concrete mode currently in effect and which schedule
            # entity is driving it. For non-scheduled modes effective ==
            # active and active_schedule_link is None.
            "ev_effective_mode": self._ev_effective_mode,
            "ev_active_schedule_link": self._ev_active_schedule_link,
            "ev_target_kw": round(target_kw, 2),
            "ev_target_amps": target_amps,
            "ev_surplus_kw": round(surplus_kw, 2),
            "ev_reason": reason,
            "ev_last_commanded_amps": self._ev_last_amps,
            "ev_state": state,
            "ev_arming_seconds_left": arming_left,
            "ev_cooling_seconds_left": cooling_left,
            "ev_arming_until": arming_until_iso,
            "ev_cooling_until": cooling_until_iso,
            "ev_battery_locked": self._ev_battery_locked,
        }

    def _resolve_effective_ev_mode(self, requested_mode: str) -> tuple[str, str | None]:
        """Resolve `requested_mode` into a concrete operating mode.

        For LOCKED / PV / PV_BATTERY / FULL the requested mode IS the
        effective mode — returned unchanged.

        For SCHEDULED (v0.38.0 — native schedules) the resolver walks
        `_stored["ev_schedules"]` in slot-order and returns the first
        enabled slot whose `days` include today AND whose `[start, end)`
        window contains the current local time. End-before-start is
        handled as midnight-wrap. If no slot matches, falls back to the
        user-configured fallback mode (default `locked`).

        Schedules are owned entirely by Solar AI and edited from the
        dashboard — no HA `schedule.*` helper involvement (v0.36.0
        Phase A link-based design replaced).
        """
        if requested_mode != EV_MODE_SCHEDULED:
            return requested_mode, None

        slots = self._stored.get("ev_schedules", []) or []
        if slots:
            from datetime import time as _time, timedelta as _td   # noqa: PLC0415
            try:
                from homeassistant.util import dt as dt_util       # noqa: PLC0415
                now_local = dt_util.now()
            except Exception:                                      # noqa: BLE001
                now_local = datetime.now()                         # naive local fallback

            cur_t = now_local.time()
            weekday_today = EV_SCHEDULE_DAYS[now_local.weekday()]
            weekday_yesterday = EV_SCHEDULE_DAYS[(now_local.weekday() - 1) % 7]

            def _parse(s: str) -> "_time | None":
                try:
                    parts = (s or "").split(":")
                    return _time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
                except (ValueError, IndexError):
                    return None

            for slot in slots:
                if not isinstance(slot, dict) or not slot.get("enabled"):
                    continue
                mode = slot.get("mode") or ""
                if mode not in (EV_MODE_PV, EV_MODE_PV_BATTERY, EV_MODE_FULL):
                    continue
                days = slot.get("days") or []
                if not days:
                    continue
                start_t = _parse(slot.get("start"))
                end_t = _parse(slot.get("end"))
                if start_t is None or end_t is None:
                    continue
                slot_num = slot.get("slot", "?")
                label = f"Skema {slot_num}"

                if start_t == end_t:
                    # Degenerate "always on" — treat as covering all 24 h
                    if weekday_today in days:
                        return mode, label
                    continue

                if start_t < end_t:
                    # Same-day window
                    if weekday_today in days and start_t <= cur_t < end_t:
                        return mode, label
                else:
                    # Midnight wrap — slot spans (start..midnight..end)
                    if weekday_today in days and cur_t >= start_t:
                        return mode, label
                    if weekday_yesterday in days and cur_t < end_t:
                        return mode, label

        # No slot matched — use fallback
        fallback = self.config.get(
            CONF_EV_SCHEDULED_FALLBACK_MODE, DEFAULT_EV_SCHEDULED_FALLBACK_MODE,
        )
        if fallback not in (EV_MODE_LOCKED, EV_MODE_PV, EV_MODE_PV_BATTERY, EV_MODE_FULL):
            fallback = EV_MODE_LOCKED
        return fallback, None

    def set_schedule_link_mode(self, slot_idx: int, new_mode: str) -> None:
        """Public setter used by the per-slot dashboard select entities (v0.37.0).

        Writes the user's choice to `_stored[f"ev_schedule_link_{idx}_mode"]`
        so `_resolve_effective_ev_mode` picks it up on the next tick — no
        OptionsFlow trip required. Persisted to disk so it survives restart.
        """
        if new_mode not in EV_SCHEDULE_LINK_MODE_OPTIONS:
            _LOGGER.warning(
                "Schedule link %d: unknown mode '%s' ignored", slot_idx, new_mode,
            )
            return
        if not (1 <= slot_idx <= EV_SCHEDULE_LINKS_MAX):
            _LOGGER.warning(
                "Schedule link slot %d out of range (1..%d)",
                slot_idx, EV_SCHEDULE_LINKS_MAX,
            )
            return
        key = f"{EV_SCHEDULE_LINK_MODE_STORAGE_PREFIX}{slot_idx}_mode"
        self._stored[key] = new_mode
        if self.hass:
            self.hass.async_create_task(self._store.async_save(self._stored))

    # v0.38.0 — native-schedule mutators. These are the only blessed paths
    # for editing `_stored["ev_schedules"]`. Dashboard cards bind directly
    # to entities (mode select / enabled switch / start+end time) that
    # call these, or to `battery_arbitrage.*` services that wrap them.
    # All mutators persist asynchronously and notify listeners so platform
    # entities re-render.

    def get_schedule_slot(self, slot_idx: int) -> dict | None:
        """Return a copy of the slot dict or None."""
        slots = self._stored.get("ev_schedules") or []
        for s in slots:
            if isinstance(s, dict) and s.get("slot") == slot_idx:
                return dict(s)
        return None

    def _get_or_create_slot(self, slot_idx: int) -> dict:
        """Return the live slot dict; create a default if absent."""
        slots: list = self._stored.setdefault("ev_schedules", [])
        for s in slots:
            if isinstance(s, dict) and s.get("slot") == slot_idx:
                return s
        new_slot = {
            "slot": slot_idx,
            "enabled": False,
            "mode": EV_SCHEDULE_DEFAULT_MODE,
            "name": f"Skema {slot_idx}",
            "start": EV_SCHEDULE_DEFAULT_START,
            "end": EV_SCHEDULE_DEFAULT_END,
            "days": list(EV_SCHEDULE_DEFAULT_DAYS),
        }
        slots.append(new_slot)
        # Keep stable slot order
        slots.sort(key=lambda x: (x.get("slot") if isinstance(x, dict) else 99))
        return new_slot

    def _persist_schedules(self) -> None:
        """Async-save the storage; called after every schedule mutation."""
        if self.hass:
            self.hass.async_create_task(self._store.async_save(self._stored))

    def set_schedule_slot_mode(self, slot_idx: int, new_mode: str) -> None:
        if new_mode not in (EV_MODE_PV, EV_MODE_PV_BATTERY, EV_MODE_FULL):
            _LOGGER.warning("set_schedule_slot_mode: bad mode '%s'", new_mode); return
        if not (1 <= slot_idx <= EV_SCHEDULES_MAX): return
        slot = self._get_or_create_slot(slot_idx)
        slot["mode"] = new_mode
        self._persist_schedules()

    def set_schedule_slot_enabled(self, slot_idx: int, enabled: bool) -> None:
        if not (1 <= slot_idx <= EV_SCHEDULES_MAX): return
        slot = self._get_or_create_slot(slot_idx)
        slot["enabled"] = bool(enabled)
        self._persist_schedules()

    def set_schedule_slot_time(self, slot_idx: int, which: str, hhmm: str) -> None:
        """Update start or end time. `which` is 'start' or 'end'. `hhmm` is HH:MM[:SS]."""
        if which not in ("start", "end"): return
        if not (1 <= slot_idx <= EV_SCHEDULES_MAX): return
        # Normalise to HH:MM (drop seconds if present)
        normalised = (hhmm or "")[:5]
        if len(normalised) != 5 or normalised[2] != ":":
            _LOGGER.warning("set_schedule_slot_time: bad time '%s'", hhmm); return
        try:
            h = int(normalised[:2]); m = int(normalised[3:])
            assert 0 <= h <= 23 and 0 <= m <= 59
        except (ValueError, AssertionError):
            _LOGGER.warning("set_schedule_slot_time: out-of-range '%s'", hhmm); return
        slot = self._get_or_create_slot(slot_idx)
        slot[which] = normalised
        self._persist_schedules()

    def toggle_schedule_slot_day(self, slot_idx: int, day: str) -> None:
        if day not in EV_SCHEDULE_DAYS: return
        if not (1 <= slot_idx <= EV_SCHEDULES_MAX): return
        slot = self._get_or_create_slot(slot_idx)
        days: list = slot.setdefault("days", [])
        if day in days:
            days.remove(day)
        else:
            days.append(day)
            # Keep canonical order
            days.sort(key=EV_SCHEDULE_DAYS.index)
        self._persist_schedules()

    def set_schedule_slot_day(self, slot_idx: int, day: str, present: bool) -> None:
        """Add or remove a single weekday from a slot (for the GUI day toggles).

        Unlike toggle_schedule_slot_day this sets an explicit on/off state, so
        a switch turning on/off lands deterministically regardless of the
        current membership.
        """
        if day not in EV_SCHEDULE_DAYS:
            return
        if not (1 <= slot_idx <= EV_SCHEDULES_MAX):
            return
        slot = self._get_or_create_slot(slot_idx)
        days: list = slot.setdefault("days", [])
        if present and day not in days:
            days.append(day)
            days.sort(key=EV_SCHEDULE_DAYS.index)
        elif not present and day in days:
            days.remove(day)
        self._persist_schedules()

    def set_schedule_slot_days(self, slot_idx: int, days: list[str]) -> None:
        if not (1 <= slot_idx <= EV_SCHEDULES_MAX): return
        clean = [d for d in (days or []) if d in EV_SCHEDULE_DAYS]
        clean.sort(key=EV_SCHEDULE_DAYS.index)
        slot = self._get_or_create_slot(slot_idx)
        slot["days"] = clean
        self._persist_schedules()

    def delete_schedule_slot(self, slot_idx: int) -> None:
        """Remove a slot's entry entirely. The slot's entities stay (always-created)
        but report as 'empty' until the slot is added again."""
        if not (1 <= slot_idx <= EV_SCHEDULES_MAX): return
        slots = self._stored.get("ev_schedules") or []
        new = [s for s in slots if not (isinstance(s, dict) and s.get("slot") == slot_idx)]
        self._stored["ev_schedules"] = new
        self._persist_schedules()

    def add_schedule_slot_native(self) -> int | None:
        """Allocate the lowest unused slot index (1..MAX) and seed it with
        the default schedule. Returns the slot index or None if full."""
        slots = self._stored.setdefault("ev_schedules", [])
        used = {s.get("slot") for s in slots if isinstance(s, dict)}
        for i in range(1, EV_SCHEDULES_MAX + 1):
            if i not in used:
                self._get_or_create_slot(i)
                self._persist_schedules()
                return i
        return None

    def set_ev_mode(self, new_mode: str, *, _from_auto_full: bool = False) -> None:
        """Public setter used by the mode select entity.

        v0.39.0 — `_from_auto_full=True` is set when the negative-price
        auto-promotion calls this setter, so we can distinguish that path
        from a user-triggered mode change. A user-triggered change while
        auto-Full is active clears the auto state — the user's choice wins.
        """
        if new_mode not in (EV_MODE_LOCKED, EV_MODE_PV, EV_MODE_PV_BATTERY, EV_MODE_FULL, EV_MODE_SCHEDULED):
            _LOGGER.warning("EV controller: unknown mode '%s' ignored", new_mode)
            return
        # v0.39.0 — user manually changed the mode while auto-Full was
        # active. Clear the auto state. The next negative-price event
        # will start fresh.
        if not _from_auto_full and self._ev_auto_full_active_since_ts is not None:
            _LOGGER.info(
                "EV controller: auto-Full state cleared because user "
                "manually changed master mode (%s → %s).",
                self._ev_active_mode, new_mode,
            )
            self._ev_auto_full_active_since_ts = None
            self._ev_pre_auto_full_mode = None
        # v0.75.4 — flag an actual change so the next control tick bypasses
        # the anti-flap windows instead of holding the old rate for up to a
        # full stop_window. Applies whether the change is manual or the
        # auto-full negative-price promotion/revert — both are deliberate
        # transitions, not surplus noise.
        if new_mode != self._ev_active_mode:
            self._ev_mode_change_pending = True
        self._ev_active_mode = new_mode
        self._stored["ev_active_mode"] = new_mode
        # Reset hysteresis state so the new mode takes effect on the next loop iteration
        self._ev_above_start_count = 0
        self._ev_below_stop_count = 0
        self._ev_surplus_above_min_since_ts = None
        self._ev_surplus_below_min_since_ts = None
        # Persist asynchronously
        if self.hass:
            self.hass.async_create_task(self._store.async_save(self._stored))

    async def _maybe_auto_full_negative_price(
        self, now_local: datetime, buy_price_now: float,
    ) -> None:
        """v0.39.0 — Promote EV mode to Full during negative-price periods
        and revert when the price-floor block closes.

        Behaviour
        ---------
        - Opt-in via `auto_full_on_negative_price` storage flag (the switch
          entity). Default OFF.
        - Promotion gate: switch ON + EV plugged + master mode != Full +
          buy_price ≤ 0 sustained for AUTO_FULL_DEBOUNCE_SECONDS.
        - Revert gate: floor block transitions from active to inactive.
        - Pre-promotion mode is stashed and restored on revert. Manual
          mode changes clear the auto state (see `set_ev_mode`).
        - EV unplug clears the auto state and the debounce timestamp.

        This logic is the only place that flips master mode automatically.
        """
        enabled = bool(self._stored.get(
            "auto_full_on_negative_price",
            self.config.get(CONF_AUTO_FULL_ON_NEGATIVE_PRICE,
                            DEFAULT_AUTO_FULL_ON_NEGATIVE_PRICE),
        ))
        if not enabled:
            # Feature off — clear any lingering state but otherwise no-op.
            if self._ev_auto_full_active_since_ts is not None:
                self._ev_auto_full_active_since_ts = None
                self._ev_pre_auto_full_mode = None
            self._ev_neg_price_seen_since_ts = None
            self._ev_prev_floor_block_active = self._current_floor_block is not None
            return

        # EV plug state — read same way as the EV controller.
        charger_id = self.config.get(CONF_EV_OCPP_CHARGE_POINT_ID, "")
        ev_connected = False
        if charger_id:
            try:
                status = self._get_ocpp_status(charger_id)
                ev_connected = status in (
                    "Preparing", "Charging", "SuspendedEV",
                    "SuspendedEVSE", "Finishing",
                )
            except Exception:  # noqa: BLE001
                ev_connected = False
        if not ev_connected:
            # Clear all auto state on disconnect — next plug-in starts clean.
            if (self._ev_auto_full_active_since_ts is not None
                    or self._ev_neg_price_seen_since_ts is not None):
                _LOGGER.info(
                    "Auto-Full: EV disconnected — clearing auto state.",
                )
            self._ev_auto_full_active_since_ts = None
            self._ev_pre_auto_full_mode = None
            self._ev_neg_price_seen_since_ts = None
            self._ev_prev_floor_block_active = self._current_floor_block is not None
            return

        floor_active = self._current_floor_block is not None

        # ---- Revert edge: floor was active last tick, inactive this tick ----
        if (self._ev_prev_floor_block_active and not floor_active
                and self._ev_auto_full_active_since_ts is not None):
            restore_mode = self._ev_pre_auto_full_mode or EV_MODE_PV
            _LOGGER.info(
                "Auto-Full: price-floor block closed — restoring master "
                "mode to %s (had been auto-promoted from %s to Full at %s).",
                restore_mode, self._ev_pre_auto_full_mode,
                self._ev_auto_full_active_since_ts.isoformat(timespec="seconds"),
            )
            self._ev_auto_full_active_since_ts = None
            self._ev_pre_auto_full_mode = None
            self.set_ev_mode(restore_mode, _from_auto_full=True)
            # Don't return — still update prev_floor + maybe re-promote.

        self._ev_prev_floor_block_active = floor_active

        # ---- Promotion gate ----
        # Track sustained-below-zero on the buy price.
        try:
            buy_price = float(buy_price_now)
        except (TypeError, ValueError):
            buy_price = 0.001   # treat non-numeric as positive — no promotion
        if buy_price <= 0.0:
            if self._ev_neg_price_seen_since_ts is None:
                self._ev_neg_price_seen_since_ts = now_local
        else:
            self._ev_neg_price_seen_since_ts = None

        if self._ev_auto_full_active_since_ts is not None:
            return   # already promoted, nothing to do
        if self._ev_neg_price_seen_since_ts is None:
            return   # buy price not currently negative
        if self._ev_active_mode == EV_MODE_FULL:
            return   # user already in Full — no promotion needed
        elapsed = (now_local - self._ev_neg_price_seen_since_ts).total_seconds()
        if elapsed < AUTO_FULL_DEBOUNCE_SECONDS:
            return   # not sustained long enough

        # All gates passed — promote.
        prev_mode = self._ev_active_mode
        self._ev_pre_auto_full_mode = prev_mode
        self._ev_auto_full_active_since_ts = now_local
        _LOGGER.info(
            "Auto-Full: buy_price=%.4f DKK/kWh has been ≤ 0 for %.0fs "
            "(threshold %ds) — promoting master mode %s → Full. Will "
            "auto-revert to %s when the price-floor block closes.",
            buy_price, elapsed, AUTO_FULL_DEBOUNCE_SECONDS,
            prev_mode, prev_mode,
        )
        self.set_ev_mode(EV_MODE_FULL, _from_auto_full=True)

    # ------------------------------------------------------------------ #
    # Decoupled EV control loop (v0.26.0)                                   #
    # ------------------------------------------------------------------ #

    async def async_start_ev_control_loop(self) -> None:
        """Start the background EV control task if not already running."""
        if self._ev_control_task is not None and not self._ev_control_task.done():
            return
        # Use a *background* task so HA doesn't wait on it during the startup
        # phase (otherwise this infinite loop trips the bootstrap timeout — see
        # `Something is blocking Home Assistant from wrapping up the start up
        # phase` warning in v0.26.0/v0.26.1).
        self._ev_control_task = self.hass.async_create_background_task(
            self._ev_control_loop(), name="solar_ai_ev_control_loop"
        )
        _LOGGER.info("EV control loop started (background task)")

    async def async_stop_ev_control_loop(self) -> None:
        """Cancel the background EV control task."""
        if self._ev_control_task is None or self._ev_control_task.done():
            return
        self._ev_control_task.cancel()
        try:
            await self._ev_control_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        finally:
            self._ev_control_task = None
            _LOGGER.info("EV control loop stopped")

    async def _ev_control_loop(self) -> None:
        """Background loop: re-evaluates the EV target at the configured cadence.

        Runs independently of the main coordinator fast-poll. Reads cached
        inputs (evcc_state, battery_soc, floor_soc) written by the main update;
        on each tick, computes a fresh decision via `_run_ev_controller` and
        publishes the result to `_latest_ev_telemetry` for the main update to
        merge into its result dict on its next pass.

        Loop interval, start window, and stop window are configurable. If the
        main update has not yet populated the cache, the iteration is a no-op.
        """
        _LOGGER.debug("EV control loop entering")
        while True:
            # Read via _setting so the dashboard "EV control interval" number
            # (stored override) applies on the next iteration without a reload.
            interval = int(self._setting(
                CONF_EV_CONTROL_INTERVAL_SECONDS,
                DEFAULT_EV_CONTROL_INTERVAL_SECONDS,
            ))
            # Clamp to a sane minimum so a bad config value can't spin the loop
            interval = max(5, min(interval, 300))
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                _LOGGER.debug("EV control loop cancelled")
                return
            try:
                cached = self._cached_ev_inputs
                if cached is None:
                    continue  # main update hasn't produced fresh inputs yet
                telemetry = await self._run_ev_controller(
                    evcc_state=cached["evcc_state"],
                    battery_soc=cached["battery_soc"],
                    floor_soc=cached["floor_soc"],
                )
                self._latest_ev_telemetry = telemetry
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception("EV control loop iteration failed: %s", err)

    # ------------------------------------------------------------------ #
    # Strømligning retailer pricing (v0.29.0)                              #
    # ------------------------------------------------------------------ #

    async def _maybe_refresh_stromligning_prices(
        self, session: aiohttp.ClientSession, now: datetime,
    ) -> None:
        """Refresh the Strømligning per-slot price cache if the mode is
        enabled and the cache is stale. No-op in manual mode.
        """
        if self._setting(CONF_BUY_PRICE_MODE, DEFAULT_BUY_PRICE_MODE) != BUY_PRICE_MODE_STROMLIGNING:
            return
        product_id = self._setting(CONF_STROMLIGNING_PRODUCT_ID, "")
        supplier_id = self._setting(CONF_STROMLIGNING_SUPPLIER_ID, "")
        if not product_id or not supplier_id:
            return
        # Cache freshness check (24 h by default)
        if (
            self._last_stromligning_refresh is not None
            and (now - self._last_stromligning_refresh).total_seconds()
                < STROMLIGNING_CACHE_HOURS * 3600
            and self._cached_stromligning_prices
        ):
            return

        # Derive price area from the DSO option, fall back to DK2
        price_area = "DK2"
        for opt in DSO_OPTIONS:
            if opt.get("stromligning") == supplier_id:
                price_area = opt.get("price_area") or "DK2"
                break

        customer_group = self.config.get(
            CONF_STROMLIGNING_CUSTOMER_GROUP, DEFAULT_STROMLIGNING_CUSTOMER_GROUP,
        )

        # Fetch a 48-hour window starting at the previous full hour
        from_dt = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        to_dt = from_dt + timedelta(hours=49)

        # Import here to avoid a hard module-load dependency for users who
        # never touch Strømligning mode
        from . import stromligning as sl

        prices = await sl.fetch_prices(
            session,
            product_id=product_id,
            supplier_id=supplier_id,
            customer_group_id=customer_group,
            price_area=price_area,
            from_dt=from_dt,
            to_dt=to_dt,
        )
        if prices is None:
            _LOGGER.warning(
                "Strømligning fetch returned None (product=%s, supplier=%s); "
                "keeping previous cache and falling back to manual stack",
                product_id, supplier_id,
            )
            return

        self._cached_stromligning_prices = prices
        self._last_stromligning_refresh = now
        # v0.59.4 — persist so a restart reuses these (and skips the daily
        # re-fetch while still fresh, which also avoids hammering the API).
        self._stored["stromligning_prices_cache"] = prices
        self._stored["stromligning_refresh_iso"] = now.isoformat()
        await self._store.async_save(self._stored)
        _LOGGER.debug(
            "Strømligning prices refreshed: %d slots for product=%s, supplier=%s, area=%s",
            len(prices), product_id, supplier_id, price_area,
        )

    def _stromligning_spot_forecast(self, now: datetime) -> dict:
        """Opt-in cross-source forecast fallback (v0.59.20).

        When EDS has no day-ahead data, derive an EDS-compatible spot-price
        forecast from the cached Strømligning prices — using their *spot*
        component (not the all-in total, which already bakes in tariffs + VAT) —
        so the price chart and the optimiser don't go blind during an EDS gap.

        Returns {"rates": [{"start": <utc-iso>, "value": <spot dkk/kwh>}, ...]}
        for still-future slots, or {} when the toggle is off, there's no
        Strømligning cache, or no usable future slots.
        """
        if not self._stored.get("price_cross_source_fallback", False):
            return {}
        cache = self._cached_stromligning_prices
        if not cache:
            return {}
        from . import stromligning as sl  # noqa: PLC0415
        cutoff = now - timedelta(minutes=15)
        rates: list[dict] = []
        for key, entry in cache.items():
            try:
                ts = datetime.strptime(key[:19], "%Y-%m-%dT%H:%M:%S").replace(
                    tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
            if ts < cutoff:
                continue
            try:
                spot = float(sl.get_price_details(entry)["spot"])
            except Exception:  # noqa: BLE001
                continue
            rates.append({"start": ts.isoformat(), "value": spot})
        rates.sort(key=lambda r: r["start"])
        return {"rates": rates} if rates else {}

    def _compute_buy_price(
        self,
        spot: float,
        hour: int,
        slot_start_dt: datetime | None = None,
        *,
        spot_markup: float,
        tariff_this_hour_dso: float,
        elafgift: float,
        vat_factor: float,
    ) -> float:
        """Compute the per-slot buy price.

        In manual mode (default) this is the classic stack:
            (spot + markup + DSO tariff + elafgift) × VAT
        In Strømligning mode it tries the cached per-slot all-in price for the
        matching timestamp, falling back to the manual stack when no Strømligning
        data is available for that slot.

        With override mode enabled, it recomposes the price using Strømligning's
        spot/distribution/transmission components but the user's markup,
        elafgift, and VAT.
        """
        mode = self._setting(CONF_BUY_PRICE_MODE, DEFAULT_BUY_PRICE_MODE)

        # ── Octopus Energy mode (v0.30.0, UK) ────────────────────────────
        if mode == BUY_PRICE_MODE_OCTOPUS and slot_start_dt is not None:
            # Octopus rates are keyed by `valid_from` ISO Z timestamps,
            # always at half-hour boundaries.
            slot_key = slot_start_dt.astimezone(timezone.utc).replace(
                minute=(slot_start_dt.minute // 30) * 30,
                second=0, microsecond=0,
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            entry = self._cached_octopus_prices.get(slot_key)
            if entry is None:
                # Try the half-hour-aligned alternate (Octopus uses :00 and :30)
                slot_key_alt = slot_start_dt.astimezone(timezone.utc).replace(
                    minute=0, second=0, microsecond=0,
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
                entry = self._cached_octopus_prices.get(slot_key_alt)
            if entry is not None:
                try:
                    # Octopus values are pence/kWh inc-VAT. Convert to
                    # currency-units/kWh (consistent with the rest of the
                    # integration which uses DKK/kWh by default; UK users
                    # set the currency to GBP in Configure).
                    return float(entry["value_inc_vat"]) / 100.0
                except (KeyError, TypeError, ValueError):
                    pass
            # Cache miss or parse failure → fall back to manual stack
            return (spot + spot_markup + tariff_this_hour_dso + elafgift) * vat_factor

        if mode != BUY_PRICE_MODE_STROMLIGNING or slot_start_dt is None:
            return (spot + spot_markup + tariff_this_hour_dso + elafgift) * vat_factor

        # Strømligning mode — lookup by 15-min aligned ISO timestamp.
        # Strømligning publishes 15-min slots; the cache key built in
        # `stromligning.fetch_prices` uses `(minute // 15) * 15`. v0.39.6
        # fixed an earlier bug where this lookup used hour-aligned keys
        # and silently received only the :45 quarter's price for every
        # intra-hour slot the optimizer queried. Hour-aligned fallback
        # covers products/dates where Strømligning returns hourly slots
        # (entries with `resolution: "1h"` land at minute=0 in the cache).
        slot_utc = slot_start_dt.astimezone(timezone.utc)
        slot_minute = (slot_utc.minute // 15) * 15
        slot_key = slot_utc.replace(
            minute=slot_minute, second=0, microsecond=0,
        ).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        entry = self._cached_stromligning_prices.get(slot_key)
        if entry is None and slot_minute != 0:
            # 15-min miss — try the hour-aligned key (handles hourly-resolution
            # entries from Strømligning).
            slot_key_h = slot_utc.replace(
                minute=0, second=0, microsecond=0,
            ).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            entry = self._cached_stromligning_prices.get(slot_key_h)
        if entry is None:
            # No matching slot — fall back to manual stack
            return (spot + spot_markup + tariff_this_hour_dso + elafgift) * vat_factor

        if not self.config.get(
            CONF_STROMLIGNING_USE_MANUAL_OVERRIDES, DEFAULT_STROMLIGNING_USE_MANUAL_OVERRIDES,
        ):
            # Pure Strømligning — return the all-in number directly.
            # v0.39.5: was entry["price"]["price"]["total"] (wrong nesting),
            # silently fell through to the manual stack on every lookup.
            try:
                return float(entry["price"]["total"])
            except (KeyError, TypeError, ValueError):
                return (spot + spot_markup + tariff_this_hour_dso + elafgift) * vat_factor

        # Override mode — recompose using Strømligning components + user overrides
        from . import stromligning as sl
        try:
            d = sl.get_price_details(entry)
        except Exception:  # noqa: BLE001
            return (spot + spot_markup + tariff_this_hour_dso + elafgift) * vat_factor
        ex_vat = (
            d["spot"]
            + spot_markup
            + d["net_tariff"]
            + d["system_tariff"]
            + d["distribution"]
            + elafgift
        )
        return ex_vat * vat_factor

    # ------------------------------------------------------------------ #
    # Octopus Energy retailer pricing (v0.30.0)                            #
    # ------------------------------------------------------------------ #

    async def _maybe_refresh_octopus_prices(
        self, session: aiohttp.ClientSession, now: datetime,
    ) -> None:
        """Refresh the Octopus per-half-hour price cache.

        Only runs when CONF_BUY_PRICE_MODE is "octopus" and both product
        code and region are configured. Cache freshness window matches the
        tariff refresh interval (24 h by default). Octopus publishes Agile
        prices for tomorrow around 16:00 UK time; the daily refresh window
        guarantees we have today + tomorrow.
        """
        if self._setting(CONF_BUY_PRICE_MODE, DEFAULT_BUY_PRICE_MODE) != BUY_PRICE_MODE_OCTOPUS:
            return
        product_code = self.config.get(CONF_OCTOPUS_PRODUCT_CODE, "")
        region = self.config.get(CONF_OCTOPUS_REGION, DEFAULT_OCTOPUS_REGION)
        if not product_code or not region:
            return
        if (
            self._last_octopus_refresh is not None
            and (now - self._last_octopus_refresh).total_seconds()
                < OCTOPUS_CACHE_HOURS * 3600
            and self._cached_octopus_prices
        ):
            return

        # Fetch a 49-hour window — yesterday's tail + today + tomorrow
        from_dt = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        to_dt = from_dt + timedelta(hours=49)

        from . import octopus as oc

        prices = await oc.fetch_prices(
            session,
            product_code=product_code,
            region=region,
            from_dt=from_dt,
            to_dt=to_dt,
        )
        if prices is None:
            _LOGGER.warning(
                "Octopus fetch returned None (product=%s, region=%s); "
                "keeping previous cache and falling back to manual stack",
                product_code, region,
            )
            return

        self._cached_octopus_prices = prices
        self._last_octopus_refresh = now
        _LOGGER.debug(
            "Octopus prices refreshed: %d slots for product=%s, region=%s",
            len(prices), product_code, region,
        )

    # ------------------------------------------------------------------ #
    # Live state source dispatcher (EVCC / Hybrid / FoxESS)                #
    # ------------------------------------------------------------------ #

    async def _fetch_live_state(
        self, session: aiohttp.ClientSession, evcc_url: str
    ) -> dict:
        """Return live grid / PV / load / EV state in EVCC /api/state shape.

        Three modes (CONF_LIVE_DATA_SOURCE):
          - "evcc"   — single GET /api/state, fatal on failure (no fallback)
          - "hybrid" — FoxESS for grid/PV/load; EVCC for EV loadpoints + batteryMode.
                       Soft-fails on EVCC unreachability (empties loadpoints, keeps going).
          - "foxess" — FoxESS only; no EVCC calls at all; empty loadpoints.
        """
        source = self._setting(CONF_LIVE_DATA_SOURCE, DEFAULT_LIVE_DATA_SOURCE)

        if source == LIVE_SOURCE_EVCC:
            try:
                return await self._fetch_json(session, f"{evcc_url}{EVCC_API_STATE}")
            except Exception as err:
                raise UpdateFailed(f"EVCC unreachable: {err}") from err

        # FoxESS-derived base — used by both hybrid and foxess modes
        base = self._read_foxess_live_state()

        if source == LIVE_SOURCE_FOXESS:
            # No EV info, no EVCC coordination
            base["loadpoints"] = []
            base["batteryMode"] = EVCC_BATTERY_NORMAL
            return base

        # Hybrid: enrich with EVCC loadpoints + batteryMode; soft-fail on EVCC error
        try:
            evcc_state = await self._fetch_json(session, f"{evcc_url}{EVCC_API_STATE}")
            base["loadpoints"] = evcc_state.get("loadpoints", []) or []
            base["batteryMode"] = evcc_state.get("batteryMode", EVCC_BATTERY_NORMAL)
        except Exception as err:
            _LOGGER.warning(
                "Hybrid mode: EVCC unreachable for EV info (%s) — "
                "continuing with FoxESS data and empty loadpoints", err,
            )
            base["loadpoints"] = []
            base["batteryMode"] = EVCC_BATTERY_NORMAL
        return base

    def _read_foxess_live_state(self) -> dict:
        """Construct an EVCC-style live-state dict from FoxESS Modbus sensors.

        Uses the direction-separated grid sensors so the conventional sign
        question (CT clamp orientation) is irrelevant:
            gridPower = grid_consumption − feed_in   (positive = import)
        Returned values are in watts to match the EVCC API.
        """
        grid_in_kw  = self._get_float_state(
            self.config.get(CONF_FOXESS_GRID_IMPORT_ENTITY, DEFAULT_FOXESS_GRID_IMPORT), 0.0,
        )
        grid_out_kw = self._get_float_state(
            self.config.get(CONF_FOXESS_GRID_EXPORT_ENTITY, DEFAULT_FOXESS_GRID_EXPORT), 0.0,
        )
        pv_kw       = self._get_float_state(
            self.config.get(CONF_FOXESS_PV_POWER_ENTITY, DEFAULT_FOXESS_PV_POWER), 0.0,
        )
        load_kw     = self._get_float_state(
            self.config.get(CONF_FOXESS_LOAD_POWER_ENTITY, DEFAULT_FOXESS_LOAD_POWER), 0.0,
        )
        # Sensors may be unavailable on first tick — _get_float_state returns 0.0
        # in that case so we don't crash the update.
        return {
            "homePower": (load_kw or 0.0) * 1000,
            "pvPower":   (pv_kw or 0.0) * 1000,
            "gridPower": ((grid_in_kw or 0.0) - (grid_out_kw or 0.0)) * 1000,
            "loadpoints": [],
            "batteryMode": EVCC_BATTERY_NORMAL,
        }

    # ------------------------------------------------------------------ #
    # Solar forecast source dispatcher                                    #
    # ------------------------------------------------------------------ #

    async def _fetch_solar_forecast(
        self, session: aiohttp.ClientSession, evcc_url: str
    ) -> dict:
        """Fetch the per-slot solar forecast based on the configured source.

        Returns a dict in EVCC-compatible format:
            {"rates": [{"start": "<utc-iso>", "value": <watts>}, ...]}

        Source values (CONF_SOLAR_FORECAST_SOURCE):
          - "evcc"           → EVCC /api/tariff/solar (default; Solcast underneath)
          - "forecast_solar" → user-picked Forecast.Solar HA entity's `watts` attribute
          - "solcast"        → user-picked Solcast HA integration entity's `detailedForecast`
          - "auto"           → try EVCC → Forecast.Solar → Solcast in order until one returns data
        """
        source = self._setting(CONF_SOLAR_FORECAST_SOURCE, DEFAULT_SOLAR_FORECAST_SOURCE)
        fs_entity = self.config.get(CONF_FORECAST_SOLAR_ENTITY)
        solcast_entity = self.config.get(CONF_SOLCAST_ENTITY)
        solcast_tomorrow_entity = self.config.get(CONF_SOLCAST_TOMORROW_ENTITY)

        async def try_evcc() -> dict:
            try:
                data = await self._fetch_json(session, f"{evcc_url}{EVCC_API_SOLAR}")
                return data if data and data.get("rates") else {}
            except Exception as err:
                _LOGGER.debug("EVCC solar fetch failed: %s", err)
                return {}

        def try_forecast_solar() -> dict:
            if not fs_entity:
                _LOGGER.debug("forecast_solar entity not configured")
                return {}
            return self._fetch_solar_from_forecast_solar(fs_entity)

        def try_solcast() -> dict:
            if not solcast_entity:
                _LOGGER.debug("solcast entity not configured")
                return {}
            # v0.28.0: combine today + tomorrow forecasts for a true 48-h
            # horizon. The optimizer can now plan across midnight when
            # tomorrow's Solcast data is available.
            today_data = self._fetch_solar_from_solcast(solcast_entity)
            today_rates = today_data.get("rates", [])
            if solcast_tomorrow_entity:
                tom_data = self._fetch_solar_from_solcast(solcast_tomorrow_entity)
                tom_rates = tom_data.get("rates", [])
                # De-duplicate by start timestamp (in case of overlap at midnight)
                seen = {r["start"] for r in today_rates}
                merged = today_rates + [r for r in tom_rates if r["start"] not in seen]
                merged.sort(key=lambda r: r["start"])
                _LOGGER.debug(
                    "solcast: merged today (%d slots) + tomorrow (%d new slots) = %d total",
                    len(today_rates), len(merged) - len(today_rates), len(merged),
                )
                return {"rates": merged} if merged else {}
            return today_data

        if source == SOLAR_SOURCE_EVCC:
            return await try_evcc()

        if source == SOLAR_SOURCE_FORECAST_SOLAR:
            return try_forecast_solar()

        if source == SOLAR_SOURCE_SOLCAST:
            return try_solcast()

        if source == SOLAR_SOURCE_AUTO:
            data = await try_evcc()
            if data.get("rates"):
                return data
            _LOGGER.debug("Auto: EVCC empty — trying Forecast.Solar")
            data = try_forecast_solar()
            if data.get("rates"):
                return data
            _LOGGER.debug("Auto: Forecast.Solar empty — trying Solcast")
            return try_solcast()

        _LOGGER.warning("Unknown solar forecast source '%s' — defaulting to EVCC", source)
        return await try_evcc()

    def _fetch_solar_from_forecast_solar(self, entity_id: str) -> dict:
        """Read a Forecast.Solar HA entity's `watts` attribute and convert to EVCC format.

        Forecast.Solar exposes a `watts` attribute on its energy_production_* sensors,
        keyed by ISO timestamp (typically hourly, local-naive or with TZ). We normalise
        to UTC ISO and emit the same {start, value} list the rest of the coordinator
        consumes from EVCC.
        """
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            _LOGGER.debug("forecast_solar entity %s unavailable", entity_id)
            return {}

        watts_dict = state.attributes.get("watts")
        if not isinstance(watts_dict, dict) or not watts_dict:
            _LOGGER.debug("forecast_solar entity %s missing/empty 'watts' attribute", entity_id)
            return {}

        rates: list[dict] = []
        for ts_str, watts in watts_dict.items():
            try:
                start_dt = datetime.fromisoformat(str(ts_str))
                if start_dt.tzinfo is None:
                    # forecast_solar usually returns local Copenhagen times without TZ
                    start_dt = start_dt.replace(tzinfo=_CPH_TZ)
                utc_dt = start_dt.astimezone(timezone.utc)
                rates.append({"start": utc_dt.isoformat(), "value": float(watts)})
            except (ValueError, TypeError) as err:
                _LOGGER.debug("forecast_solar: skipping bad timestamp %s: %s", ts_str, err)

        rates.sort(key=lambda r: r["start"])
        if rates:
            _LOGGER.debug(
                "forecast_solar: read %d slots from %s (first=%s, last=%s)",
                len(rates), entity_id, rates[0]["start"], rates[-1]["start"],
            )
        return {"rates": rates} if rates else {}

    def _fetch_solar_from_solcast(self, entity_id: str) -> dict:
        """Read a Solcast HA integration entity and convert to EVCC format
        (per-slot `{"start": iso, "value": watts}` where `value` is the
        average power during the slot in watts).

        Unit handling (v0.29.1 — bug fix):
        The Solcast HA integration's `pv_estimate` field is **kW (average
        power during the slot)** in modern versions (4.x and newer). Older
        v3.x versions reported `pv_estimate` as kWh per period (energy).
        The integration auto-detects which semantic applies by comparing
        the maximum `pv_estimate` in `detailedForecast` against the
        `peak_forecast_*` sibling sensor (which is unambiguously in W with
        `device_class: power`):
            - If the values match → pv_estimate is in kW (power).
            - If detailedForecast peak ≈ 2 × peak_forecast → pv_estimate
              is in kWh per 30-min slot (energy). Divide by dur_h.
        Default behaviour (when peak_forecast sibling can't be found) is
        kW, matching the modern Solcast HA integration.
        """
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            _LOGGER.debug("solcast entity %s unavailable", entity_id)
            return {}

        # Solcast exposes the forecast under different attribute names across
        # versions; try the common ones in order of preference.
        forecast = (
            state.attributes.get("detailedForecast")
            or state.attributes.get("detailedHourly")
            or state.attributes.get("DetailedForecast")
        )
        if not isinstance(forecast, list) or not forecast:
            _LOGGER.debug("solcast entity %s has no detailedForecast/Hourly list", entity_id)
            return {}

        # Pre-compute per-entry start times so we can derive slot duration from gaps
        parsed: list[tuple[datetime, float]] = []
        for item in forecast:
            ts = item.get("period_start") or item.get("periodStart")
            value = item.get("pv_estimate")
            if ts is None or value is None:
                continue
            try:
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                parsed.append((dt.astimezone(timezone.utc), float(value)))
            except (ValueError, TypeError) as err:
                _LOGGER.debug("solcast: skipping bad entry %s: %s", item, err)

        parsed.sort(key=lambda x: x[0])
        if not parsed:
            return {}

        # ── Unit detection (v0.29.1) ───────────────────────────────────────
        # Compare the maximum detailedForecast value against the matching
        # peak_forecast_today / peak_forecast_tomorrow sensor (in W,
        # device_class=power). The naming convention transforms
        # ".._forecast_today" → ".._peak_forecast_today".
        is_power = True   # Default: modern Solcast HA integration semantics
        if "forecast_today" in entity_id or "forecast_tomorrow" in entity_id:
            peak_entity = entity_id.replace("forecast_today", "peak_forecast_today")
            peak_entity = peak_entity.replace("forecast_tomorrow", "peak_forecast_tomorrow")
            peak_state = self.hass.states.get(peak_entity)
            if peak_state and peak_state.state not in ("unknown", "unavailable"):
                try:
                    peak_w = float(peak_state.state)   # always in W per sensor unit
                    max_value = max(v for _, v in parsed)
                    if max_value > 0:
                        ratio = (peak_w / 1000.0) / max_value
                        # ratio ≈ 1.0 → pv_estimate is in kW
                        # ratio ≈ 0.5 → pv_estimate is in kWh per 30-min slot
                        is_power = ratio > 0.75
                        _LOGGER.debug(
                            "Solcast unit detection: peak_w=%.0f W, max(pv_estimate)=%.3f, ratio=%.2f → %s",
                            peak_w, max_value, ratio,
                            "kW (power)" if is_power else "kWh per period (energy)",
                        )
                except (ValueError, TypeError):
                    pass

        rates: list[dict] = []
        for i, (start, value) in enumerate(parsed):
            # Slot duration = gap to next entry; fall back to 0.5 h (Solcast default)
            if i + 1 < len(parsed):
                dur_h = (parsed[i + 1][0] - start).total_seconds() / 3600
                if dur_h <= 0 or dur_h > 2:
                    dur_h = 0.5
            else:
                dur_h = 0.5
            if is_power:
                # value is already in kW (average power over the slot)
                watts = round(value * 1000, 1)
            else:
                # value is kWh per period (legacy Solcast v3.x semantic)
                watts = round(value / dur_h * 1000, 1)
            rates.append({"start": start.isoformat(), "value": watts})

        if rates:
            _LOGGER.debug(
                "solcast: read %d slots from %s (first=%s, last=%s, is_power=%s)",
                len(rates), entity_id, rates[0]["start"], rates[-1]["start"], is_power,
            )
        return {"rates": rates} if rates else {}

    # ------------------------------------------------------------------ #
    # Price source: Energi Data Service Elspotprices                      #
    # ------------------------------------------------------------------ #

    async def _fetch_eds_prices(
        self,
        session: aiohttp.ClientSession,
        price_area: str,
        reference_dt: datetime,
    ) -> dict:
        """Fetch day-ahead prices from Energi Data Service DayAheadPrices.

        Returns a dict in EVCC-compatible format:
            {"rates": [{"start": "<utc-iso>", "value": <dkk_per_kwh>}, ...]}

        The DayAheadPrices dataset has 15-minute resolution (4 slots/hour) and
        every quarter-hour record becomes its own rate — no hourly aggregation.
        The optimizer solves at this native 15-min slot resolution end-to-end
        (slot durations are derived from the gaps in `_forecast_slots`).

        Nord Pool day-ahead prices are published at 13:00 CET for the next
        calendar day.  We fetch today + tomorrow (limit=192 = 4×48h) so the
        full 24-h horizon is populated once tomorrow's prices are available.

        TimeDK values are local Copenhagen time (CET/CEST) without timezone
        info; we convert to UTC using the Europe/Copenhagen zone so that DST
        transitions are handled correctly year-round.
        """
        today_str = reference_dt.astimezone(_CPH_TZ).strftime("%Y-%m-%d")
        url = (
            f"{EDS_ELSPOT_URL}"
            f'?filter={{"PriceArea":"{price_area}"}}'
            f"&sort=TimeDK%20ASC"
            f"&start={today_str}"
            f"&limit=192"
        )
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                resp.raise_for_status()
                # v0.55.1 — size-cap the body (see _fetch_json).
                _max_bytes = 8_000_000
                if resp.content_length is not None and resp.content_length > _max_bytes:
                    raise ValueError(f"EDS response too large (area {price_area})")
                _raw = await resp.content.read(_max_bytes + 1)
                if len(_raw) > _max_bytes:
                    raise ValueError(f"EDS response exceeded size cap (area {price_area})")
                import json as _json  # noqa: PLC0415
                data = _json.loads(_raw) if _raw else {}
        except Exception as err:
            _LOGGER.warning(
                "EDS DayAheadPrices fetch failed (area %s): %s — using cached prices", price_area, err)
            return self._eds_fallback(reference_dt)

        records = data.get("records", [])
        if not records:
            _LOGGER.warning(
                "EDS DayAheadPrices: no records returned for area %s — using cached prices", price_area)
            return self._eds_fallback(reference_dt)

        rates: list[dict] = []
        for rec in records:
            time_dk = rec.get("TimeDK")
            spot_dkk_mwh = rec.get("DayAheadPriceDKK")
            if time_dk is None or spot_dkk_mwh is None:
                continue
            try:
                local_dt = datetime.fromisoformat(time_dk).replace(tzinfo=_CPH_TZ)
                utc_dt = local_dt.astimezone(timezone.utc)
                rates.append({
                    "start": utc_dt.isoformat(),
                    "value": round(float(spot_dkk_mwh) / 1000.0, 6),
                })
            except (ValueError, TypeError) as parse_err:
                _LOGGER.debug("EDS: skipping bad record %s: %s", rec, parse_err)

        _LOGGER.info(
            "EDS DayAheadPrices: area %s — %d records, %d valid rates",
            price_area, len(records), len(rates),
        )
        if rates:
            # v0.59.4 — cache the good rates (set _stored every cycle but DON'T
            # async_save here — EDS is fetched on every fast tick, and the
            # periodic learning-tick save persists it without flash-wear).
            self._cached_eds_rates = rates
            self._last_eds_refresh = reference_dt
            self._stored["eds_rates_cache"] = rates
            self._stored["eds_refresh_iso"] = reference_dt.isoformat()
            return {"rates": rates}
        return self._eds_fallback(reference_dt)

    def _eds_fallback(self, now: datetime) -> dict:
        """Return cached EDS rates whose slots are still current/future (v0.59.4).

        Lets a failed, garbled, or rate-limited fetch — or the window right
        after a restart — keep the plan running on the last known spot prices
        instead of returning nothing. Past slots are dropped so the optimiser
        only sees still-relevant prices; if nothing usable remains, returns {}.
        """
        if not self._cached_eds_rates:
            return {}
        cutoff = now - timedelta(hours=1)
        rates = []
        for r in self._cached_eds_rates:
            try:
                if datetime.fromisoformat(r["start"]) >= cutoff:
                    rates.append(r)
            except (ValueError, TypeError, KeyError):
                continue
        if rates:
            _LOGGER.info("EDS: falling back to %d cached spot rates", len(rates))
        return {"rates": rates} if rates else {}

    # ------------------------------------------------------------------ #
    # Day-ahead DP optimizer                                               #
    # ------------------------------------------------------------------ #

    def _run_optimizer(
        self,
        now: datetime,
        grid_slot_data: list[tuple],
        solar_slot_data: list[tuple],
        solar_accuracy_factor: float,
        current_soc: float,
        capacity_kwh: float,
        floor_soc: float,
        max_soc: float,
        efficiency: float,
        charge_rate_kw: float,
        house_load_profile: list[float],
        ev_charge_hourly: list[float],
        ev_max_kw: float,
        vat_factor: float,
        tariff_sched: list[float],
        elafgift: float,
        spot_markup: float,
        export_fee: float,
        feed_in_tariff: float,
        min_export_price: float,
        min_spread: float,
        max_export_kw: float,
        ev_session_kw: float = 0.0,
        ev_session_horizon_h: float = 0.0,
        house_load_weekend: list[float] | None = None,
    ) -> list[dict]:
        """Backward-induction dynamic programming optimizer.

        Solves the 24-h charge/export sequencing problem optimally over all
        future hourly slots.  The state is battery SoC (0–100 %, integer
        steps) and the actions are CHARGE, EXPORT, or IDLE.

        Returns a list of slot dicts — one per future hour — each containing:
            hour    : local hour of day (0–23)
            action  : "CHARGE" | "EXPORT" | "IDLE"
            soc     : expected SoC at the start of that hour (integer %)
            buy     : full buy-side price for that hour (DKK/kWh)
            sell    : sell-side price for that hour (DKK/kWh)

        The optimizer is intentionally conservative on the first run when the
        house-load and EV models are cold (all zeros).  Models warm up within
        a few days of operation, after which the optimizer has accurate per-hour
        demand forecasts to work with.
        """
        if not grid_slot_data or capacity_kwh <= 0 or charge_rate_kw <= 0:
            return []

        try:
            return self._dp_solve(
                now, grid_slot_data, solar_slot_data, solar_accuracy_factor, current_soc,
                capacity_kwh, floor_soc, max_soc, efficiency,
                charge_rate_kw, house_load_profile, ev_charge_hourly, ev_max_kw,
                vat_factor, tariff_sched, elafgift, spot_markup,
                export_fee, feed_in_tariff, min_export_price, min_spread, max_export_kw,
                ev_session_kw, ev_session_horizon_h,
                house_load_weekend=house_load_weekend,
            )
        except Exception as err:
            _LOGGER.warning("Optimizer failed — returning empty plan: %s", err)
            return []

    def _dp_solve(
        self,
        now: datetime,
        grid_slot_data: list[tuple],
        solar_slot_data: list[tuple],
        solar_accuracy_factor: float,
        current_soc: float,
        capacity_kwh: float,
        floor_soc: float,
        max_soc: float,
        efficiency: float,
        charge_rate_kw: float,
        house_load_profile: list[float],
        ev_charge_hourly: list[float],
        ev_max_kw: float,
        vat_factor: float,
        tariff_sched: list[float],
        elafgift: float,
        spot_markup: float,
        export_fee: float,
        feed_in_tariff: float,
        min_export_price: float,
        min_spread: float,
        max_export_kw: float,
        ev_session_kw: float = 0.0,
        ev_session_horizon_h: float = 0.0,
        house_load_weekend: list[float] | None = None,
    ) -> list[dict]:
        """Core DP computation at native 15-min resolution.

        Key model features (v0.22.0):
        - Solves at slot granularity (typically 15 min) rather than averaging to
          hourly. Captures short-duration price spikes that hourly averaging hides.
        - Horizon extends up to 48 h when tomorrow's day-ahead prices are
          available (published at 13:00 CET).
        - Terminal value at end of horizon = (remaining usable kWh) × (mean sell
          price across the planning window). Prevents the trivial-discharge bug
          at hour N-1 where V was previously zero.
        - `spread_ok` uses the cheapest buy *after* the candidate export slot,
          not the global cheapest — OR a genuine solar-funded refill later in
          the horizon (v0.75.13), so a real export opportunity isn't vetoed
          on a day with free solar coming but no cheap grid price. Stops the
          model from approving late-day exports that have no viable recharge
          ahead, grid- or solar-funded.
        - Battery degradation cost (DKK/kWh cycled) is subtracted from both
          CHARGE and EXPORT rewards so the optimizer prices in finite cycle life.
        """
        # ── Build per-slot data ───────────────────────────────────────────
        # Each slot keeps its native duration (typically 0.25 h for 15-min
        # day-ahead prices). Solar is mapped to slot by start timestamp.
        #
        # Per-slot accuracy correction: the optimizer now applies a HOUR-OF-DAY
        # specific factor learned from observation, falling back to the global
        # factor for hours that haven't warmed up yet. This captures the
        # orientation effect (east panels over-forecast in afternoon, west
        # panels in morning, etc.) without any user input about panel layout.
        global_acc = max(0.0, float(solar_accuracy_factor))
        # v0.44.0 — S1: the per-hour solar factor is the `confidence` percentile
        # of the observed forecast/actual ratio, not just the median. At the
        # default confidence of 50 this IS the median (numerically identical to
        # the prior behaviour), so the default is a no-op. Lowering it makes the
        # planner assume more conservative solar. Cold hours fall back to the
        # global rolling factor, exactly as before.
        confidence = float(self._stored.get(
            "solar_confidence_pct", DEFAULT_SOLAR_CONFIDENCE_PCT,
        ))
        hourly_acc: list[float] = []
        for h in range(24):
            pct = self.get_solar_hour_percentile(h, confidence)
            hourly_acc.append(global_acc if pct is None else pct)

        def _slot_factor(slot_start_dt):
            try:
                h = slot_start_dt.astimezone().hour
            except Exception:
                return global_acc
            base = max(0.0, float(hourly_acc[h] if 0 <= h < 24 else global_acc))
            # v0.28.6: layer the short-term residual on top of the long-term
            # per-hour factor for slots within the decay window.
            try:
                hours_ahead = max(0.0, (slot_start_dt - now).total_seconds() / 3600.0)
                st = self.get_short_term_solar_factor(hours_ahead)
                return base * st
            except Exception:  # noqa: BLE001
                return base

        solar_kw_by_start: dict = {
            s[0]: (s[4] / 1000.0) * _slot_factor(s[0]) for s in solar_slot_data
        }

        while len(ev_charge_hourly) < 24:
            ev_charge_hourly.append(0.0)
        while len(house_load_profile) < 24:
            house_load_profile.append(0.5)
        while len(tariff_sched) < 24:
            tariff_sched.append(0.0)
        # v0.46.0 — L1: weekend profile (falls back to the weekday profile when
        # not supplied / not yet warmed up). Per-slot selection happens below.
        house_load_weekend = list(house_load_weekend) if house_load_weekend else list(house_load_profile)
        while len(house_load_weekend) < 24:
            house_load_weekend.append(0.5)

        slot_data: list[dict] = []
        for slot_start, dur_h, h, m, spot in grid_slot_data:
            # v0.29.0: buy price routes through _compute_buy_price so the DP
            # optimiser sees the same Strømligning-aware values as the rest
            # of the integration.
            buy_h = self._compute_buy_price(
                spot=spot,
                hour=h,
                slot_start_dt=slot_start,
                spot_markup=spot_markup,
                tariff_this_hour_dso=tariff_sched[h],
                elafgift=elafgift,
                vat_factor=vat_factor,
            )
            sell_h = max(0.0, spot - export_fee - feed_in_tariff)
            solar_kw = solar_kw_by_start.get(slot_start, 0.0)
            # v0.46.0 — L1: pick the weekday or weekend load curve by the slot's
            # own date, so a 48 h horizon that spans into the weekend uses the
            # right shape per slot.
            try:
                slot_is_weekend = slot_start.astimezone().weekday() >= 5
            except Exception:  # noqa: BLE001
                slot_is_weekend = False
            house_kw = (house_load_weekend if slot_is_weekend else house_load_profile)[h]
            ev_prob = ev_charge_hourly[h]
            ev_kw = ev_prob * ev_max_kw
            # v0.45.0 — E1: within the live-session horizon, use the certain
            # session demand instead of the hour-of-day expectation, and block
            # battery grid-charging so it doesn't stack against the car's draw.
            hours_ahead = max(0.0, (slot_start - now).total_seconds() / 3600.0)
            ev_session_active = (
                ev_session_kw > 0.0 and hours_ahead <= ev_session_horizon_h
            )
            if ev_session_active:
                ev_kw = max(ev_kw, ev_session_kw)

            # Idle dynamics: solar → house → EV → battery, then any deficit from battery
            solar_to_house = min(solar_kw, house_kw)
            house_from_battery = max(0.0, house_kw - solar_kw)
            solar_remaining = solar_kw - solar_to_house
            solar_to_ev = min(solar_remaining, ev_kw)
            solar_to_battery = max(0.0, solar_remaining - solar_to_ev)
            # SoC drift over the slot duration (% of capacity)
            idle_delta_pct = (solar_to_battery - house_from_battery) * dur_h / capacity_kwh * 100.0

            slot_data.append({
                "slot_start": slot_start,
                "h": h,
                "m": m,
                "dur_h": dur_h,
                "buy": round(buy_h, 4),
                "sell": round(sell_h, 4),
                "idle_delta_pct": idle_delta_pct,
                # v0.75.13 — the expected/certain EV draw for this slot,
                # kept instead of collapsing straight to a binary "blocked"
                # flag; see the CHARGE branch below for how it's used.
                "ev_kw": ev_kw,
            })

        N = len(slot_data)
        if N == 0:
            return []

        # ── Best buy AFTER each slot (for spread_ok check) ─────────────────
        # An EXPORT decision at slot t is only viable if there exists a cheaper
        # buy slot AFTER t — otherwise the round-trip is guaranteed to lose money.
        best_buy_after: list[float] = [float("inf")] * N
        running_min = float("inf")
        for t in range(N - 1, -1, -1):
            if t < N - 1:
                running_min = min(running_min, slot_data[t + 1]["buy"])
            best_buy_after[t] = running_min

        # ── Solar-funded refill available AFTER each slot ──────────────────
        # v0.75.13 — the check above only recognises a GRID-funded refill.
        # The value function's own idle-dynamics accounting (idle_delta_pct
        # below) already knows solar can refill the battery for free — this
        # pre-filter couldn't see that, so it could veto a genuinely
        # profitable export on a day with real solar and a thin grid spread
        # (exactly a "prices too flat for arbitrage" day) purely because no
        # cheap grid buy existed later, even though free solar did. Cumulative
        # sum (not running min, since solar refill accumulates across several
        # slots rather than coming from one best slot) of the positive
        # idle_delta_pct — genuine solar surplus over house load — for every
        # slot strictly after t. Gated at MIN_EXPORTABLE_KWH, the same
        # "worth bothering with" threshold already used elsewhere for export
        # decisions, so a negligible solar dribble doesn't unlock the gate.
        solar_kwh_after: list[float] = [0.0] * N
        running_solar_kwh = 0.0
        for t in range(N - 1, -1, -1):
            if t < N - 1:
                next_idle_pct = slot_data[t + 1]["idle_delta_pct"]
                if next_idle_pct > 0:
                    running_solar_kwh += next_idle_pct / 100.0 * capacity_kwh
            solar_kwh_after[t] = running_solar_kwh

        # ── Terminal value: worth of SoC remaining at the horizon end ──
        # v0.63.0 — value retained SoC at the AVOIDED-BUY price, not the sell
        # price. A kWh kept past the horizon is worth what it replaces: the
        # buy price the house would otherwise pay (buy > sell by the full retail
        # spread). The old mean-SELL proxy under-valued it, so the optimiser
        # dumped the final SoC at the horizon edge — an over-discharge bias that
        # the dynamic floor then had to fight. Avoided-buy is the economically
        # correct value ("never sell a kWh for less than it costs to replace");
        # peaks still exceed it so real arbitrage is unaffected, and spread_ok
        # still governs mid-horizon trades. Floored at mean sell (selling is
        # always an option) for robustness against degenerate price data.
        sell_vals = [s["sell"] for s in slot_data if s["sell"] > 0]
        buy_vals = [s["buy"] for s in slot_data if s["buy"] > 0]
        mean_sell = statistics.mean(sell_vals) if sell_vals else 0.0
        mean_buy = statistics.mean(buy_vals) if buy_vals else 0.0
        expected_terminal_value = max(mean_buy, mean_sell)
        if expected_terminal_value <= 0.0:
            expected_terminal_value = DEFAULT_TERMINAL_VALUE_FALLBACK

        # Effective export rate: use user cap if set, else same as charge rate
        export_rate_kw = max_export_kw if max_export_kw > 0 else charge_rate_kw

        # Efficiency split: assume symmetric charge/discharge
        charge_eff = efficiency ** 0.5
        discharge_eff = efficiency ** 0.5

        # Battery degradation cost per kWh cycled (read once from storage)
        degradation_cost = float(self._stored.get(
            "battery_degradation_cost", DEFAULT_BATTERY_DEGRADATION_COST,
        ))

        SOC_STATES = 101  # SoC 0–100 %

        # Floor/max as integers
        soc_floor = int(max(0, round(floor_soc)))
        soc_max = int(min(100, round(max_soc)))

        # ── Backward induction ────────────────────────────────────────────
        # Initialize V at the horizon edge with the terminal value.
        # V_terminal[s] = (usable kWh at SoC s) × discharge_eff × expected_terminal_value
        V: list[float] = []
        for s in range(SOC_STATES):
            remaining_kwh = max(0.0, (s - soc_floor) / 100.0 * capacity_kwh)
            V.append(remaining_kwh * discharge_eff * expected_terminal_value)

        policy: list[list[str]] = [["I"] * SOC_STATES for _ in range(N)]

        for t in range(N - 1, -1, -1):
            sd = slot_data[t]
            buy_h = sd["buy"]
            sell_h = sd["sell"]
            idle_delta = sd["idle_delta_pct"]
            ev_kw = sd["ev_kw"]
            dur_h = sd["dur_h"]

            # v0.75.13 — the battery's allowed charge rate for this slot is
            # reduced by the EV's expected draw, rather than the CHARGE
            # action being entirely unavailable above a hard EV-probability
            # threshold. charge_rate_kw is the grid-headroom-capped rate for
            # a SINGLE draw; sharing that same headroom with a simultaneous
            # EV draw means subtracting the EV's share from it. At ev_kw=0
            # this is unchanged from before; at high EV probability/certainty
            # it converges to the old fully-blocked behaviour when
            # charge_rate_kw itself is smaller than the EV's draw, but
            # recovers the real spare headroom in between instead of
            # discarding it at a single 0.7 cliff. The DP's plan is
            # inherently a forecast either way — the actual command at
            # execution time is still re-capped to LIVE headroom every cycle
            # by _maintain_charge_power, so an imprecise planning-time
            # estimate here can't cause a real overcurrent, only a
            # suboptimal plan that gets corrected when the slot arrives.
            effective_charge_rate_kw = max(0.0, charge_rate_kw - ev_kw)

            # Per-slot SoC step sizes (% of capacity) — duration matters at 15-min granularity
            charge_delta_slot = effective_charge_rate_kw * charge_eff * dur_h / capacity_kwh * 100.0
            export_delta_slot = export_rate_kw * dur_h / capacity_kwh * 100.0
            charge_kwh_slot = effective_charge_rate_kw * dur_h

            # Forward-only spread check: cheapest buy AFTER this slot
            #
            # v0.75.11 — recharge_cost_after now matches the CHARGE branch's
            # own economics (below): the true cost per usable kWh added by
            # grid-charging is buy_price / charge_eff, not buy_price divided
            # by the full round-trip `efficiency`. The CHARGE branch pays
            # buy_h on the raw grid kWh drawn but only banks charge_eff of it
            # as usable capacity — so /efficiency (charge_eff × discharge_eff,
            # the smaller number) overstated the real refill cost and made
            # this pre-filter gate stricter than the value function it's
            # gating ever actually prices the refill at. Since spread_ok only
            # decides whether EXPORT is offered as an option at a given state
            # — the real profit math (val_ex/val_ch below) is unaffected
            # either way — the old, too-pessimistic version could only ever
            # cause a missed opportunity, never a bad trade; this just lets
            # the optimiser recognise a few more of them.
            buy_after = best_buy_after[t]
            recharge_cost_after = (
                buy_after / charge_eff if charge_eff > 0 else buy_after
            )
            grid_spread_ok = (
                buy_after != float("inf")
                and sell_h - recharge_cost_after >= min_spread
            )
            # v0.75.13 — a solar-funded refill is free, so it doesn't need to
            # clear min_spread the way a grid refill does; sell_h > 0 (checked
            # separately below at the EXPORT branch's own gate) is enough to
            # make it worthwhile. See solar_kwh_after's own comment above.
            solar_refill_ok = solar_kwh_after[t] >= MIN_EXPORTABLE_KWH
            spread_ok = grid_spread_ok or solar_refill_ok

            new_V: list[float] = [0.0] * SOC_STATES

            for s in range(SOC_STATES):
                # ── IDLE ──────────────────────────────────────────────────
                # Three regimes depending on where idle dynamics land SoC:
                #   below floor  → house deficit imported from grid at buy_h
                #   above max    → solar surplus exported to grid at sell_h
                #   in range     → SoC drifts within bounds; no extra grid flow
                unclamped = s + idle_delta
                if unclamped < soc_floor:
                    deficit_pct = soc_floor - unclamped
                    deficit_kwh = deficit_pct / 100.0 * capacity_kwh
                    grid_import_cost = deficit_kwh * buy_h
                    s_idle = soc_floor
                    val_idle = V[s_idle] - grid_import_cost
                elif unclamped > soc_max:
                    overflow_pct = unclamped - soc_max
                    overflow_kwh = overflow_pct / 100.0 * capacity_kwh
                    # Solar surplus exported — no degradation cost since the
                    # battery is not cycled (surplus bypasses storage).
                    solar_export_revenue = overflow_kwh * sell_h
                    s_idle = soc_max
                    val_idle = V[s_idle] + solar_export_revenue
                else:
                    s_idle = int(unclamped + 0.5)
                    s_idle = max(0, min(100, s_idle))
                    val_idle = V[s_idle]
                best_val = val_idle
                best_act = "I"

                # ── CHARGE ────────────────────────────────────────────────
                # Cost = (buy_price + degradation) × kWh charged from grid.
                # Same floor/max-aware accounting for residual idle dynamics.
                # v0.75.13 — gated on effective_charge_rate_kw (already
                # reduced by the EV's expected draw above) clearing the same
                # "not worth a token charge" minimum used elsewhere, instead
                # of the old hard ev_blocked cliff.
                if s < soc_max and effective_charge_rate_kw >= GRID_MIN_CHARGE_KW:
                    unclamped_ch = s + charge_delta_slot + idle_delta
                    val_ch = -charge_kwh_slot * (buy_h + degradation_cost)
                    if unclamped_ch < soc_floor:
                        deficit_pct = soc_floor - unclamped_ch
                        deficit_kwh = deficit_pct / 100.0 * capacity_kwh
                        val_ch -= deficit_kwh * buy_h
                        s_ch = soc_floor
                    elif unclamped_ch > soc_max:
                        overflow_pct = unclamped_ch - soc_max
                        overflow_kwh = overflow_pct / 100.0 * capacity_kwh
                        val_ch += overflow_kwh * sell_h
                        s_ch = soc_max
                    else:
                        s_ch = int(unclamped_ch + 0.5)
                        s_ch = max(0, min(100, s_ch))
                    val_ch += V[s_ch]
                    if val_ch > best_val:
                        best_val = val_ch
                        best_act = "C"

                # ── EXPORT ────────────────────────────────────────────────
                # Revenue = (kWh out × discharge_eff × sell) − (kWh out × degradation)
                # Floor/max-aware accounting for residual idle dynamics.
                if s > soc_floor and sell_h > min_export_price and spread_ok:
                    avail_pct = s - soc_floor
                    actual_exp_pct = min(export_delta_slot, avail_pct)
                    actual_exp_kwh = actual_exp_pct / 100.0 * capacity_kwh
                    val_ex = actual_exp_kwh * (discharge_eff * sell_h - degradation_cost)
                    unclamped_ex = s - actual_exp_pct + idle_delta
                    if unclamped_ex < soc_floor:
                        deficit_pct = soc_floor - unclamped_ex
                        deficit_kwh = deficit_pct / 100.0 * capacity_kwh
                        val_ex -= deficit_kwh * buy_h
                        s_ex = soc_floor
                    elif unclamped_ex > soc_max:
                        overflow_pct = unclamped_ex - soc_max
                        overflow_kwh = overflow_pct / 100.0 * capacity_kwh
                        val_ex += overflow_kwh * sell_h
                        s_ex = soc_max
                    else:
                        s_ex = int(unclamped_ex + 0.5)
                        s_ex = max(0, min(100, s_ex))
                    val_ex += V[s_ex]
                    if val_ex > best_val:
                        best_val = val_ex
                        best_act = "E"

                new_V[s] = best_val
                policy[t][s] = best_act

            V = new_V

        # ── Forward pass: generate the plan from current SoC ─────────────
        _ACTION_NAMES = {"I": "IDLE", "C": "CHARGE", "E": "EXPORT"}
        soc_s = max(0, min(100, int(current_soc + 0.5)))
        plan: list[dict] = []

        for t in range(N):
            sd = slot_data[t]
            dur_h = sd["dur_h"]
            act_code = policy[t][soc_s]
            action = _ACTION_NAMES[act_code]

            plan.append({
                "hour": sd["h"],
                "minute": sd["m"],
                "action": action,
                "soc": soc_s,
                "buy": sd["buy"],
                "sell": sd["sell"],
                "iso": sd["slot_start"].isoformat() if hasattr(sd["slot_start"], "isoformat") else str(sd["slot_start"]),
            })

            charge_delta_slot = charge_rate_kw * charge_eff * dur_h / capacity_kwh * 100.0
            export_delta_slot = export_rate_kw * dur_h / capacity_kwh * 100.0
            idle_delta = sd["idle_delta_pct"]

            if act_code == "C":
                soc_s = int(max(float(soc_floor), min(float(soc_max), soc_s + charge_delta_slot + idle_delta)) + 0.5)
            elif act_code == "E":
                avail_pct = soc_s - soc_floor
                actual_exp_pct = min(export_delta_slot, float(avail_pct))
                soc_s = int(max(float(soc_floor), min(float(soc_max), soc_s - actual_exp_pct + idle_delta)) + 0.5)
            else:
                soc_s = int(max(float(soc_floor), min(float(soc_max), soc_s + idle_delta)) + 0.5)
            soc_s = max(0, min(100, soc_s))

        n_charge = sum(1 for s in plan if s["action"] == "CHARGE")
        n_export = sum(1 for s in plan if s["action"] == "EXPORT")
        horizon_hours = sum(s["dur_h"] for s in slot_data)
        _LOGGER.debug(
            "Optimizer: %d charge slots, %d export slots over %d slots (%.1f h horizon) "
            "(SoC %d%%→%d%%, terminal_value=%.3f, degradation=%.3f)",
            n_charge, n_export, N, horizon_hours,
            int(current_soc + 0.5), soc_s,
            expected_terminal_value, degradation_cost,
        )
        return plan

    # ------------------------------------------------------------------ #
    # Helpers                                                               #
    # ------------------------------------------------------------------ #

    def _get_float_state(self, entity_id: str, default: float | None = None) -> float | None:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return default
        try:
            return float(state.state)
        except ValueError:
            return default

    @staticmethod
    async def _fetch_json(session: aiohttp.ClientSession, url: str) -> dict:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            resp.raise_for_status()
            # v0.55.1 — cap the body so a hostile/runaway endpoint can't exhaust
            # memory. Real price/EVCC payloads are well under 8 MB.
            max_bytes = 8_000_000
            if resp.content_length is not None and resp.content_length > max_bytes:
                raise ValueError(f"Response too large ({resp.content_length} B) from {url}")
            raw = await resp.content.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise ValueError(f"Response exceeded {max_bytes} B from {url}")
            import json as _json  # noqa: PLC0415
            return _json.loads(raw) if raw else {}

    @staticmethod
    def _make_result(mode: str = MODE_NORMAL, reason: str = "", **kwargs: Any) -> dict[str, Any]:
        return {"mode": mode, "reason": reason, **kwargs}

    async def async_restore_normal(self) -> None:
        """Force-restore normal operation (called on unload or disable)."""
        if self._current_mode != MODE_NORMAL:
            # v0.75.8 — close any open export/charge action-log session before
            # the mode is overwritten below. This is the only other place
            # self._current_mode changes outside the per-tick decision loop's
            # own transition-detection (coordinator.py ~2298), and it was the
            # one path that bypassed _close_action_session entirely — leaving
            # revenue tracking open forever for a session ended by disabling
            # Solar AI (switch off, the restore_normal service, or unload)
            # rather than by the decision loop picking a new mode itself.
            if self._current_mode in (MODE_EXPORTING, MODE_GRID_CHARGING):
                battery_soc = self._get_float_state(
                    self.config.get(CONF_BATTERY_SOC_ENTITY, FOXESS_BATTERY_SOC), 0)
                capacity_kwh = float(self._stored.get(
                    "battery_capacity", self.config.get("battery_capacity", DEFAULT_BATTERY_CAPACITY)))
                await self._close_action_session(datetime.now(timezone.utc), battery_soc, capacity_kwh)
            await self._transition_to(MODE_NORMAL)
            self._current_mode = MODE_NORMAL
        # v0.60.2 — restoring the inverter mode is not a full restore if the EV
        # controller left the house battery locked (max_discharge_current = 0,
        # set during FULL-mode charging so the car isn't fed by the battery).
        # Without this, the restore_normal service would strand the lock and the
        # battery could not discharge. The unload path already unlocks before
        # calling this (so the guard skips there); this covers the service path.
        if self._ev_battery_locked:
            try:
                await self._set_battery_lock(False)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "Battery unlock during restore_normal failed: %s", err)
        # v0.65.0 — likewise restore the on-grid Min-SoC if export raised it, so
        # the hardware export-floor backstop never strands the house's overnight SoC.
        await self._restore_export_min_soc()


# ------------------------------------------------------------------ #
# Module-level pure functions (easy to unit test)                     #
# ------------------------------------------------------------------ #

def _temp_bucket(temp_c: float) -> str | None:
    for key, min_c, max_c, _ in TEMP_BUCKETS:
        if (min_c is None or temp_c >= min_c) and (max_c is None or temp_c < max_c):
            return key
    return None


def _current_slot_forecast(rates: list[dict], now: datetime) -> float | None:
    """Return the Solcast forecasted watts for the current 15-min slot."""
    for rate in rates:
        start = datetime.fromisoformat(rate["start"])
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        end = start + timedelta(minutes=15)
        if start <= now < end:
            return float(rate["value"])
    return None


def _forecast_slots(
    rates: list[dict], now: datetime, hours: float
) -> list[tuple]:
    """Return (slot_start, duration_h, local_hour, local_minute, value) for each slot.

    Handles any slot granularity (15-min, 30-min, 1h) automatically by deriving
    the duration from the gap to the next slot.  Falls back to 15 minutes for the
    last slot.  Slots are returned in ascending time order.

    v0.47.5 fix: the slot currently *in progress* is INCLUDED (a slot is kept if
    it has not yet ended, i.e. its end > now), not just slots starting at/after
    `now`. Previously slots were filtered `now <= start`, which dropped the
    in-progress slot whenever the plan was (re)built mid-slot. The decision
    logic matches the current (hour, minute-bucket) to a plan slot, so dropping
    the in-progress slot left the optimiser with no slot to act on for the
    current interval — it fell through to IDLE and never executed the planned
    charge/export. With the receding-horizon replan (every 15 min, usually
    mid-slot) this happened almost every cycle. Including the in-progress slot
    makes plan slot 0 cover "now", so the match — and execution — work.
    """
    cutoff = now + timedelta(hours=hours)
    parsed: list[tuple] = []
    for rate in rates:
        start = datetime.fromisoformat(rate["start"])
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        parsed.append((start, rate["value"]))
    parsed.sort(key=lambda x: x[0])

    result: list[tuple] = []
    for i, (start, value) in enumerate(parsed):
        if start >= cutoff:
            continue
        if i + 1 < len(parsed):
            next_start = parsed[i + 1][0]
            dur_h = (next_start - start).total_seconds() / 3600
        else:
            next_start = start + timedelta(minutes=15)
            dur_h = 0.25  # default 15 min for the last slot
        # Keep the slot if it hasn't ended yet (covers the in-progress slot) —
        # not just slots starting at/after `now`.
        if next_start <= now:
            continue
        local = start.astimezone()
        result.append((start, dur_h, local.hour, local.minute, value))
    return result


def _forecast_values(rates: list[dict], now: datetime, hours: float) -> list[float]:
    cutoff = now + timedelta(hours=hours)
    result = []
    for rate in rates:
        start = datetime.fromisoformat(rate["start"])
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if now <= start < cutoff:
            result.append(rate["value"])
    return result


def _sum_forecast(rates: list[dict], now: datetime, hours: float, watts: bool = False) -> float:
    cutoff = now + timedelta(hours=hours)
    total = 0.0
    for rate in rates:
        start = datetime.fromisoformat(rate["start"])
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if now <= start < cutoff:
            val = rate["value"]
            if watts:
                total += val * (15 / 60) / 1000  # W × 15min → kWh
            else:
                total += val
    return round(total, 3)


def _rolling_mean(history: list[float], window: int) -> float:
    if not history:
        return 0.0
    relevant = history[-window:]
    return round(statistics.mean(relevant), 3) if relevant else 0.0


# NOTE: house-load projection moved to BatteryArbitrageCoordinator.
# _predict_house_load_window (v0.47.5) — it uses the learned hourly profile
# instead of flat-extrapolating the 2-hour average, which over-projected a
# short evening spike across the whole day.
