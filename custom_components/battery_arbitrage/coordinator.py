"""Data coordinator for Battery Arbitrage — the core brain."""
from __future__ import annotations

import asyncio
import logging
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
    DEFAULT_VAT_PCT,
    DEFAULT_EXPORT_FEE,
    LEARNING_TICK_INTERVAL_SECONDS,
    TARIFF_REFRESH_INTERVAL_SECONDS,
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
    FOXESS_LOAD_POWER,
    FOXESS_WORK_MODE_ENTITY,
    FOXESS_EXPORT_LIMIT_REGISTER,
    LEGACY_EXPORT_AUTOMATION,
    LOAD_HISTORY_MAX_SAMPLES,
    MIN_EXPORTABLE_KWH,
    SAVINGS_LOG_MAX_DAYS,
    MIN_GRID_CHARGE_KWH,
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
    STORAGE_KEY,
    STORAGE_VERSION,
    STROMLIGNING_SPOTPRICE_EX_VAT,
    TEMP_BUCKETS,
    VACATION_MIN_DURATION,
    VACATION_SHORT_WINDOW,
    VACATION_THRESHOLD,
    WORK_MODE_EXPORT,
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
    EV_CURTAILMENT_PROBE_SECONDS,
    EV_CURTAILMENT_PROBE_COOLDOWN_SECONDS,
    EV_STOP_RECOVERY_SECONDS,
    EV_START_DROP_TIMEOUT_SECONDS,
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
        self._current_mode = MODE_NORMAL
        self._mode_reason = ""
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
        # Legacy tick counters kept for set_ev_mode() back-compat reset only
        self._ev_above_start_count: int = 0
        self._ev_below_stop_count: int = 0
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
        self._pv_power_limited_flag: bool = False
        # Timestamp the probe started. None means no probe in flight. The
        # probe ends when the flag clears or `EV_CURTAILMENT_PROBE_SECONDS`
        # elapses, whichever comes first.
        self._ev_probe_started_at: datetime | None = None
        # v0.38.1 — Cool-down after a probe expired without clearing the
        # PV-limited flag. MPPT didn't lift → curtailment is for a reason
        # we can't undo (grid-operator limit, fault, etc.). Wait this long
        # before trying again. Cleared on EV disconnect so the next plug-in
        # is a fresh start.
        self._ev_probe_cooldown_until: datetime | None = None
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
        evcc_url = self.config["evcc_url"]
        now = datetime.now(timezone.utc)
        forecast_hours = self.config.get("forecast_hours", 24)

        # ── Fast: fetch live state every tick (dispatches on configured source) ──
        # Returns a dict in EVCC /api/state shape: homePower, pvPower, gridPower,
        # loadpoints (list), batteryMode. See _fetch_live_state() for the per-source
        # logic and resilience rules.
        evcc_state = await self._fetch_live_state(session, evcc_url)

        # ── Hourly: refresh tariff / price data ──────────────────────────
        tariff_stale = (
            self._last_tariff_refresh is None
            or (now - self._last_tariff_refresh).total_seconds() >= TARIFF_REFRESH_INTERVAL_SECONDS
        )
        if tariff_stale:
            price_area = self.config.get(CONF_PRICE_AREA, DEFAULT_PRICE_AREA)

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
            if eds_data.get("rates"):
                self._cached_grid_rates = eds_data
                _LOGGER.debug(
                    "EDS: %d spot price slots for area %s",
                    len(eds_data["rates"]), price_area,
                )
            else:
                # EDS unavailable — fall back to EVCC grid tariff
                _LOGGER.info(
                    "EDS spot prices unavailable for %s — falling back to EVCC grid tariff",
                    price_area,
                )
                try:
                    grid_data = await self._fetch_json(session, f"{evcc_url}{EVCC_API_GRID}")
                    if grid_data.get("rates"):
                        self._cached_grid_rates = grid_data
                    else:
                        _LOGGER.warning("EVCC grid tariff also returned no rates")
                except Exception as evcc_err:
                    _LOGGER.debug("EVCC grid tariff fallback failed: %s", evcc_err)

            self._last_tariff_refresh = now

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
                dso_sched, energinet_sched, (dso_feed_in, en_feed_in) = await asyncio.gather(
                    # DSO: 24 hourly prices + genuinely varying hours → nettarif C time only
                    # (excludes Effektbetaling capacity charges and flat samplaceret band tariffs)
                    fetch_tariff_schedule(
                        session, dso_gln, now,
                        require_all_prices=True,
                        require_varying_prices=True,
                    ),
                    # Energinet: only code 40000 (Transmissions nettarif, residential consumers)
                    # excludes 40010 (Indfødningstarif produktion) and 40020 (HV 132/150 kV)
                    fetch_tariff_schedule(
                        session, ENERGINET_GLN, now,
                        allowed_codes=ENERGINET_TARIFF_CODES,
                    ),
                    # Feed-in tariffs: DSO indfødning C + Energinet indfødning produktion (40010)
                    fetch_feed_in_tariff(session, dso_gln, ENERGINET_GLN, now),
                )
                self._tariff_schedule = [
                    round(d + e, 4) for d, e in zip(dso_sched, energinet_sched)
                ]
                self._feed_in_tariff_dso = dso_feed_in
                self._feed_in_tariff_energinet = en_feed_in
                self._last_tariff_schedule_refresh = now
                _LOGGER.debug(
                    "Tariff schedule refreshed (GLN %s + Energinet). "
                    "Hour 0: %.4f, Hour 12: %.4f DKK/kWh",
                    dso_gln,
                    self._tariff_schedule[0],
                    self._tariff_schedule[12],
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
                floor_active = self._current_floor_block is not None
                self._update_solar_accuracy(
                    current_forecast_w, pv_power_w, curtailed=floor_active,
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

        grid_slots = _forecast_values_with_hours(grid_rates.get("rates", []), now, forecast_hours)

        # Native-resolution slot data (handles 15-min or hourly depending on DSO/EVCC config)
        grid_slot_data = _forecast_slots(grid_rates.get("rates", []), now, forecast_hours)
        solar_slot_data = _forecast_slots(solar_rates.get("rates", []), now, forecast_hours)
        # Extended window for the DP optimizer — uses all available price data (typically 48 h
        # once tomorrow's day-ahead prices are published at 13:00 CET).
        grid_slot_data_opt = _forecast_slots(grid_rates.get("rates", []), now, 48)
        solar_slot_data_opt = _forecast_slots(solar_rates.get("rates", []), now, 48)
        # Solar lookup: slot_start → kW (value is average Watts during the slot)
        solar_kw_by_start: dict = {s[0]: s[4] / 1000.0 for s in solar_slot_data}
        if grid_slots:
            # v0.29.0: buy price computation routes through _compute_buy_price
            # which handles Strømligning mode (with optional overrides) and
            # falls back to the manual stack when no Strømligning data exists
            # for the slot.
            def _buy(spot_value: float, hour: int) -> float:
                return self._compute_buy_price(
                    spot=spot_value,
                    hour=hour,
                    slot_start_dt=now.replace(hour=hour, minute=0, second=0, microsecond=0),
                    spot_markup=spot_markup,
                    tariff_this_hour_dso=tariff_sched[hour],
                    elafgift=elafgift,
                    vat_factor=vat_factor,
                )
            buy_vals_sorted = sorted(_buy(spot, h) for h, spot in grid_slots)
            n_buy = len(buy_vals_sorted)
            buy_price_min = buy_vals_sorted[0]
            buy_price_p25 = buy_vals_sorted[max(0, n_buy // 4 - 1)]
            next_slot_slots = _forecast_values_with_hours(grid_rates.get("rates", []), now, 0.5)
            if next_slot_slots:
                h_next, spot_next = next_slot_slots[0]
                buy_price_next_slot = _buy(spot_next, h_next)
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
        if spot_entity_id:
            spot_state = self.hass.states.get(spot_entity_id)
            if spot_state and spot_state.state not in ("unknown", "unavailable"):
                try:
                    spot_ex_vat = float(spot_state.state)
                except ValueError:
                    pass

        if spot_ex_vat == 0.0:
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
        predicted_house_load_24h = _predict_house_load(
            load_2h_avg, load_28d_avg, vacation_mode, forecast_hours
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

        # Capacity: use learned value once enough Force Charge samples exist
        learned_capacity = self.get_learned_capacity()
        capacity_kwh = learned_capacity if learned_capacity is not None \
            else self.config.get("battery_capacity", DEFAULT_BATTERY_CAPACITY)

        # Efficiency: use FoxESS lifetime totals if available
        auto_efficiency = self.get_auto_efficiency()
        efficiency = auto_efficiency if auto_efficiency is not None \
            else self.config.get("round_trip_efficiency", DEFAULT_ROUND_TRIP_EFFICIENCY)

        # Capacity learning: gate to 5-min ticks (energy calculation needs correct interval_h)
        if is_learning_tick:
            self._learn_capacity(battery_soc, battery_charge_kw)

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
        if tariff_stale or not self._optimizer_plan:
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
                house_load_profile=self.get_house_load_profile(),
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
        # Fall back to reactive thresholds when no plan is available
        if not self._optimizer_plan:
            battery_export_at_peak = price_p75 > 0 and export_price >= price_p75
            optimizer_says_export = battery_export_at_peak and grid_arbitrage_worthwhile
            optimizer_says_charge = buy_price_next_slot <= buy_price_p25

        # ---- decision logic ----
        should_export = (
            optimizer_says_export
            and truly_exportable_kwh >= MIN_EXPORTABLE_KWH
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
            and optimizer_says_charge
            and importable_kwh >= MIN_GRID_CHARGE_KWH
            and not solar_will_fill
            and battery_soc < max_soc
            # Same EVCC respect: don't grid-charge if EVCC is managing battery
            and not evcc_managing_battery
            # Skip if EV typically charges at this hour — avoid competing for cheap slots
            and not ev_likely_charging
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

        # If grid is paying US to buy electricity (buy price ≤ 0), always charge if there's
        # room — this overrides the spread threshold and even the EV schedule check.
        if (
            buy_price_next_slot <= 0.0
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
                sell_slot = round(max(0.0, spot - export_fee - feed_in_tariff), 3)
                price_chart_slots.append({"h": h, "m": m, "buy": buy_slot, "sell": sell_slot})
        else:
            seen_ch: set[int] = set()
            for slot_start, dur_h, h, m, spot in grid_slot_data:
                if h not in seen_ch:
                    seen_ch.add(h)
                    buy_slot = round((spot + spot_markup + tariff_sched[h] + elafgift) * vat_factor, 3)
                    sell_slot = round(max(0.0, spot - export_fee - feed_in_tariff), 3)
                    price_chart_slots.append({"h": h, "m": 0, "buy": buy_slot, "sell": sell_slot})

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
            charge_str = ", ".join(f"{h:02d}h" for h in charge_hours) if charge_hours else "none"
            export_str = ", ".join(f"{h:02d}h" for h in export_hours) if export_hours else "none"
            plan_text = f"Charge: {charge_str}  ·  Export: {export_str}"
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

        # ---- execute action (skipped when disabled — data still reported) ----
        prev_mode = self._current_mode
        if self._enabled:
            new_mode, reason = await self._execute_decision(
                should_export, should_grid_charge, export_price,
                grid_arbitrage_spread, buy_price_next_slot, buy_price_p25, price_p75,
                truly_exportable_kwh, importable_kwh, solar_will_fill,
                ev_charging_now, ev_likely_charging, ev_block_prob,
                evcc_battery_mode, evcc_managing_battery,
                capped_charge_rate_kw,
            )
        else:
            new_mode = MODE_DISABLED
            if ev_charging_now:
                reason = "Disabled — EV actively charging"
            elif should_export:
                reason = "Disabled — would export if enabled"
            elif should_grid_charge:
                reason = "Disabled — would grid charge if enabled"
            elif ev_likely_charging:
                reason = f"Disabled — EV typically charges now ({ev_block_prob:.0%} learned)"
            else:
                reason = "Disabled — monitoring only"

        # ---- action log: detect export/charge session transitions ----
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

        # ---- export limit (every tick — enforces solar floor even when disabled) ----
        await self._maintain_export_limit(export_price_raw, min_export_price, new_mode)

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
            )
        savings = self.get_savings_summary()

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
        # result dict so the new charger_* sensors can read it (v0.27.0)
        ev_telemetry = {**ev_telemetry, **self.get_charger_telemetry()}

        # ---- save storage (learning tick only — avoids flash wear on fast ticks) ----
        if is_learning_tick:
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
            capacity_source="learned" if learned_capacity is not None else "configured",
            efficiency_source="auto" if auto_efficiency is not None else "configured",
            capacity_sample_count=len(self._stored.get("capacity_samples", [])),
            price_chart_slots=price_chart_slots,
            solar_chart_slots=solar_chart_slots,
            solar_today_remaining_raw_kwh=round(solar_today_remaining_raw_kwh, 2),
            solar_today_remaining_adj_kwh=round(solar_today_remaining_adj_kwh, 2),
            solar_tomorrow_raw_kwh=round(solar_tomorrow_raw_kwh, 2),
            solar_tomorrow_adj_kwh=round(solar_tomorrow_adj_kwh, 2),
            plan_text=plan_text,
            plan_charge_hours=charge_hours,
            plan_export_hours=export_hours,
            house_load_hourly=self.get_house_load_profile(),
            ev_max_kw=float(self._stored.get("ev_max_kw", 0.0)),
            action_log=self.get_action_log(20),
            action_log_count=len(self._stored.get("action_log", [])),
            solar_floor_log=self.get_solar_floor_log(20),
            solar_floor_log_count=len(self._stored.get("solar_floor_log", [])),
            solar_hourly_factors=self.get_solar_hourly_accuracy_profile(),
            solar_hourly_samples=self.get_solar_hourly_sample_counts(),
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
                f"Exporting: price {export_price:.2f} ≥ p75 {price_p75:.2f} DKK/kWh, "
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
        live_source = self.config.get(CONF_LIVE_DATA_SOURCE, DEFAULT_LIVE_DATA_SOURCE)
        coordinate_with_evcc = live_source in (LIVE_SOURCE_EVCC, LIVE_SOURCE_HYBRID) and evcc_url

        if new_mode == MODE_EXPORTING:
            # Feed-in First: inverter pushes battery + solar to grid
            await self._set_work_mode(WORK_MODE_EXPORT)
            # Apply export power cap if configured (0 = no cap)
            max_export_kw = float(self._stored.get("max_export_kw", DEFAULT_MAX_EXPORT_KW))
            if max_export_kw > 0:
                await self._set_discharge_power(max_export_kw)
            # Tell EVCC to hold so it doesn't fight our export
            if coordinate_with_evcc:
                self._we_set_evcc_mode = True
                await self._evcc_post(session, evcc_url, f"{EVCC_API_BATTERY_MODE}/{EVCC_BATTERY_HOLD}")

        elif new_mode == MODE_GRID_CHARGING:
            # Force Charge: inverter charges battery from grid at grid-headroom-capped rate
            await self._set_work_mode(WORK_MODE_FORCE_CHARGE)
            await self._set_charge_power(inverter_id, max_kw=capped_charge_rate_kw)
            if coordinate_with_evcc:
                self._we_set_evcc_mode = True
                await self._evcc_post(session, evcc_url, f"{EVCC_API_BATTERY_MODE}/{EVCC_BATTERY_HOLD}")

        elif new_mode == MODE_NORMAL:
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
        """
        if current_mode == MODE_GRID_CHARGING:
            limit_w = 0
        elif export_price_raw <= min_export_price:
            limit_w = 25
        else:
            limit_w = 10000

        prev_limit = self._last_export_limit
        if limit_w == prev_limit:
            return  # no change — skip the write

        inverter_id = self.config.get("foxess_inverter_id", "")
        await self._set_export_limit(inverter_id, limit_w)
        self._last_export_limit = limit_w

        # ── Solar floor log ───────────────────────────────────────────────
        # Track any entry/exit of limit_w == 25 (floor active) so the log
        # captures blocks that were already in effect at HA startup. The
        # original `prev_limit == 10000 and limit_w == 25` condition missed
        # the -1 → 25 transition that happens on every restart with low price.
        prev_was_floor = (prev_limit == 25)
        now_is_floor   = (limit_w == 25)
        if now_is_floor and not prev_was_floor:
            _LOGGER.info(
                "Solar floor activated: price %.3f ≤ floor %.2f DKK/kWh "
                "— solar export blocked (transition %s → 25)",
                export_price_raw, min_export_price, prev_limit,
            )
            self._open_floor_block(datetime.now(timezone.utc), export_price_raw, min_export_price)
        elif prev_was_floor and not now_is_floor:
            _LOGGER.info(
                "Solar floor deactivated: solar export resumed "
                "(transition 25 → %s, price %.3f, floor %.2f)",
                limit_w, export_price_raw, min_export_price,
            )
            self._close_floor_block(datetime.now(timezone.utc), export_price_raw)

        # ── Solar floor notifications (intentionally narrower) ───────────
        # Notifications fire only on direct 10000↔25 transitions — i.e. the
        # genuine "price crossed the floor" events. 0↔25 cases (grid-charge
        # start/stop while floor is active) are already covered by the
        # existing charge-start/stop notifications and would be noise here.
        if prev_limit == 10000 and limit_w == 25:
            if self._stored.get("notify_solar_floor_blocked", False):
                await self._send_mobile_notification(
                    "☀️ Solar AI: Solareksport blokeret",
                    f"Pris {export_price_raw:.3f} DKK/kWh er under gulv "
                    f"{min_export_price:.2f} — solareksport stoppet",
                )
        elif prev_limit == 25 and limit_w == 10000:
            if self._stored.get("notify_solar_floor_resumed", False):
                await self._send_mobile_notification(
                    "☀️ Solar AI: Solareksport genoptaget",
                    f"Pris {export_price_raw:.3f} DKK/kWh er over gulv "
                    f"{min_export_price:.2f} — eksport aktiv igen",
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
        rate_w = int(rate_kw * 1000)
        entity = self.config.get("foxess_force_charge_entity", "number.foxessmodbus_force_charge_power")
        try:
            await self.hass.services.async_call(
                "number", "set_value",
                {"entity_id": entity, "value": rate_w},
                blocking=True,
            )
            _LOGGER.debug("Battery Arbitrage: force charge power → %dW", rate_w)
        except Exception as err:
            _LOGGER.error("Failed to set force charge power: %s", err)

    async def _set_discharge_power(self, max_kw: float) -> None:
        """Set the Force Discharge power entity to cap grid export at max_kw."""
        rate_w = int(max_kw * 1000)
        entity = self.config.get("foxess_force_discharge_entity", FOXESS_FORCE_DISCHARGE_ENTITY)
        try:
            await self.hass.services.async_call(
                "number", "set_value",
                {"entity_id": entity, "value": rate_w},
                blocking=True,
            )
            _LOGGER.debug("Battery Arbitrage: force discharge power capped → %dW", rate_w)
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
        hour = datetime.now().hour
        hourly: list[float] = self._stored.setdefault("house_load_hourly", [0.0] * 24)
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

    def get_house_load_profile(self) -> list[float]:
        """Return the learned per-hour house load profile (kW, 24 values).

        For hours that have not been observed yet (value == 0.0), falls back
        to the short-term rolling average so the optimizer always has a
        reasonable estimate from the very first run.
        """
        profile = list(self._stored.get("house_load_hourly", [0.0] * 24))
        while len(profile) < 24:
            profile.append(0.0)
        load_history = self._stored.get("load_history", [])
        fallback = _rolling_mean(load_history, VACATION_SHORT_WINDOW) if load_history else 0.5
        return [v if v > 0.0 else round(fallback, 3) for v in profile]

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

    # ------------------------------------------------------------------ #
    # Action log (export / grid-charge session tracking)                  #
    # ------------------------------------------------------------------ #

    async def _open_action_session(
        self, now: datetime, action_type: str, soc: float, price: float
    ) -> None:
        """Open a new export or grid-charge session in the action log."""
        _CPH_TZ = ZoneInfo("Europe/Copenhagen")
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
                "☀️ Solar AI: Eksport startet",
                f"Batteri eksporterer til nettet · SoC {soc:.0f}% · {price:.2f} DKK/kWh",
            )
        # Mobile push notification — charge start
        elif action_type == "charge" and self._stored.get("notify_charge_start", False):
            await self._send_mobile_notification(
                "⚡ Solar AI: Opladning startet",
                f"Batteri oplades fra nettet · SoC {soc:.0f}% · {price:.2f} DKK/kWh",
            )

    async def _close_action_session(
        self, now: datetime, soc_end: float, capacity_kwh: float
    ) -> None:
        """Close the current open session and append the completed entry to action_log."""
        if self._open_action is None:
            return
        _CPH_TZ = ZoneInfo("Europe/Copenhagen")
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
                "☀️ Solar AI: Eksport afsluttet",
                f"SoC {soc_start:.0f}%→{soc_end:.0f}% · {duration_min} min · {kwh} kWh · {dkk} DKK",
            )
        # Mobile push notification — charge stop
        elif action_type == "charge" and self._stored.get("notify_charge_stop", False):
            await self._send_mobile_notification(
                "⚡ Solar AI: Opladning afsluttet",
                f"SoC {soc_start:.0f}%→{soc_end:.0f}% · {duration_min} min · {kwh} kWh · {dkk} DKK",
            )

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
        _CPH_TZ = ZoneInfo("Europe/Copenhagen")
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
        _CPH_TZ = ZoneInfo("Europe/Copenhagen")
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
            _LOGGER.info("EV plugged in (%s) — resetting mode to %s", charger_id, default_mode)
        self._ev_prev_connected = ev_connected

        if not ev_connected:
            self._ev_last_amps = 0
            self._ev_last_reason = f"EV not connected (status: {ocpp_status})"
            # v0.38.1 — clear any pending probe state on disconnect so the
            # next car plug-in is a fresh start. Without this, a failed
            # probe earlier in the day could leave the cool-down active
            # and block Car 2 from probing legitimately.
            if (self._ev_probe_started_at is not None
                    or self._ev_probe_cooldown_until is not None):
                self._ev_probe_started_at = None
                self._ev_probe_cooldown_until = None
            return self._ev_telemetry(0.0, 0, 0.0, ocpp_status)

        # ── Compute target ────────────────────────────────────────────────
        home_power_w = evcc_state.get("homePower", 0) or 0
        pv_power_w   = evcc_state.get("pvPower", 0) or 0
        ev_current_kw = self._get_ocpp_power_kw(charger_id)
        house_load_kw = home_power_w / 1000.0
        solar_kw      = pv_power_w / 1000.0

        # v0.36.2 — curtailment probe (replaces the v0.30.1 forecast-substitution
        # heuristic). The inverter publishes a "PV Power Limited Flag" on reg
        # 49251: 1 = MPPT actively throttling PV. When that flag is set and
        # the house battery has no headroom to absorb more (≥ max_soc − 2 %),
        # the EV controller starts a probe — it synthesises enough solar to
        # guarantee `ev_min_charge_kw` of EV demand for EV_CURTAILMENT_PROBE_SECONDS
        # so MPPT can lift to match. After the window, real PV drives the
        # target directly (no forecast involved). The flag clearing during
        # the probe ends it early (MPPT now tracking EV draw, curtailment
        # resolved). If the window expires with the flag still high, the
        # probe releases and the normal stop-window (default 180 s) backs
        # the session out within minutes.
        pv_curtailed = self._pv_power_limited_flag
        now_ts = datetime.now(timezone.utc)

        # v0.38.1 — Probe trigger: drop the `battery_near_full` precondition
        # that was added in v0.36.2. It blocked legitimate restarts in two
        # observed cases:
        #   1. Plugging in a second car after the first finished — battery
        #      had drifted a few % below max during the swap, so the gate
        #      failed even though MPPT was still curtailed.
        #   2. After clouds passed and sun returned — the battery had been
        #      covering house load during the cloud and dropped below the
        #      98% threshold, so the gate failed when curtailment resumed.
        # The stop-window safety net (180 s) backs out wrong probes within
        # minutes at a worst-case cost of ~0.07 kWh grid import — small.
        # A cool-down after failed probes (15 min, see below) caps how often
        # that can happen.
        probe_cooldown_active = (
            self._ev_probe_cooldown_until is not None
            and now_ts < self._ev_probe_cooldown_until
        )
        # v0.38.2 — Restrict the probe to fire only while Solar AI's own
        # price-floor block is open (`_current_floor_block is not None`).
        # That couples the probe 1:1 to the user-controlled price floor:
        # the EV starts on a kick-in only when the user's configured min
        # export price has been crossed and Solar AI has dropped the
        # export limit. Catches the bread-and-butter case (battery-full
        # during a price-floor period) and ignores the rare "curtailed
        # for other reasons" cases (grid-operator hard limit, faults)
        # that the EV can't reliably help with anyway. In-flight probes
        # are still allowed to run out their 60 s window if the floor
        # closes mid-probe — that avoids stuttering when the price
        # hovers near the floor.
        floor_active = self._current_floor_block is not None
        if (pv_curtailed
                and floor_active
                and self._ev_probe_started_at is None
                and not probe_cooldown_active):
            self._ev_probe_started_at = now_ts
            _LOGGER.info(
                "EV controller: PV-limited flag active (reg 49251=1) "
                "AND price-floor block open — starting %d s curtailment "
                "probe at min charge to lift MPPT.",
                EV_CURTAILMENT_PROBE_SECONDS,
            )

        # End the probe when the flag clears OR the window expires.
        probing = False
        if self._ev_probe_started_at is not None:
            elapsed = (now_ts - self._ev_probe_started_at).total_seconds()
            if not pv_curtailed:
                _LOGGER.info(
                    "EV controller: curtailment cleared after probe (%.0fs) "
                    "— MPPT now tracking EV draw; resuming normal surplus control.",
                    elapsed,
                )
                self._ev_probe_started_at = None
                # Successful probe — clear any lingering cool-down too.
                self._ev_probe_cooldown_until = None
            elif elapsed > EV_CURTAILMENT_PROBE_SECONDS:
                # Probe expired with flag still set — MPPT didn't respond.
                # Start a cool-down so we don't keep importing grid every
                # ~4 minutes (probe + stop-window cycle).
                self._ev_probe_cooldown_until = now_ts + timedelta(
                    seconds=EV_CURTAILMENT_PROBE_COOLDOWN_SECONDS,
                )
                _LOGGER.info(
                    "EV controller: probe window expired (%.0fs) with flag "
                    "still active — MPPT did not lift. Cooling down for "
                    "%d s before retry.",
                    elapsed, EV_CURTAILMENT_PROBE_COOLDOWN_SECONDS,
                )
                self._ev_probe_started_at = None
            else:
                probing = True

        # Synthesise solar during the probe window: guarantee at least
        # ev_min_charge_kw of EV demand. Real PV will reassert once the
        # probe ends. No forecast involved.
        if probing:
            non_ev_load_kw_for_probe = max(0.0, house_load_kw - ev_current_kw)
            min_kw_probe = float(self._stored.get(
                "ev_min_charge_kw", DEFAULT_EV_MIN_CHARGE_KW,
            ))
            probe_floor_kw = non_ev_load_kw_for_probe + min_kw_probe
            if solar_kw < probe_floor_kw:
                _LOGGER.debug(
                    "EV controller: probe in flight (%.0fs/%ds) — "
                    "synthesising solar %.2f → %.2f kW to keep EV at "
                    "min charge while MPPT lifts.",
                    (now_ts - self._ev_probe_started_at).total_seconds(),
                    EV_CURTAILMENT_PROBE_SECONDS,
                    solar_kw, probe_floor_kw,
                )
                solar_kw = probe_floor_kw

        # Surplus = solar minus non-EV portion of house load
        non_ev_load_kw   = max(0.0, house_load_kw - ev_current_kw)
        solar_surplus_kw = max(0.0, solar_kw - non_ev_load_kw)

        # NET surplus available to the EV (v0.27.5): the physical solar
        # surplus minus what the house battery is currently absorbing.
        # When the battery is below the priority threshold it's actively
        # taking everything left over, so the EV-available surplus is 0
        # even though there's a positive physical surplus.
        # Battery charge sensor returns kW (positive = charging).
        # We clamp to 0 if it's negative (i.e. battery discharging — that
        # case happens in PV+battery mode where battery feeds the EV).
        from .const import CONF_BATTERY_CHARGE_ENTITY, FOXESS_BATTERY_CHARGE_POWER  # noqa: PLC0415
        battery_charge_kw = max(0.0, float(self._get_float_state(
            self.config.get(CONF_BATTERY_CHARGE_ENTITY, FOXESS_BATTERY_CHARGE_POWER),
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
        )
        target_amps = self._kw_to_amps(target_kw)

        # ── Anti-flap window (time-based, v0.26.0) ────────────────────────
        final_amps = self._apply_ev_time_window(target_amps)

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

        if send:
            await self._set_ocpp_charge_rate(charger_id, final_amps)
            self._ev_last_amps = final_amps

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
                reason = (
                    f"PV: overskud {net_surplus_for_ev_kw:.1f} kW < min — "
                    f"oplader fortsætter ved minimum ({reported_target_kw:.1f} kW) "
                    f"i nedkøling ({cooling_left_s}s)"
                )
            else:
                reason = (
                    f"PV: overskud {net_surplus_for_ev_kw:.1f} kW < min — "
                    f"oplader fortsætter ved minimum ({reported_target_kw:.1f} kW)"
                )

        self._ev_last_reason = reason
        # v0.27.5: show NET surplus on the dashboard (after battery's current
        # absorption), not the raw PV-minus-house-load number. Below the
        # priority threshold this will show 0 because the battery is
        # consuming everything.
        return self._ev_telemetry(reported_target_kw, final_amps, net_surplus_for_ev_kw, reason)

    def _compute_ev_target_kw(
        self, mode: str, solar_surplus: float, battery_soc: float,
        floor_soc: float, min_kw: float, max_kw: float,
        priority_soc: float = 80.0,
    ) -> tuple[float, str]:
        """Pure mode→target translation. Returns (target_kw, human-readable reason).

        Battery-priority threshold (v0.26.4): in PV and PV+battery modes, EV
        charging is held off until `battery_soc >= priority_soc`. The inverter
        naturally diverts solar surplus to the battery while the EV target is
        0, so the battery fills first; once the threshold is reached, EV
        resumes normal surplus tracking. FULL mode ignores this (user wants
        max charge regardless of battery state).
        """
        if mode == EV_MODE_LOCKED:
            return 0.0, "Mode: Låst — ingen opladning"

        if mode == EV_MODE_FULL:
            return max_kw, f"Mode: Fuld kraft — {max_kw:.1f} kW"

        # Battery-priority gate (applies to PV mode only — v0.27.2 fix)
        # In PV+battery mode the user has *explicitly* opted in to using the
        # house battery to top the EV up to the minimum charge rate, so
        # holding the EV off while the battery is "not yet full" would
        # contradict that intent. The gate therefore only applies to pure
        # PV mode (Kun solenergi), where the user picks the threshold for
        # "how much solar to save for the house battery before sharing".
        if mode == EV_MODE_PV and battery_soc < priority_soc:
            return 0.0, (
                f"Batteri prioriteret: {battery_soc:.0f}% / {priority_soc:.0f}% "
                f"— EV venter til batteri er fyldt"
            )

        if mode == EV_MODE_PV:
            if solar_surplus >= min_kw:
                # Floor to whole amps (v0.27.2): when surplus falls *between*
                # two amp steps, command the LOWER amp so the fractional
                # surplus flows into the house battery instead of being
                # waste-exported or pulled from grid. Example: 5.4 kW surplus
                # → 7 A (4.83 kW to EV), 0.57 kW to battery.
                import math
                line_voltage_kw = EV_VOLTAGE * EV_PHASES / 1000.0  # 0.69 kW per amp
                raw_amps = math.floor(solar_surplus / line_voltage_kw)
                max_amps = max(EV_OCPP_MIN_AMPS, int(round(max_kw / line_voltage_kw)))
                amps = max(EV_OCPP_MIN_AMPS, min(max_amps, raw_amps))
                target = amps * line_voltage_kw
                excess = max(0.0, solar_surplus - target)
                if excess > 0.05:  # only show "til batteri" if meaningful
                    return target, (
                        f"PV: {solar_surplus:.2f} kW overskud → {target:.2f} kW "
                        f"({amps} A), {excess:.2f} kW til batteri"
                    )
                return target, (
                    f"PV: {solar_surplus:.2f} kW overskud → {target:.2f} kW ({amps} A)"
                )
            return 0.0, (
                f"PV: overskud {solar_surplus:.1f} kW < min {min_kw:.1f} kW — stoppet"
            )

        if mode == EV_MODE_PV_BATTERY:
            if solar_surplus >= min_kw:
                target = min(solar_surplus, max_kw)
                return target, (
                    f"PV+batteri: {solar_surplus:.1f} kW overskud → {target:.1f} kW"
                )
            # Solar can't reach min — can the battery help?
            if battery_soc > floor_soc:
                return min_kw, (
                    f"PV+batteri: sol {solar_surplus:.1f} kW utilstrækkelig, "
                    f"batteri dækker forskel → {min_kw:.1f} kW"
                )
            return 0.0, (
                f"PV+batteri: sol {solar_surplus:.1f} kW < min og batteri ved gulv — stoppet"
            )

        return 0.0, f"Ukendt mode: {mode}"

    @staticmethod
    def _kw_to_amps(kw: float) -> int:
        """Convert target kW to 3-phase line current (A), clamped to OCPP limits.

        Danish 3-phase wye system: P = 3 × V_phase × I (cos φ ≈ 1 for EVs).
        With V_phase = 230 V → P = 690 × I W → I = P / 690.
        Equivalently P = √3 × V_LL × I with V_LL = 400 V.

        Verification: 6 A → 4.14 kW (matches DEFAULT_EV_MIN_CHARGE_KW),
                     16 A → 11.04 kW (matches DEFAULT_EV_MAX_CHARGE_KW).
        """
        if kw <= 0:
            return 0
        amps = int(round(kw * 1000.0 / (EV_VOLTAGE * EV_PHASES)))
        return max(EV_OCPP_MIN_AMPS, min(EV_OCPP_MAX_AMPS, amps))

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
            if self.config.get(CONF_LIVE_DATA_SOURCE, "evcc") in ("evcc", "hybrid"):
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

            if (self.config.get(CONF_LIVE_DATA_SOURCE, "evcc") in ("evcc", "hybrid")
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
            }
        cp = self.ocpp_server.charge_points[charger_id]
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
        }

    def _apply_ev_time_window(self, target_amps: int) -> int:
        """Time-based anti-flap (v0.26.0, narrowed in v0.27.4 to PV-only).

        Anti-flap windows are ONLY needed for `pv` mode — they exist to absorb
        cloud-flicker on the solar surplus signal. In any other mode
        (LOCKED, FULL, PV+battery) the target is deterministic and changes
        only via user action, so we should respond immediately.

        For PV mode: surplus must hold ≥ min for `start_window` seconds
        before charging starts, and < min for `stop_window` seconds before
        charging stops.
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
            return target_amps
        now = datetime.now()
        start_window = int(self.config.get(
            CONF_EV_START_WINDOW_SECONDS, DEFAULT_EV_START_WINDOW_SECONDS,
        ))
        stop_window = int(self.config.get(
            CONF_EV_STOP_WINDOW_SECONDS, DEFAULT_EV_STOP_WINDOW_SECONDS,
        ))

        if target_amps == 0:
            # Want to stop ── arm the stop timer when currently charging
            if self._ev_last_amps > 0:
                if self._ev_surplus_below_min_since_ts is None:
                    self._ev_surplus_below_min_since_ts = now
                self._ev_surplus_above_min_since_ts = None  # reset start timer
                self._ev_arm_drop_since_ts = None          # not in ARMING path
                elapsed = (now - self._ev_surplus_below_min_since_ts).total_seconds()
                if elapsed >= stop_window:
                    self._ev_surplus_below_min_since_ts = None
                    return 0                              # confirmed stop
                return self._ev_last_amps                  # keep going until confirmed
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
            if self._ev_surplus_above_min_since_ts is None:
                self._ev_surplus_above_min_since_ts = now
            self._ev_surplus_below_min_since_ts = None     # reset stop timer
            self._ev_arm_drop_since_ts = None              # v0.38.5: recovered from any blip-below
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
                # Brief blip — keep the stop timer running, hold last amps.
                return self._ev_last_amps
            # Sustained recovery — surplus has held above min long enough.
            self._ev_surplus_above_min_since_ts = None
            self._ev_surplus_below_min_since_ts = None
            return target_amps

        # Already charging, no pending stop — normal live ramp.
        self._ev_surplus_above_min_since_ts = None
        self._ev_surplus_below_min_since_ts = None
        return target_amps

    async def _set_ocpp_charge_rate(self, charger_id: str, amps: int) -> None:
        """Send the target current to the charger.

        Routes through Solar AI's embedded OCPP server if the embedded toggle
        is on (v0.27.0+ default), else falls back to the legacy lbbrhzn/ocpp
        HA service for users who haven't migrated.
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
            ok = await cp.set_current(amps)
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
            interval = int(self.config.get(
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
        if self.config.get(CONF_BUY_PRICE_MODE, DEFAULT_BUY_PRICE_MODE) != BUY_PRICE_MODE_STROMLIGNING:
            return
        product_id = self.config.get(CONF_STROMLIGNING_PRODUCT_ID, "")
        supplier_id = self.config.get(CONF_STROMLIGNING_SUPPLIER_ID, "")
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
        _LOGGER.debug(
            "Strømligning prices refreshed: %d slots for product=%s, supplier=%s, area=%s",
            len(prices), product_id, supplier_id, price_area,
        )

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
        mode = self.config.get(CONF_BUY_PRICE_MODE, DEFAULT_BUY_PRICE_MODE)

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

        # Strømligning mode — lookup by hour-aligned ISO timestamp
        slot_key = slot_start_dt.astimezone(timezone.utc).replace(
            minute=0, second=0, microsecond=0,
        ).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        entry = self._cached_stromligning_prices.get(slot_key)
        if entry is None:
            # No matching slot — fall back to manual stack
            return (spot + spot_markup + tariff_this_hour_dso + elafgift) * vat_factor

        if not self.config.get(
            CONF_STROMLIGNING_USE_MANUAL_OVERRIDES, DEFAULT_STROMLIGNING_USE_MANUAL_OVERRIDES,
        ):
            # Pure Strømligning — return the all-in number directly
            try:
                return float(entry["price"]["price"]["total"])
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
        if self.config.get(CONF_BUY_PRICE_MODE, DEFAULT_BUY_PRICE_MODE) != BUY_PRICE_MODE_OCTOPUS:
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
        source = self.config.get(CONF_LIVE_DATA_SOURCE, DEFAULT_LIVE_DATA_SOURCE)

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
        source = self.config.get(CONF_SOLAR_FORECAST_SOURCE, DEFAULT_SOLAR_FORECAST_SOURCE)
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

        _CPH_TZ = ZoneInfo("Europe/Copenhagen")
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

        The DayAheadPrices dataset has 15-minute resolution (4 slots/hour).
        The optimizer averages slots within each hour, so 15-min data works
        correctly without any pre-aggregation here.

        Nord Pool day-ahead prices are published at 13:00 CET for the next
        calendar day.  We fetch today + tomorrow (limit=192 = 4×48h) so the
        full 24-h horizon is populated once tomorrow's prices are available.

        TimeDK values are local Copenhagen time (CET/CEST) without timezone
        info; we convert to UTC using the Europe/Copenhagen zone so that DST
        transitions are handled correctly year-round.
        """
        _CPH_TZ = ZoneInfo("Europe/Copenhagen")
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
                data = await resp.json(content_type=None)
        except Exception as err:
            _LOGGER.warning("EDS DayAheadPrices fetch failed (area %s): %s", price_area, err)
            return {}

        records = data.get("records", [])
        if not records:
            _LOGGER.warning("EDS DayAheadPrices: no records returned for area %s", price_area)
            return {}

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
          not the global cheapest. Stops the model from approving late-day
          exports that have no viable recharge ahead.
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
        # Precompute hourly factors (clamped, rounded already by getter)
        hourly_acc: list[float] = self.get_solar_hourly_accuracy_profile() if hasattr(self, "get_solar_hourly_accuracy_profile") else [global_acc] * 24

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

        ev_block_prob_threshold = EV_CHARGE_BLOCK_PROBABILITY
        while len(ev_charge_hourly) < 24:
            ev_charge_hourly.append(0.0)
        while len(house_load_profile) < 24:
            house_load_profile.append(0.5)
        while len(tariff_sched) < 24:
            tariff_sched.append(0.0)

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
            house_kw = house_load_profile[h]
            ev_prob = ev_charge_hourly[h]
            ev_kw = ev_prob * ev_max_kw

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
                "ev_blocked": ev_prob >= ev_block_prob_threshold,
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

        # ── Terminal value: expected revenue from SoC remaining at horizon end ──
        # Use mean sell price over the planning window as a proxy. This adapts
        # to current market conditions and prevents the optimizer from
        # discharging to floor in the last few slots just because V=0.
        sell_vals = [s["sell"] for s in slot_data if s["sell"] > 0]
        if sell_vals:
            expected_terminal_sell = max(0.0, statistics.mean(sell_vals))
        else:
            expected_terminal_sell = DEFAULT_TERMINAL_VALUE_FALLBACK

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
        # V_terminal[s] = (usable kWh at SoC s) × discharge_eff × expected_terminal_sell
        V: list[float] = []
        for s in range(SOC_STATES):
            remaining_kwh = max(0.0, (s - soc_floor) / 100.0 * capacity_kwh)
            V.append(remaining_kwh * discharge_eff * expected_terminal_sell)

        policy: list[list[str]] = [["I"] * SOC_STATES for _ in range(N)]

        for t in range(N - 1, -1, -1):
            sd = slot_data[t]
            buy_h = sd["buy"]
            sell_h = sd["sell"]
            idle_delta = sd["idle_delta_pct"]
            ev_blocked = sd["ev_blocked"]
            dur_h = sd["dur_h"]

            # Per-slot SoC step sizes (% of capacity) — duration matters at 15-min granularity
            charge_delta_slot = charge_rate_kw * charge_eff * dur_h / capacity_kwh * 100.0
            export_delta_slot = export_rate_kw * dur_h / capacity_kwh * 100.0
            charge_kwh_slot = charge_rate_kw * dur_h

            # Forward-only spread check: cheapest buy AFTER this slot
            buy_after = best_buy_after[t]
            recharge_cost_after = (
                buy_after / efficiency if efficiency > 0 else buy_after
            )
            spread_ok = (
                buy_after != float("inf")
                and sell_h - recharge_cost_after >= min_spread
            )

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
                if s < soc_max and not ev_blocked:
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
            "(SoC %d%%→%d%%, terminal_sell=%.3f, degradation=%.3f)",
            n_charge, n_export, N, horizon_hours,
            int(current_soc + 0.5), soc_s,
            expected_terminal_sell, degradation_cost,
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
            return await resp.json()

    @staticmethod
    def _make_result(mode: str = MODE_NORMAL, reason: str = "", **kwargs: Any) -> dict[str, Any]:
        return {"mode": mode, "reason": reason, **kwargs}

    async def async_restore_normal(self) -> None:
        """Force-restore normal operation (called on unload or disable)."""
        if self._current_mode != MODE_NORMAL:
            await self._transition_to(MODE_NORMAL)
            self._current_mode = MODE_NORMAL


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
        if not (now <= start < cutoff):
            continue
        if i + 1 < len(parsed):
            dur_h = (parsed[i + 1][0] - start).total_seconds() / 3600
        else:
            dur_h = 0.25  # default 15 min for the last slot
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


def _forecast_values_with_hours(
    rates: list[dict], now: datetime, hours: float
) -> list[tuple[int, float]]:
    """Return (local_hour_of_day, spot_value) pairs for slots within the forecast window.

    Used to pair each forecast slot with its correct hourly DSO tariff before
    computing buy-side price percentiles. Timestamps are converted to local time
    so the hour index matches the DatahubPricelist Price1..Price24 fields.
    """
    cutoff = now + timedelta(hours=hours)
    result: list[tuple[int, float]] = []
    for rate in rates:
        start = datetime.fromisoformat(rate["start"])
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if now <= start < cutoff:
            local_hour = start.astimezone().hour
            result.append((local_hour, rate["value"]))
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


def _predict_house_load(load_2h: float, load_28d: float, vacation_mode: bool, hours: float) -> float:
    if vacation_mode:
        hourly_kw = max(load_2h * 1.5, 0.05)
    else:
        hourly_kw = max(load_2h * 1.1, load_28d * 0.5)
    return round(hourly_kw * hours, 3)
