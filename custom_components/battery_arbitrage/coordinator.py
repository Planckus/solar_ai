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
        # Learning tick gate: storage-write operations run every 5 min, not every fast tick
        self._last_learning_tick: datetime | None = None
        self._vacation_mode: bool = False  # Cached between learning ticks
        # Export limit tracker — avoids unnecessary register writes; -1 forces first write
        self._last_export_limit: int = -1
        # Day-ahead DP optimizer plan — list of {hour, action, soc, buy, sell}
        self._optimizer_plan: list[dict] = []
        # Currently open export/charge session (closed when mode exits)
        self._open_action: dict | None = None

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
            }
        else:
            self._stored = data
            # Ensure all keys exist (migration safety)
            self._stored.setdefault("charge_rates", {key: default for key, _, _, default in TEMP_BUCKETS})
            self._stored.setdefault("charge_samples", {key: [] for key, _, _, _ in TEMP_BUCKETS})
            self._stored.setdefault("load_history", [])
            self._stored.setdefault("vacation_counter", 0)
            self._stored.setdefault("solar_accuracy_samples", [])
            self._stored.setdefault("savings_log", [])
            self._stored.setdefault("action_log", [])
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

        # ── Fast: fetch live EVCC state every tick ───────────────────────
        try:
            evcc_state = await self._fetch_json(session, f"{evcc_url}{EVCC_API_STATE}")
        except Exception as err:
            raise UpdateFailed(f"EVCC unreachable: {err}") from err

        # ── Hourly: refresh tariff / price data ──────────────────────────
        tariff_stale = (
            self._last_tariff_refresh is None
            or (now - self._last_tariff_refresh).total_seconds() >= TARIFF_REFRESH_INTERVAL_SECONDS
        )
        if tariff_stale:
            price_area = self.config.get(CONF_PRICE_AREA, DEFAULT_PRICE_AREA)

            # Solar forecast — best-effort; a 404 from EVCC must not block startup
            try:
                solar_data = await self._fetch_json(session, f"{evcc_url}{EVCC_API_SOLAR}")
                self._cached_solar_rates = solar_data
            except Exception as solar_err:
                _LOGGER.warning("EVCC solar forecast unavailable (%s) — using cached/empty data", solar_err)

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
        if tariff_schedule_stale:
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

        # ---- parse EVCC ----
        home_power_w = evcc_state.get("homePower", 0)
        pv_power_w = evcc_state.get("pvPower", 0)
        grid_power_w = evcc_state.get("gridPower", 0)   # positive = import, negative = export
        loadpoints = evcc_state.get("loadpoints", [{}])
        lp = loadpoints[0] if loadpoints else {}
        ev_charge_power_w = lp.get("chargePower", 0)
        ev_mode = lp.get("mode", "pv")

        # Check all loadpoints for EV presence and active non-PV charging
        ev_connected = any(lp_.get("connected", False) for lp_ in loadpoints)
        ev_charging_now = any(
            lp_.get("charging", False) and lp_.get("mode") in (EV_MODE_NOW, EV_MODE_MIN_PV)
            for lp_ in loadpoints
        )
        # EV charging purely on solar surplus (pv mode, real charge power flowing)
        ev_charging_solar = any(
            lp_.get("charging", False)
            and lp_.get("mode") == "pv"
            and lp_.get("chargePower", 0) > EV_CHARGE_THRESHOLD_W
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
        is_learning_tick = (
            self._last_learning_tick is None
            or (now - self._last_learning_tick).total_seconds() >= LEARNING_TICK_INTERVAL_SECONDS
        )
        if is_learning_tick:
            if current_forecast_w is not None and (
                current_forecast_w >= SOLAR_ACCURACY_MIN_FORECAST_W
                or pv_power_w >= SOLAR_ACCURACY_MIN_FORECAST_W
            ):
                self._update_solar_accuracy(current_forecast_w, pv_power_w)
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
        # Solar lookup: slot_start → kW (value is average Watts during the slot)
        solar_kw_by_start: dict = {s[0]: s[4] / 1000.0 for s in solar_slot_data}
        if grid_slots:
            buy_vals_sorted = sorted(
                (spot + spot_markup + tariff_sched[h] + elafgift) * vat_factor
                for h, spot in grid_slots
            )
            n_buy = len(buy_vals_sorted)
            buy_price_min = buy_vals_sorted[0]
            buy_price_p25 = buy_vals_sorted[max(0, n_buy // 4 - 1)]
            next_slot_slots = _forecast_values_with_hours(grid_rates.get("rates", []), now, 0.5)
            if next_slot_slots:
                h_next, spot_next = next_slot_slots[0]
                buy_price_next_slot = (spot_next + spot_markup + tariff_sched[h_next] + elafgift) * vat_factor
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
        export_fee = self._stored.get("export_fee", DEFAULT_EXPORT_FEE)
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
                        buy_h = (spot + spot_markup + tariff_sched[h] + elafgift) * vat_factor
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
        # The optimizer produces a 24-h plan (charge/export/idle per hour) that
        # replaces the reactive p25/p75 threshold logic for decisions.
        if tariff_stale or not self._optimizer_plan:
            max_export_kw_setting = float(self._stored.get("max_export_kw", DEFAULT_MAX_EXPORT_KW))
            self._optimizer_plan = self._run_optimizer(
                now=now,
                grid_slot_data=grid_slot_data,
                solar_slot_data=solar_slot_data,
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

        # Translate optimizer plan into flags for the current hour
        optimizer_says_export = any(
            s["hour"] == current_local_hour and s["action"] == "EXPORT"
            for s in self._optimizer_plan
        )
        optimizer_says_charge = any(
            s["hour"] == current_local_hour and s["action"] == "CHARGE"
            for s in self._optimizer_plan
        )
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
                self._close_action_session(now, battery_soc, capacity_kwh)
            if new_mode == MODE_EXPORTING:
                self._open_action_session(now, "export", battery_soc, export_price)
            elif new_mode == MODE_GRID_CHARGING:
                current_buy_price = round(
                    (spot_ex_vat + spot_markup + tariff_sched[current_local_hour] + elafgift)
                    * vat_factor,
                    4,
                )
                self._open_action_session(now, "charge", battery_soc, current_buy_price)

        # ---- export limit (every tick — enforces solar floor even when disabled) ----
        await self._maintain_export_limit(export_price_raw, min_export_price, new_mode)

        # ---- savings tracking (learning tick only — accumulates per interval_h) ----
        if is_learning_tick:
            self._update_savings(
                new_mode, should_export, should_grid_charge,
                export_price, grid_arbitrage_spread,
                battery_discharge_kw, battery_charge_kw,
                learned_charge_rate, truly_exportable_kwh, importable_kwh,
            )
        savings = self.get_savings_summary()

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
            export_price=export_price,
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
            plan_text=plan_text,
            plan_charge_hours=charge_hours,
            plan_export_hours=export_hours,
            house_load_hourly=self.get_house_load_profile(),
            ev_max_kw=float(self._stored.get("ev_max_kw", 0.0)),
            action_log=self.get_action_log(20),
            action_log_count=len(self._stored.get("action_log", [])),
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
        evcc_url = self.config["evcc_url"]

        if new_mode == MODE_EXPORTING:
            # Feed-in First: inverter pushes battery + solar to grid
            await self._set_work_mode(WORK_MODE_EXPORT)
            # Apply export power cap if configured (0 = no cap)
            max_export_kw = float(self._stored.get("max_export_kw", DEFAULT_MAX_EXPORT_KW))
            if max_export_kw > 0:
                await self._set_discharge_power(max_export_kw)
            # Tell EVCC to hold so it doesn't fight our export
            self._we_set_evcc_mode = True
            await self._evcc_post(session, evcc_url, f"{EVCC_API_BATTERY_MODE}/{EVCC_BATTERY_HOLD}")

        elif new_mode == MODE_GRID_CHARGING:
            # Force Charge: inverter charges battery from grid at grid-headroom-capped rate
            await self._set_work_mode(WORK_MODE_FORCE_CHARGE)
            await self._set_charge_power(inverter_id, max_kw=capped_charge_rate_kw)
            self._we_set_evcc_mode = True
            await self._evcc_post(session, evcc_url, f"{EVCC_API_BATTERY_MODE}/{EVCC_BATTERY_HOLD}")

        elif new_mode == MODE_NORMAL:
            await self._set_work_mode(WORK_MODE_SELF_USE)
            # Release EVCC back to normal only if WE were the one who set it to hold
            if self._we_set_evcc_mode:
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
        floor is always enforced.
        """
        if current_mode == MODE_GRID_CHARGING:
            limit_w = 0
        elif export_price_raw <= min_export_price:
            limit_w = 25
        else:
            limit_w = 10000

        if limit_w == self._last_export_limit:
            return  # no change — skip the write

        inverter_id = self.config.get("foxess_inverter_id", "")
        await self._set_export_limit(inverter_id, limit_w)
        self._last_export_limit = limit_w

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
        is_charging = ev_charge_power_w > EV_CHARGE_THRESHOLD_W
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
        if ev_charge_power_w <= EV_CHARGE_THRESHOLD_W:
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

    def _update_solar_accuracy(self, forecast_w: float, actual_w: float) -> None:
        """Append a (forecast, actual) PV power pair to the rolling sample buffer."""
        samples: list[dict] = self._stored.setdefault("solar_accuracy_samples", [])
        samples.append({"f": round(forecast_w, 0), "a": round(actual_w, 0)})
        if len(samples) > SOLAR_ACCURACY_MAX_SAMPLES:
            del samples[: len(samples) - SOLAR_ACCURACY_MAX_SAMPLES]

    # ------------------------------------------------------------------ #
    # Action log (export / grid-charge session tracking)                  #
    # ------------------------------------------------------------------ #

    def _open_action_session(
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

    def _close_action_session(
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

    def get_action_log(self, n: int = 20) -> list[dict]:
        """Return last n action log entries, newest first."""
        log: list[dict] = self._stored.get("action_log", [])
        return list(reversed(log[-n:]))

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
                now, grid_slot_data, solar_slot_data, current_soc,
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
        """Core DP computation (separated for clean error handling)."""
        # ── Build per-hour buy/sell/solar/idle arrays ─────────────────────
        # Average values across 15-min sub-slots within each hour
        buy_acc: dict[int, list[float]] = {}
        sell_acc: dict[int, list[float]] = {}
        for slot_start, dur_h, h, m, spot in grid_slot_data:
            buy_h = (spot + spot_markup + tariff_sched[h] + elafgift) * vat_factor
            sell_h = max(0.0, spot - export_fee - feed_in_tariff)
            buy_acc.setdefault(h, []).append(buy_h)
            sell_acc.setdefault(h, []).append(sell_h)

        solar_acc: dict[int, list[float]] = {}
        for slot_start, dur_h, h, m, watts in solar_slot_data:
            solar_acc.setdefault(h, []).append(watts / 1000.0)

        hours = sorted(buy_acc.keys())
        if not hours:
            return []

        # Effective export rate: use user cap if set, else same as charge rate
        export_rate_kw = max_export_kw if max_export_kw > 0 else charge_rate_kw

        # Efficiency split: assume symmetric charge/discharge
        charge_eff = efficiency ** 0.5
        discharge_eff = efficiency ** 0.5

        # Global cheapest buy price across all future hours — used for spread check
        best_buy_global = min(
            statistics.mean(buy_acc[h]) for h in hours
        )
        recharge_cost = best_buy_global / efficiency if efficiency > 0 else best_buy_global

        # ── Precompute per-hour data ──────────────────────────────────────
        hour_data: list[dict] = []
        ev_block_prob_threshold = EV_CHARGE_BLOCK_PROBABILITY
        while len(ev_charge_hourly) < 24:
            ev_charge_hourly.append(0.0)
        while len(house_load_profile) < 24:
            house_load_profile.append(0.5)
        while len(tariff_sched) < 24:
            tariff_sched.append(0.0)

        for h in hours:
            buy_h = round(statistics.mean(buy_acc[h]), 4)
            sell_h = round(statistics.mean(sell_acc[h]), 4)
            solar_kw = statistics.mean(solar_acc.get(h, [0.0]))
            house_kw = house_load_profile[h]
            ev_prob = ev_charge_hourly[h]
            ev_kw = ev_prob * ev_max_kw  # EV expected draw this hour

            # Battery idle delta: solar → house first, then EV, then battery
            # EV never draws from battery (EVCC setting) — only house drain from battery
            solar_to_house = min(solar_kw, house_kw)
            house_from_battery = max(0.0, house_kw - solar_kw)
            solar_remaining = solar_kw - solar_to_house
            solar_to_ev = min(solar_remaining, ev_kw)
            solar_to_battery = max(0.0, solar_remaining - solar_to_ev)
            idle_delta_pct = (solar_to_battery - house_from_battery) / capacity_kwh * 100.0

            # Spread viability: can we profitably export and recharge later?
            spread_ok = sell_h - recharge_cost >= min_spread

            hour_data.append({
                "h": h,
                "buy": buy_h,
                "sell": sell_h,
                "idle_delta_pct": idle_delta_pct,
                "ev_blocked": ev_prob >= ev_block_prob_threshold,
                "spread_ok": spread_ok,
            })

        N = len(hours)
        SOC_STATES = 101  # SoC 0–100 %

        # SoC step sizes per action (in % per hour)
        charge_delta_pct = charge_rate_kw * charge_eff / capacity_kwh * 100.0
        export_delta_pct = export_rate_kw / capacity_kwh * 100.0

        # Floor/max as integers
        soc_floor = int(max(0, round(floor_soc)))
        soc_max = int(min(100, round(max_soc)))

        # ── Backward induction ────────────────────────────────────────────
        # V[s] = best cumulative value from the next slot onward, starting at SoC s
        V: list[float] = [0.0] * SOC_STATES
        policy: list[list[str]] = [["I"] * SOC_STATES for _ in range(N)]

        for t in range(N - 1, -1, -1):
            hd = hour_data[t]
            buy_h = hd["buy"]
            sell_h = hd["sell"]
            idle_delta = hd["idle_delta_pct"]
            ev_blocked = hd["ev_blocked"]
            spread_ok = hd["spread_ok"]

            new_V: list[float] = [0.0] * SOC_STATES

            for s in range(SOC_STATES):
                # ── IDLE ──────────────────────────────────────────────────
                s_idle = int(max(float(soc_floor), min(float(soc_max), s + idle_delta)) + 0.5)
                s_idle = max(0, min(100, s_idle))
                best_val = V[s_idle]
                best_act = "I"

                # ── CHARGE ────────────────────────────────────────────────
                if s < soc_max and not ev_blocked:
                    s_ch = int(max(float(soc_floor), min(float(soc_max), s + charge_delta_pct + idle_delta)) + 0.5)
                    s_ch = max(0, min(100, s_ch))
                    val_ch = -charge_rate_kw * buy_h + V[s_ch]
                    if val_ch > best_val:
                        best_val = val_ch
                        best_act = "C"

                # ── EXPORT ────────────────────────────────────────────────
                if s > soc_floor and sell_h > min_export_price and spread_ok:
                    avail_pct = s - soc_floor
                    actual_exp_pct = min(export_delta_pct, avail_pct)
                    actual_exp_kw = actual_exp_pct / 100.0 * capacity_kwh
                    s_ex = int(max(float(soc_floor), min(float(soc_max), s - actual_exp_pct + idle_delta)) + 0.5)
                    s_ex = max(0, min(100, s_ex))
                    revenue = actual_exp_kw * discharge_eff * sell_h
                    val_ex = revenue + V[s_ex]
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
            hd = hour_data[t]
            h = hd["h"]
            act_code = policy[t][soc_s]
            action = _ACTION_NAMES[act_code]

            plan.append({
                "hour": h,
                "action": action,
                "soc": soc_s,
                "buy": hd["buy"],
                "sell": hd["sell"],
            })

            if act_code == "C":
                soc_s = int(max(float(soc_floor), min(float(soc_max), soc_s + charge_delta_pct + hd["idle_delta_pct"])) + 0.5)
            elif act_code == "E":
                avail_pct = soc_s - soc_floor
                actual_exp_pct = min(export_delta_pct, float(avail_pct))
                soc_s = int(max(float(soc_floor), min(float(soc_max), soc_s - actual_exp_pct + hd["idle_delta_pct"])) + 0.5)
            else:
                soc_s = int(max(float(soc_floor), min(float(soc_max), soc_s + hd["idle_delta_pct"])) + 0.5)
            soc_s = max(0, min(100, soc_s))

        n_charge = sum(1 for s in plan if s["action"] == "CHARGE")
        n_export = sum(1 for s in plan if s["action"] == "EXPORT")
        _LOGGER.debug(
            "Optimizer: %d charge slots, %d export slots over %d hours (SoC %d%%→%d%%)",
            n_charge, n_export, N, int(current_soc + 0.5), soc_s,
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
