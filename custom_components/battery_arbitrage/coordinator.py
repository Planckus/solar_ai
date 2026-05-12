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
    DEFAULT_EXPORT_DEDUCTION,
    DOMAIN,
    EVCC_API_BATTERY_MODE,
    EVCC_API_GRID,
    EVCC_API_SOLAR,
    EVCC_API_STATE,
    EV_MODE_NOW,
    FOXESS_BATTERY_CHARGE_POWER,
    FOXESS_BATTERY_SOC,
    FOXESS_CELL_TEMP_LOW,
    FOXESS_FEED_IN,
    FOXESS_FORCE_CHARGE_ENTITY,
    FOXESS_FORCE_DISCHARGE_ENTITY,
    FOXESS_LOAD_POWER,
    FOXESS_WORK_MODE_ENTITY,
    FOXESS_EXPORT_LIMIT_REGISTER,
    LOAD_HISTORY_MAX_SAMPLES,
    MIN_EXPORTABLE_KWH,
    MIN_GRID_CHARGE_KWH,
    MODE_DISABLED,
    MODE_EXPORTING,
    MODE_GRID_CHARGING,
    MODE_NORMAL,
    STORAGE_KEY,
    STORAGE_VERSION,
    STROMLIGNING_SPOTPRICE_EX_VAT,
    TEMP_BUCKETS,
    UPDATE_INTERVAL_SECONDS,
    VACATION_MIN_DURATION,
    VACATION_SHORT_WINDOW,
    VACATION_THRESHOLD,
    WORK_MODE_FORCE_CHARGE,
    WORK_MODE_FORCE_DISCHARGE,
    WORK_MODE_SELF_USE,
    EVCC_BATTERY_CHARGE,
    EVCC_BATTERY_NORMAL,
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
        self._enabled = True

    # ------------------------------------------------------------------ #
    # Public helpers                                                        #
    # ------------------------------------------------------------------ #

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

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

    def reset_learned_rates(self) -> None:
        """Reset all learned charge rates to defaults."""
        self._stored["charge_rates"] = {
            key: default for key, _, _, default in TEMP_BUCKETS
        }
        self._stored["load_history"] = []
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
            }
        else:
            self._stored = data
            # Ensure all keys exist (migration safety)
            self._stored.setdefault("charge_rates", {key: default for key, _, _, default in TEMP_BUCKETS})
            self._stored.setdefault("charge_samples", {key: [] for key, _, _, _ in TEMP_BUCKETS})
            self._stored.setdefault("load_history", [])
            self._stored.setdefault("vacation_counter", 0)

    # ------------------------------------------------------------------ #
    # Main update cycle                                                     #
    # ------------------------------------------------------------------ #

    async def _async_update_data(self) -> dict[str, Any]:
        if not self._enabled:
            return self._make_result(mode=MODE_DISABLED, reason="System disabled")

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
        loadpoints = evcc_state.get("loadpoints", [{}])
        lp = loadpoints[0] if loadpoints else {}
        ev_charge_power_w = lp.get("chargePower", 0)
        ev_mode = lp.get("mode", "pv")
        ev_connected = lp.get("connected", False)

        # Base house load (subtract EV charging)
        base_load_kw = max(0.0, (home_power_w - ev_charge_power_w) / 1000)

        # ---- solar forecast ----
        solar_kwh = _sum_forecast(solar_rates.get("rates", []), now, forecast_hours, watts=True)
        solar_kwh_6h = _sum_forecast(solar_rates.get("rates", []), now, 6, watts=True)

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
            # Next-slot price (15 min)
            next_slot_vals = _forecast_values(grid_rates.get("rates", []), now, 0.5)
            price_next_slot = next_slot_vals[0] if next_slot_vals else price_min
        else:
            price_min = price_max = price_mean = price_p25 = price_p75 = price_next_slot = 0.0

        # ---- FoxESS state ----
        battery_soc = self._get_float_state(FOXESS_BATTERY_SOC, 0)
        cell_temp_low = self._get_float_state(FOXESS_CELL_TEMP_LOW)
        battery_charge_kw = self._get_float_state(FOXESS_BATTERY_CHARGE_POWER, 0)
        current_work_mode = self.hass.states.get(FOXESS_WORK_MODE_ENTITY)
        work_mode_str = current_work_mode.state if current_work_mode else WORK_MODE_SELF_USE

        # ---- strømligning export price ----
        spot_state = self.hass.states.get(STROMLIGNING_SPOTPRICE_EX_VAT)
        spot_ex_vat = float(spot_state.state) if spot_state and spot_state.state not in ("unknown", "unavailable") else 0.0
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

        # ---- battery capacity calcs ----
        floor_soc = self.config.get("battery_floor_soc", 50)
        max_soc = self.config.get("battery_max_soc", 100)
        capacity_kwh = self.config.get("battery_capacity", 11.52)
        efficiency = self.config.get("round_trip_efficiency", 0.92)

        exportable_kwh = max(0.0, (battery_soc - floor_soc) / 100 * capacity_kwh * efficiency)
        importable_kwh = max(0.0, (max_soc - battery_soc) / 100 * capacity_kwh)

        # Net house need = predicted load minus expected solar (what battery must cover)
        net_house_need_kwh = max(0.0, predicted_house_load_24h - solar_kwh)
        truly_exportable_kwh = max(0.0, exportable_kwh - net_house_need_kwh)

        # Time to charge to target SoC
        if learned_charge_rate > 0:
            time_to_charge_h = importable_kwh / learned_charge_rate
        else:
            time_to_charge_h = 999.0

        # ---- spread calculations ----
        grid_arbitrage_spread = export_price - price_min  # sell now vs cheapest in window
        solar_export_worthwhile = export_price >= self.config.get("min_solar_export_price", 0.50)
        grid_arbitrage_worthwhile = grid_arbitrage_spread >= self.config.get("min_spread_arbitrage", 1.0)

        # ---- decision logic ----
        should_export = (
            (solar_export_worthwhile or grid_arbitrage_worthwhile)
            and truly_exportable_kwh >= MIN_EXPORTABLE_KWH
            and battery_soc > floor_soc
            and ev_mode != EV_MODE_NOW
        )

        # Don't grid-charge if solar will fill the battery anyway in 6h
        solar_will_fill = solar_kwh_6h >= importable_kwh
        should_grid_charge = (
            not should_export
            and grid_vals
            and price_next_slot <= price_p25
            and importable_kwh >= MIN_GRID_CHARGE_KWH
            and not solar_will_fill
            and battery_soc < max_soc
        )

        # ---- execute action ----
        new_mode, reason = await self._execute_decision(
            should_export, should_grid_charge, export_price,
            grid_arbitrage_spread, price_min, price_next_slot, price_p25,
            truly_exportable_kwh, importable_kwh, solar_will_fill, ev_mode
        )

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
            base_load_kw=base_load_kw,
            load_2h_avg_kw=load_2h_avg,
            load_28d_avg_kw=load_28d_avg,
            vacation_mode=vacation_mode,
            predicted_house_load_24h_kwh=predicted_house_load_24h,
            solar_kwh_24h=solar_kwh,
            solar_kwh_6h=solar_kwh_6h,
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
            learned_rates=self.get_all_learned_rates(),
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
        exportable_kwh: float,
        importable_kwh: float,
        solar_will_fill: bool,
        ev_mode: str,
    ) -> tuple[str, str]:
        """Execute the decided mode and return (mode, reason)."""
        target_mode = MODE_NORMAL
        reason = "Conditions not met for export or grid charging"

        if should_export:
            target_mode = MODE_EXPORTING
            reason = (
                f"Exporting: price {export_price:.2f} DKK/kWh, "
                f"spread vs 24h min {spread:.2f} DKK/kWh, "
                f"{exportable_kwh:.1f} kWh available"
            )
        elif should_grid_charge:
            target_mode = MODE_GRID_CHARGING
            reason = (
                f"Grid charging: price {price_next_slot:.2f} ≤ p25 {price_p25:.2f} DKK/kWh, "
                f"{importable_kwh:.1f} kWh room available"
            )
        else:
            if ev_mode == EV_MODE_NOW:
                reason = "EV fast-charging: holding battery reserve"
            elif solar_will_fill:
                reason = "Solar will fill battery: grid charging not needed"

        if target_mode != self._current_mode:
            await self._transition_to(target_mode)

        self._current_mode = target_mode
        self._mode_reason = reason
        return target_mode, reason

    async def _transition_to(self, new_mode: str) -> None:
        """Handle transition between operating modes."""
        _LOGGER.info("Battery Arbitrage: transitioning %s → %s", self._current_mode, new_mode)

        inverter_id = self.config.get("foxess_inverter_id", "")
        session = async_get_clientsession(self.hass)
        evcc_url = self.config["evcc_url"]

        if new_mode == MODE_EXPORTING:
            # Set FoxESS to Force Discharge and open export gate
            await self._set_work_mode(WORK_MODE_FORCE_DISCHARGE)
            await self._set_export_limit(inverter_id, 10000)
            # Tell EVCC to hold battery (don't let it interfere)
            await self._evcc_post(session, evcc_url, f"{EVCC_API_BATTERY_MODE}/hold")

        elif new_mode == MODE_GRID_CHARGING:
            # Set FoxESS to Self Use (solar still contributes)
            await self._set_work_mode(WORK_MODE_SELF_USE)
            # Keep export gate open for solar
            await self._set_export_limit(inverter_id, 10000)
            # Tell EVCC to force-charge battery from grid
            await self._evcc_post(session, evcc_url, f"{EVCC_API_BATTERY_MODE}/{EVCC_BATTERY_CHARGE}")

        elif new_mode == MODE_NORMAL:
            # Restore everything to defaults
            await self._set_work_mode(WORK_MODE_SELF_USE)
            await self._set_export_limit(inverter_id, 10000)
            await self._evcc_post(session, evcc_url, f"{EVCC_API_BATTERY_MODE}/{EVCC_BATTERY_NORMAL}")

    async def _set_work_mode(self, mode: str) -> None:
        """Set FoxESS work mode via HA service."""
        entity = self.config.get("foxess_work_mode_entity", FOXESS_WORK_MODE_ENTITY)
        try:
            await self.hass.services.async_call(
                "select", "select_option",
                {"entity_id": entity, "option": mode},
                blocking=True,
            )
        except Exception as err:
            _LOGGER.error("Failed to set FoxESS work mode to %s: %s", mode, err)

    async def _set_export_limit(self, inverter_id: str, limit_watts: int) -> None:
        """Write the FoxESS export limit register."""
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
        except Exception as err:
            _LOGGER.error("Failed to set export limit: %s", err)

    async def _evcc_post(self, session: aiohttp.ClientSession, base_url: str, path: str) -> None:
        """POST to EVCC API."""
        try:
            async with session.post(f"{base_url}{path}", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status >= 400:
                    _LOGGER.warning("EVCC POST %s returned %s", path, resp.status)
        except Exception as err:
            _LOGGER.error("EVCC POST %s failed: %s", path, err)

    # ------------------------------------------------------------------ #
    # Learning model                                                        #
    # ------------------------------------------------------------------ #

    def _update_load_history(self, base_load_kw: float) -> None:
        """Append current base load to ring buffer."""
        history: list[float] = self._stored.setdefault("load_history", [])
        history.append(round(base_load_kw, 3))
        if len(history) > LOAD_HISTORY_MAX_SAMPLES:
            del history[: len(history) - LOAD_HISTORY_MAX_SAMPLES]

    def _update_vacation_mode(self, load_2h: float, load_28d: float) -> bool:
        """Update vacation counter and return vacation_mode flag."""
        counter: int = self._stored.get("vacation_counter", 0)
        baseline = load_28d if load_28d > 0.05 else 0.2  # guard against cold-start

        if load_2h < baseline * VACATION_THRESHOLD:
            counter = min(counter + 1, VACATION_MIN_DURATION + 1)
        else:
            counter = max(counter - 1, 0)

        self._stored["vacation_counter"] = counter
        return counter >= VACATION_MIN_DURATION

    def _calibrate_charge_rate(
        self,
        cell_temp: float,
        charge_kw: float,
        soc: float,
        work_mode: str,
    ) -> None:
        """Update learned max charge rate for current temperature bucket."""
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
            # Use 90th percentile — robust to occasional low readings
            idx = int(0.90 * len(samples))
            learned = sorted(samples)[idx]
            self._stored["charge_rates"][bucket] = round(learned, 3)
            _LOGGER.debug(
                "Calibrated charge rate for %s: %.2f kW (from %d samples)",
                bucket, learned, len(samples)
            )

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
    """Return the temperature bucket key for a given temperature."""
    for key, min_c, max_c, _ in TEMP_BUCKETS:
        if (min_c is None or temp_c >= min_c) and (max_c is None or temp_c < max_c):
            return key
    return None


def _forecast_values(
    rates: list[dict],
    now: datetime,
    hours: float,
) -> list[float]:
    """Return rate values within the next `hours` hours from now."""
    cutoff = now + timedelta(hours=hours)
    result = []
    for rate in rates:
        start = datetime.fromisoformat(rate["start"])
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if now <= start < cutoff:
            result.append(rate["value"])
    return result


def _sum_forecast(
    rates: list[dict],
    now: datetime,
    hours: float,
    watts: bool = False,
) -> float:
    """Sum forecast values over the next `hours` hours.

    If watts=True, values are in W for 15-min slots → convert to kWh.
    """
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
    """Return the mean of the last `window` samples."""
    if not history:
        return 0.0
    relevant = history[-window:]
    return round(statistics.mean(relevant), 3) if relevant else 0.0


def _predict_house_load(
    load_2h: float,
    load_28d: float,
    vacation_mode: bool,
    hours: float,
) -> float:
    """Predict total house load (kWh) over the next `hours` hours."""
    if vacation_mode:
        # Minimal buffer — nobody home
        hourly_kw = max(load_2h * 1.5, 0.05)
    else:
        # Use the higher of short-term and half the long-term baseline
        # Short-term captures current activity; long-term captures full-day patterns
        hourly_kw = max(load_2h * 1.1, load_28d * 0.5)

    return round(hourly_kw * hours, 3)
