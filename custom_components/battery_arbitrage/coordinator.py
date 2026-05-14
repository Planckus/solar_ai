"""Data coordinator for Battery Arbitrage — the core brain."""
from __future__ import annotations

import asyncio
import logging
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CALIBRATION_MAX_SAMPLES,
    CALIBRATION_MAX_SOC,
    CALIBRATION_MIN_CHARGE_KW,
    DEFAULT_BATTERY_FLOOR_SOC,
    DEFAULT_BATTERY_MAX_SOC,
    DEFAULT_MIN_SPREAD_ARBITRAGE,
    GRID_MAX_KW,
    GRID_SAFETY_MARGIN_KW,
    GRID_MIN_CHARGE_KW,
    DEFAULT_EXPORT_DEDUCTION,
    EV_CHARGE_BLOCK_PROBABILITY,
    EV_CHARGE_THRESHOLD_W,
    EV_LEARNING_ALPHA,
    SEASON_SOLAR_THRESHOLD_KWH,
    SOLAR_DAILY_SAMPLES_MAX,
    DOMAIN,
    EVCC_API_BATTERY_MODE,
    EVCC_API_GRID,
    EVCC_API_SOLAR,
    EVCC_API_STATE,
    EV_MODE_NOW,
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
    UPDATE_INTERVAL_SECONDS,
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
)

_LOGGER = logging.getLogger(__name__)


class BatteryArbitrageCoordinator(DataUpdateCoordinator):
    """Coordinator: fetches data, runs model, executes decisions."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.config = config
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._stored: dict[str, Any] = {}
        self._current_mode = MODE_NORMAL
        self._mode_reason = ""
        self._enabled = False        # OFF by default — user enables after learning period
        self._we_set_evcc_mode = False  # True while WE have EVCC battery mode set non-normal

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
        temp = self._get_float_state(FOXESS_CELL_TEMP_LOW)
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
            self._stored.setdefault("ev_charge_hourly", [0.0] * 24)
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

        try:
            evcc_state, solar_rates, grid_rates = await asyncio.gather(
                self._fetch_json(session, f"{evcc_url}{EVCC_API_STATE}"),
                self._fetch_json(session, f"{evcc_url}{EVCC_API_SOLAR}"),
                self._fetch_json(session, f"{evcc_url}{EVCC_API_GRID}"),
            )
        except Exception as err:
            raise UpdateFailed(f"EVCC unreachable: {err}") from err

        now = datetime.now(timezone.utc)
        forecast_hours = self.config.get("forecast_hours", 24)

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

        # ---- solar accuracy: sample current slot ----
        current_forecast_w = _current_slot_forecast(solar_rates.get("rates", []), now)
        if current_forecast_w is not None and (
            current_forecast_w >= SOLAR_ACCURACY_MIN_FORECAST_W or pv_power_w >= SOLAR_ACCURACY_MIN_FORECAST_W
        ):
            self._update_solar_accuracy(current_forecast_w, pv_power_w)
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

        # ---- FoxESS state ----
        battery_soc = self._get_float_state(FOXESS_BATTERY_SOC, 0)
        cell_temp_low = self._get_float_state(FOXESS_CELL_TEMP_LOW)
        battery_charge_kw = self._get_float_state(FOXESS_BATTERY_CHARGE_POWER, 0)
        battery_discharge_kw = self._get_float_state(FOXESS_BATTERY_DISCHARGE_POWER, 0)
        current_work_mode = self.hass.states.get(FOXESS_WORK_MODE_ENTITY)
        work_mode_str = current_work_mode.state if current_work_mode else WORK_MODE_SELF_USE

        # ---- strømligning export price ----
        spot_state = self.hass.states.get(
            self.config.get("stromligning_entity", "sensor.stromligning_spotprice_ex_vat")
        )
        spot_ex_vat = (
            float(spot_state.state)
            if spot_state and spot_state.state not in ("unknown", "unavailable")
            else 0.0
        )
        export_price = max(0.0, spot_ex_vat - DEFAULT_EXPORT_DEDUCTION)

        # ---- load model ----
        self._update_load_history(base_load_kw)
        load_history = self._stored.get("load_history", [])
        load_2h_avg = _rolling_mean(load_history, VACATION_SHORT_WINDOW)
        load_28d_avg = _rolling_mean(load_history, LOAD_HISTORY_MAX_SAMPLES)
        vacation_mode = self._update_vacation_mode(load_2h_avg, load_28d_avg)
        predicted_house_load_24h = _predict_house_load(
            load_2h_avg, load_28d_avg, vacation_mode, forecast_hours
        )

        # ---- temperature learning ----
        if cell_temp_low is not None:
            self._calibrate_charge_rate(
                cell_temp_low, battery_charge_kw, battery_soc, work_mode_str
            )
        learned_charge_rate = self.get_current_charge_rate()

        # ---- EV charge pattern learning ----
        self._update_ev_charge_learning(ev_charge_power_w)
        ev_block_prob = self.get_ev_charge_probability()
        ev_likely_charging = ev_block_prob >= EV_CHARGE_BLOCK_PROBABILITY

        # ---- seasonal mode ----
        self._update_daily_solar(pv_power_w)
        is_summer_mode, solar_28d_avg = self.get_season_mode()

        # ---- battery capacity calcs ----
        floor_soc = int(self._stored.get("battery_floor_soc", self.config.get("battery_floor_soc", DEFAULT_BATTERY_FLOOR_SOC)))
        max_soc = int(self._stored.get("battery_max_soc", self.config.get("battery_max_soc", DEFAULT_BATTERY_MAX_SOC)))
        capacity_kwh = self.config.get("battery_capacity", 11.52)
        efficiency = self.config.get("round_trip_efficiency", 0.92)

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
        grid_arbitrage_spread = export_price - price_min
        min_spread = float(self._stored.get("min_spread_arbitrage", self.config.get("min_spread_arbitrage", DEFAULT_MIN_SPREAD_ARBITRAGE)))
        grid_arbitrage_worthwhile = grid_arbitrage_spread >= min_spread

        # ---- decision logic ----
        # Battery export (Feed-in First) only at top-quartile prices — preserves energy
        # for evening peak. Solar surplus already exports automatically in Self-Use mode.
        battery_export_at_peak = price_p75 > 0 and export_price >= price_p75
        should_export = (
            battery_export_at_peak
            and grid_arbitrage_worthwhile
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
            and price_next_slot <= price_p25
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

        # ---- execute action (skipped when disabled — data still reported) ----
        if self._enabled:
            new_mode, reason = await self._execute_decision(
                should_export, should_grid_charge, export_price,
                grid_arbitrage_spread, price_min, price_next_slot, price_p25, price_p75,
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

        # ---- savings tracking ----
        self._update_savings(
            new_mode, should_export, should_grid_charge,
            export_price, grid_arbitrage_spread,
            battery_discharge_kw, battery_charge_kw,
            learned_charge_rate, truly_exportable_kwh, importable_kwh,
        )
        savings = self.get_savings_summary()

        # ---- save storage periodically ----
        await self._store.async_save(self._stored)

        return self._make_result(
            mode=new_mode,
            reason=reason,
            home_power_w=home_power_w,
            pv_power_w=pv_power_w,
            ev_charge_power_w=ev_charge_power_w,
            ev_mode=ev_mode,
            ev_connected=ev_connected,
            ev_charging_now=ev_charging_now,
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
            capped_charge_rate_kw=round(capped_charge_rate_kw, 3),
            learned_rates=self.get_all_learned_rates(),
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
        price_min: float,
        price_next_slot: float,
        price_p25: float,
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
                f"Grid charging: price {price_next_slot:.2f} ≤ p25 {price_p25:.2f} DKK/kWh, "
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
            await self._transition_to(target_mode, capped_charge_rate_kw)

        self._current_mode = target_mode
        self._mode_reason = reason
        return target_mode, reason

    async def _transition_to(self, new_mode: str, capped_charge_rate_kw: float = 0.0) -> None:
        """Handle transition between operating modes."""
        _LOGGER.info("Battery Arbitrage: transitioning %s → %s", self._current_mode, new_mode)

        inverter_id = self.config.get("foxess_inverter_id", "")
        session = async_get_clientsession(self.hass)
        evcc_url = self.config["evcc_url"]

        if new_mode == MODE_EXPORTING:
            # Feed-in First: inverter pushes battery + solar to grid
            await self._set_work_mode(WORK_MODE_EXPORT)
            await self._set_export_limit(inverter_id, 10000)
            # Tell EVCC to hold so it doesn't fight our export
            self._we_set_evcc_mode = True
            await self._evcc_post(session, evcc_url, f"{EVCC_API_BATTERY_MODE}/{EVCC_BATTERY_HOLD}")

        elif new_mode == MODE_GRID_CHARGING:
            # Force Charge: inverter charges battery from grid at grid-headroom-capped rate
            await self._set_work_mode(WORK_MODE_FORCE_CHARGE)
            await self._set_charge_power(inverter_id, max_kw=capped_charge_rate_kw)
            await self._set_export_limit(inverter_id, 0)   # Don't export while buying cheap power
            self._we_set_evcc_mode = True
            await self._evcc_post(session, evcc_url, f"{EVCC_API_BATTERY_MODE}/{EVCC_BATTERY_HOLD}")

        elif new_mode == MODE_NORMAL:
            await self._set_work_mode(WORK_MODE_SELF_USE)
            await self._set_export_limit(inverter_id, 10000)
            # Release EVCC back to normal only if WE were the one who set it to hold
            if self._we_set_evcc_mode:
                self._we_set_evcc_mode = False
                await self._evcc_post(session, evcc_url, f"{EVCC_API_BATTERY_MODE}/{EVCC_BATTERY_NORMAL}")

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
        kwh_this_tick = pv_power_w / 1000 * (UPDATE_INTERVAL_SECONDS / 3600)
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
        interval_h = UPDATE_INTERVAL_SECONDS / 3600  # 5/60 h

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


def _predict_house_load(load_2h: float, load_28d: float, vacation_mode: bool, hours: float) -> float:
    if vacation_mode:
        hourly_kw = max(load_2h * 1.5, 0.05)
    else:
        hourly_kw = max(load_2h * 1.1, load_28d * 0.5)
    return round(hourly_kw * hours, 3)
