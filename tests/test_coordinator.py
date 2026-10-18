"""Unit tests for Battery Arbitrage coordinator pure functions."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.battery_arbitrage.coordinator import (
    BatteryArbitrageCoordinator,
    _forecast_slots,
    _forecast_values,
    _rolling_mean,
    _sum_forecast,
    _temp_bucket,
)


class TestEvAvailableSurplus:
    """Export-aware available-surplus signal (v0.59.0)."""

    # args: ev_draw, export, import, batt_charge, batt_discharge, soc, priority
    f = staticmethod(BatteryArbitrageCoordinator._ev_available_surplus_kw)

    def test_idle_while_exporting_makes_power_available(self):
        # Battery full, car idle, 4.4 kW exporting → ~4.4 kW available (restart).
        assert self.f(0.0, 4.4, 0.0, 0.0, 0.0, 100, 80) == pytest.approx(4.4)

    def test_conserved_while_charging(self):
        # Car 2.8 kW + 0.7 kW export = 3.5 kW; conserved as the car ramps.
        assert self.f(2.8, 0.7, 0.0, 0.0, 0.0, 100, 80) == pytest.approx(3.5)

    def test_battery_charge_counts_above_priority_soc(self):
        # 99% >= 80% priority → power into the battery is available to the car.
        assert self.f(2.8, 0.0, 0.0, 1.46, 0.0, 99, 80) == pytest.approx(4.26)

    def test_battery_has_priority_below_threshold(self):
        # 70% < 80% → battery charging is NOT available; car waits.
        assert self.f(0.0, 0.0, 0.0, 4.5, 0.0, 70, 80) == 0.0

    def test_battery_discharge_subtracted(self):
        # Car drawing 4.5 kW but 1.7 kW of it is from the battery → only 2.8 kW
        # is solar. Without this the car over-commits (3-phase, drains battery).
        assert self.f(4.5, 0.0, 0.0, 0.0, 1.7, 100, 80) == pytest.approx(2.8)

    def test_grid_import_reduces_available(self):
        assert self.f(3.0, 0.0, 1.0, 0.0, 0.0, 100, 80) == pytest.approx(2.0)

    def test_clamped_non_negative(self):
        assert self.f(0.0, 0.0, 2.0, 0.0, 0.0, 100, 80) == 0.0


# ------------------------------------------------------------------ #
# _temp_bucket                                                         #
# ------------------------------------------------------------------ #

class TestTempBucket:
    def test_below_zero(self):
        assert _temp_bucket(-5.0) == "below_0"

    def test_zero_boundary(self):
        assert _temp_bucket(0.0) == "0_to_5"

    def test_boundary_6(self):
        assert _temp_bucket(6.0) == "6_to_15"

    def test_mid_bucket(self):
        assert _temp_bucket(15.0) == "6_to_15"

    def test_boundary_16(self):
        assert _temp_bucket(16.0) == "16_to_21"

    def test_upper_bucket(self):
        assert _temp_bucket(25.0) == "21_to_35"

    def test_boundary_35(self):
        assert _temp_bucket(35.0) == "35_to_50"

    def test_above_50(self):
        assert _temp_bucket(55.0) == "above_50"


# ------------------------------------------------------------------ #
# _rolling_mean                                                        #
# ------------------------------------------------------------------ #

class TestRollingMean:
    def test_empty(self):
        assert _rolling_mean([], 10) == 0.0

    def test_smaller_than_window(self):
        assert _rolling_mean([1.0, 2.0, 3.0], 10) == 2.0

    def test_exactly_window(self):
        assert _rolling_mean([1.0, 2.0, 3.0], 3) == 2.0

    def test_larger_than_window(self):
        # Only uses last 2 values
        assert _rolling_mean([100.0, 1.0, 2.0], 2) == 1.5


# ------------------------------------------------------------------ #
# _forecast_values                                                     #
# ------------------------------------------------------------------ #

class TestForecastValues:
    def _make_rates(self, offsets_and_values):
        now = datetime.now(timezone.utc)
        return [
            {"start": (now + timedelta(minutes=offset)).isoformat(), "value": val}
            for offset, val in offsets_and_values
        ]

    def test_empty_rates(self):
        now = datetime.now(timezone.utc)
        assert _forecast_values([], now, 24) == []

    def test_all_within_window(self):
        now = datetime.now(timezone.utc)
        rates = self._make_rates([(15, 1.0), (30, 2.0), (45, 3.0)])
        result = _forecast_values(rates, now, 2)
        assert result == [1.0, 2.0, 3.0]

    def test_past_rates_excluded(self):
        now = datetime.now(timezone.utc)
        rates = self._make_rates([(-30, 0.5), (15, 1.0), (30, 2.0)])
        result = _forecast_values(rates, now, 2)
        assert result == [1.0, 2.0]

    def test_beyond_window_excluded(self):
        now = datetime.now(timezone.utc)
        rates = self._make_rates([(15, 1.0), (200, 9.9)])
        result = _forecast_values(rates, now, 2)
        assert result == [1.0]


# ------------------------------------------------------------------ #
# _sum_forecast                                                        #
# ------------------------------------------------------------------ #

class TestSumForecast:
    def test_watts_conversion(self):
        """2000 W for one 15-min slot = 0.5 kWh."""
        now = datetime.now(timezone.utc)
        rates = [{"start": (now + timedelta(minutes=5)).isoformat(), "value": 2000}]
        result = _sum_forecast(rates, now, 1, watts=True)
        assert abs(result - 0.5) < 0.001

    def test_no_conversion(self):
        now = datetime.now(timezone.utc)
        rates = [{"start": (now + timedelta(minutes=5)).isoformat(), "value": 1.5}]
        result = _sum_forecast(rates, now, 1, watts=False)
        assert result == 1.5


# ------------------------------------------------------------------ #
# v0.47.5 — _forecast_slots includes the in-progress slot              #
# ------------------------------------------------------------------ #

class TestForecastSlotsInProgress:
    """The slot currently in progress must be slot 0 so the decision logic can
    match the current (hour, minute-bucket) and execute the planned action."""

    _RATES = [
        {"start": "2026-06-01T00:00:00+00:00", "value": 1.0},
        {"start": "2026-06-01T00:15:00+00:00", "value": 2.0},
        {"start": "2026-06-01T00:30:00+00:00", "value": 3.0},
    ]

    def test_includes_in_progress_slot(self):
        now = datetime(2026, 6, 1, 0, 7, tzinfo=timezone.utc)  # mid 00:00 slot
        slots = _forecast_slots(self._RATES, now, 2)
        # First slot is the in-progress 00:00 slot, not 00:15.
        assert slots[0][4] == 1.0
        assert slots[0][0] == datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)

    def test_excludes_already_ended_slot(self):
        now = datetime(2026, 6, 1, 0, 20, tzinfo=timezone.utc)  # 00:00 slot ended 00:15
        slots = _forecast_slots(self._RATES, now, 2)
        assert all(s[4] != 1.0 for s in slots)   # ended slot dropped
        assert slots[0][4] == 2.0                 # 00:15 slot (ends 00:30 > now) kept

    def test_slot_exactly_at_boundary(self):
        now = datetime(2026, 6, 1, 0, 15, tzinfo=timezone.utc)  # exactly at 00:15
        slots = _forecast_slots(self._RATES, now, 2)
        # 00:00 ended at 00:15 (<= now) → dropped; 00:15 is the current slot.
        assert slots[0][4] == 2.0


# ------------------------------------------------------------------ #
# v0.47.5 — _predict_house_load_window (profile-based, no spike blow-up)#
# ------------------------------------------------------------------ #

class TestPredictHouseLoadWindow:
    """Projects from the learned hourly profile; a short-term spike is bounded
    by the recent-activity scaler instead of being multiplied across 24 h."""

    def _call(self, profile_kw, *, hours, vacation, load_2h):
        import types
        from custom_components.battery_arbitrage.coordinator import (
            BatteryArbitrageCoordinator,
        )
        stub = types.SimpleNamespace(
            get_house_load_profile=lambda weekend=None: [profile_kw] * 24
        )
        now = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
        return BatteryArbitrageCoordinator._predict_house_load_window(
            stub, now, hours, vacation, load_2h
        )

    def test_profile_sum_when_recent_matches(self):
        # Flat 0.5 kW profile, recent load matches → ~0.5 * 24 = 12 kWh.
        assert self._call(0.5, hours=24, vacation=False, load_2h=0.5) == pytest.approx(12.0, abs=0.1)

    def test_spike_is_bounded_not_extrapolated(self):
        # 0.5 kW profile but a 2.0 kW recent spike: old code → 2.0*1.1*24 ≈ 53.
        # New code caps the scaler at 1.4 → 12 * 1.4 = 16.8, not ~48–53.
        out = self._call(0.5, hours=24, vacation=False, load_2h=2.0)
        assert out == pytest.approx(16.8, abs=0.1)
        assert out < 20.0

    def test_low_recent_scales_down_bounded(self):
        # Very low recent load → scaler floored at 0.8, not 0.
        assert self._call(0.5, hours=24, vacation=False, load_2h=0.0) == pytest.approx(12.0, abs=0.1)
        assert self._call(0.5, hours=24, vacation=False, load_2h=0.1) == pytest.approx(12.0 * 0.8, abs=0.1)

    def test_vacation_tracks_low_live_load(self):
        # Away: ignore the profile, track the (low) live load with a floor.
        assert self._call(0.5, hours=24, vacation=True, load_2h=0.2) == pytest.approx(0.2 * 24, abs=0.1)
        assert self._call(0.5, hours=24, vacation=True, load_2h=0.0) == pytest.approx(0.05 * 24, abs=0.1)


# ------------------------------------------------------------------ #
# _msg — bilingual user-facing strings (v0.41.0)                       #
# ------------------------------------------------------------------ #

class TestMsgLanguage:
    """The _msg helper picks Danish or English by the resolved language."""

    def _call(self, lang, en, da):
        import types
        from custom_components.battery_arbitrage.coordinator import (
            BatteryArbitrageCoordinator,
        )
        stub = types.SimpleNamespace(_lang=lang)
        return BatteryArbitrageCoordinator._msg(stub, en, da)

    def test_english(self):
        assert self._call("en", "English", "Dansk") == "English"

    def test_danish(self):
        assert self._call("da", "English", "Dansk") == "Dansk"


# ------------------------------------------------------------------ #
# v0.43.0 — solar-forecast percentiles + prediction scorecard          #
# ------------------------------------------------------------------ #

class TestSolarPercentile:
    """get_solar_hour_percentile returns clamped ratio percentiles, or None
    when the bucket is below the minimum sample count."""

    def _stub(self, samples):
        import types
        return types.SimpleNamespace(
            _stored={"solar_accuracy_by_hour": {"12": samples}}
        )

    def _call(self, samples, p):
        from custom_components.battery_arbitrage.coordinator import (
            BatteryArbitrageCoordinator,
        )
        return BatteryArbitrageCoordinator.get_solar_hour_percentile(
            self._stub(samples), 12, p,
        )

    def test_cold_bucket_returns_none(self):
        # Fewer than SOLAR_ACCURACY_HOUR_MIN_SAMPLES (8) → None.
        samples = [{"f": 1000, "a": 1000} for _ in range(5)]
        assert self._call(samples, 50) is None

    def test_median_of_perfect_forecast_is_one(self):
        samples = [{"f": 1000, "a": 1000} for _ in range(10)]
        assert self._call(samples, 50) == 1.0

    def test_low_percentile_below_high(self):
        # ratios 0.5 … 1.4 → P10 should be well below P90.
        samples = [{"f": 1000, "a": 500 + i * 100} for i in range(10)]
        p10 = self._call(samples, 10)
        p90 = self._call(samples, 90)
        assert p10 < p90
        assert 0.3 <= p10 <= 1.5 and 0.3 <= p90 <= 1.5

    def test_samples_below_comparison_threshold_ignored(self):
        # f below SOLAR_ACCURACY_COMPARISON_W (100) don't count → still cold.
        samples = [{"f": 50, "a": 50} for _ in range(20)]
        assert self._call(samples, 50) is None

    def test_p50_equals_median_neutral_default(self):
        # S1 neutrality guarantee: confidence=50 must equal the per-hour factor
        # (the forecast-weighted median since v1.21.1), so the default knob
        # value is a no-op.
        from custom_components.battery_arbitrage.coordinator import (
            BatteryArbitrageCoordinator,
        )
        for n in (9, 10, 13, 20):
            samples = [{"f": 1000 + i * 250, "a": 400 + i * 60} for i in range(n)]
            expected = BatteryArbitrageCoordinator.get_solar_accuracy_factor_for_hour(
                self._stub(samples), 12)
            assert self._call(samples, 50) == expected


# ------------------------------------------------------------------ #
# v0.45.0 — E1 session-aware EV demand                                 #
# ------------------------------------------------------------------ #

class TestEvSessionDemand:
    """_ev_session_demand_kw returns live demand only for forced-draw sessions."""

    def _call(self, **kw):
        from custom_components.battery_arbitrage.coordinator import (
            BatteryArbitrageCoordinator,
        )
        base = dict(
            connected=True, charging_now=False, effective_mode="pv",
            requested_mode="pv", live_kw=0.0, max_kw=11.0,
        )
        base.update(kw)
        return BatteryArbitrageCoordinator._ev_session_demand_kw(**base)

    def test_disconnected_is_zero(self):
        assert self._call(connected=False, charging_now=True, live_kw=7.0) == 0.0

    def test_pure_pv_is_zero(self):
        # Connected, pv mode, not "charging_now" → handled by idle dynamics.
        assert self._call(effective_mode="pv", requested_mode="pv") == 0.0

    def test_fast_mode_uses_live_power(self):
        assert self._call(effective_mode="full", live_kw=7.4) == 7.4

    def test_fast_mode_falls_back_to_max_when_idle(self):
        # Forced session but not drawing yet (just plugged) → learned max.
        assert self._call(effective_mode="full", live_kw=0.0, max_kw=11.0) == 11.0

    def test_charging_now_counts(self):
        assert self._call(charging_now=True, live_kw=3.6) == 3.6

    def test_evcc_now_mode_counts(self):
        assert self._call(requested_mode="now", live_kw=5.0) == 5.0


# ------------------------------------------------------------------ #
# v0.46.0 — L1 weekday/weekend house-load split                        #
# ------------------------------------------------------------------ #

class TestHouseLoadProfileSplit:
    """The EMA profile returns the requested day type with layered fallback
    (own → legacy combined → other type → rolling mean). Since v1.23.0 it is
    the per-hour fallback of `get_house_load_profile`."""

    def _call(self, stored, weekend):
        import types
        from custom_components.battery_arbitrage.coordinator import (
            BatteryArbitrageCoordinator,
        )
        stub = types.SimpleNamespace(_stored=stored)
        return BatteryArbitrageCoordinator._ema_house_load_profile(stub, weekend=weekend)

    def test_returns_requested_day_type(self):
        stored = {
            "house_load_weekday": [1.0] * 24,
            "house_load_weekend": [2.0] * 24,
        }
        assert self._call(stored, weekend=False)[12] == 1.0
        assert self._call(stored, weekend=True)[12] == 2.0

    def test_cold_hour_falls_back_to_legacy(self):
        stored = {
            "house_load_weekday": [0.0] * 24,
            "house_load_weekend": [0.0] * 24,
            "house_load_hourly": [3.0] * 24,
        }
        assert self._call(stored, weekend=False)[8] == 3.0

    def test_cold_falls_back_to_other_day_type(self):
        stored = {
            "house_load_weekday": [0.0] * 24,
            "house_load_weekend": [2.5] * 24,
            "house_load_hourly": [0.0] * 24,
        }
        # Weekday cold, no legacy → borrow the weekend curve rather than guess.
        assert self._call(stored, weekend=False)[8] == 2.5

    def test_all_cold_uses_rolling_mean_fallback(self):
        stored = {"load_history": [0.4] * 50}
        # No profiles at all → short-term rolling mean (0.4).
        assert self._call(stored, weekend=False)[8] == 0.4


class TestPredictionScorecard:
    """get_prediction_accuracy_summary computes SoC MAE over the recent log."""

    def _call(self, log):
        import types
        from custom_components.battery_arbitrage.coordinator import (
            BatteryArbitrageCoordinator,
        )
        stub = types.SimpleNamespace(
            _stored={"prediction_log": log, "solar_accuracy_by_hour": {}}
        )
        return BatteryArbitrageCoordinator.get_prediction_accuracy_summary(stub)

    def test_empty_log(self):
        out = self._call([])
        assert out["prediction_soc_mae_7d"] == 0.0
        assert out["prediction_samples"] == 0

    def test_mae_computation(self):
        log = [
            {"slot": "s1", "pred_soc": 50, "act_soc": 52, "pred_action": "IDLE"},
            {"slot": "s2", "pred_soc": 60, "act_soc": 56, "pred_action": "CHARGE"},
        ]
        out = self._call(log)
        # |50-52| + |60-56| = 2 + 4 → mean 3.0
        assert out["prediction_soc_mae_7d"] == 3.0
        assert out["prediction_samples"] == 2
        assert out["prediction_action_mix"]["CHARGE"] == 1


class TestPlannerSunFill:
    """v1.21.1 — the planner does not buy grid power the sun will supply."""

    TZ = timezone(timedelta(hours=2))

    def _plan(self, *, solar_kw, ev_session_kw=0.0, ev_session_h=2.0, ev_priority_soc=80.0,
              soc=66.0, ev_hours=range(11, 17), ev_pv_stop_kw=1.38, tail_kw=None,
              ev_ignore_session=False):
        # A clear afternoon: cheap at 13:30-14:15, expensive from 17:00. A PV
        # car is learned to charge 11-16 h, which the planner used to read as
        # the sun being gone and buy the battery's top-up from the grid.
        now = datetime(2026, 9, 30, 13, 30, tzinfo=self.TZ)
        grid, solar = [], []
        for i in range(42):  # 13:30 .. 23:45
            start = now + timedelta(minutes=15 * i)
            spot = 0.05 if start.hour < 15 else 1.5
            grid.append((start, 0.25, start.hour, start.minute, spot))
            hours_to_sunset = max(0.0, 19.5 - (start.hour + start.minute / 60))
            kw = min(solar_kw, solar_kw * hours_to_sunset / 3)
            if tail_kw is not None and start.hour >= 16:
                kw = tail_kw if hours_to_sunset > 0 else 0.0
            solar.append((start, 0.25, start.hour, start.minute, 1000.0 * kw))
        c = object.__new__(BatteryArbitrageCoordinator)
        c._stored = {"battery_degradation_cost": 0.05}
        c.get_solar_hour_percentile = lambda h, p: None
        c.get_short_term_solar_factor = lambda h: 1.0
        c._compute_buy_price = lambda **k: k["spot"] * 1.25 + 0.3
        ev_hourly = [0.0] * 24
        for h in ev_hours:
            ev_hourly[h] = 0.5
        plan = c._dp_solve(
            now, grid, solar, 1.0, soc, 10.67, 85, 13, ev_priority_soc, 100, 0.926,
            9.81, 17.0, [0.7] * 24, ev_hourly, 10.4, 1.25, [0.0] * 24, 0.0, 0.0,
            0.0, 0.0, 0.03, 2.15, 10.0, ev_session_kw, ev_session_h,
            ev_pv_stop_kw=ev_pv_stop_kw, ev_ignore_session=ev_ignore_session,
        )
        return [p for p in plan if p["action"] == "CHARGE"]

    def test_sunny_afternoon_pv_car_no_grid_buy(self):
        assert self._plan(solar_kw=5.0) == []

    def test_cloudy_afternoon_still_buys_cheap(self):
        assert self._plan(solar_kw=0.5) != []

    def test_forced_car_session_counts_against_the_sun(self):
        # Full mode through sunset: the car's 11 kW draw is real, so the sun
        # cannot fill the battery and the cheap buy stays available.
        assert self._plan(
            solar_kw=5.0, ev_session_kw=11.0, ev_session_h=8.0, ev_priority_soc=0.0,
        ) != []

    def test_pv_battery_session_is_not_planned_for(self):
        # PV+battery: the car takes the sun first and the battery only covers
        # the rest. Reserving its 4 kW draw made the sun look spoken for and
        # bought grid power at midday. The session is not
        # planned for; the live SoC carries what the car really took.
        kw = dict(solar_kw=5.0, ev_session_kw=4.0, ev_session_h=2.0,
                  ev_priority_soc=0.0, ev_hours=range(11, 21))
        assert self._plan(**kw, ev_ignore_session=True) == []
        assert self._plan(**kw) != []

    def test_pv_car_stop_leaves_the_tail_to_the_battery(self):
        # Car learned to charge until sunset. Above 80 % it takes the surplus,
        # but from 16:00 the sun gives 1.2 kW, below the car's 1.38 kW minimum:
        # the car stops and the weak afternoon tops up the battery, so there
        # is nothing to buy. Without the stop the car would keep that sun and
        # the planner would buy.
        kw = dict(solar_kw=5.0, soc=88.0, ev_hours=range(11, 21), tail_kw=1.2)
        assert self._plan(**kw) == []
        assert self._plan(**kw, ev_pv_stop_kw=0.0) != []


class TestPlannerSolarAndDrain:
    """v1.21.1 — 30-min solar under 15-min prices, fractional SoC, weighted factors."""

    TZ = timezone(timedelta(hours=2))

    def _coord(self):
        c = object.__new__(BatteryArbitrageCoordinator)
        c._stored = {"battery_degradation_cost": 0.05}
        c.get_solar_hour_percentile = lambda h, p: None
        c.get_short_term_solar_factor = lambda h: 1.0
        c._compute_buy_price = lambda **k: 1.0
        return c

    def _solve(self, c, now, solar, house_kw, soc):
        grid = [(now + timedelta(minutes=15 * i), 0.25,
                 (now + timedelta(minutes=15 * i)).hour,
                 (now + timedelta(minutes=15 * i)).minute, 0.5) for i in range(32)]
        return c._dp_solve(
            now, grid, solar, 1.0, soc, 10.0, 90, 10, 0, 100, 1.0, 5.0, 17.0,
            [house_kw] * 24, [0.0] * 24, 0.0, 1.25, [0.0] * 24, 0.0, 0.0,
            0.0, 0.0, 0.03, 2.15, 10.0,
        )

    def test_half_hour_solar_covers_quarter_hour_slots(self):
        # 2 kW sun in 30-min periods, 0.5 kW house: the battery gains
        # 1.5 kW for all 8 quarter hours, not only the :00 and :30 ones.
        now = datetime(2026, 10, 1, 11, 0, tzinfo=self.TZ)
        solar = [(now + timedelta(minutes=30 * i), 0.5, 0, 0, 2000.0) for i in range(4)]
        plan = self._solve(self._coord(), now, solar, 0.5, 50.0)
        assert plan[8]["soc"] == pytest.approx(80, abs=1)  # 65 when only half counted

    def test_evening_drain_is_not_rounded_to_one_percent(self):
        # 0.6 kW house on a 10 kWh battery is 6 %/h. Rounding each quarter
        # hour to a whole percent used to report 4 %/h.
        now = datetime(2026, 9, 30, 20, 0, tzinfo=self.TZ)
        plan = self._solve(self._coord(), now, [], 0.6, 80.0)
        assert plan[16]["soc"] == pytest.approx(56, abs=1)

    def test_solar_factor_weighted_by_forecast(self):
        from custom_components.battery_arbitrage.coordinator import (
            _weighted_ratio_percentile,
        )
        # Eight clear-day samples at 0.9 and eight tiny-forecast samples at 3x.
        bucket = [{"f": 3000.0, "a": 2700.0}] * 8 + [{"f": 120.0, "a": 360.0}] * 8
        assert _weighted_ratio_percentile(bucket, 50.0) == pytest.approx(0.9)

    def test_house_use_factor_scales_planned_drain(self):
        # Factor 1.5 plans 0.6 kW as 0.9 kW: 9 %/h on a 10 kWh battery.
        now = datetime(2026, 9, 30, 20, 0, tzinfo=self.TZ)
        c = self._coord()
        c._stored["planner_house_load_factor"] = 1.5
        plan = self._solve(c, now, [], 0.6, 80.0)
        assert plan[8]["soc"] == pytest.approx(62, abs=1)


class TestHouseLoadForecast:
    """v1.23.0 — weighted 28-day house load profile, same-day correction, scorecard."""

    def _coord(self, hours):
        c = object.__new__(BatteryArbitrageCoordinator)
        c._stored = {
            "house_load_hours": hours,
            "house_load_weekday": [0.5] * 24,
            "house_load_weekend": [0.5] * 24,
        }
        c._house_profile_cache = None
        return c

    @staticmethod
    def _hours(start, ndays, kw_fn):
        out = {}
        for k in range(ndays):
            d = start - timedelta(days=k + 1)
            for h in range(24):
                out[f"{d.isoformat()}T{h:02d}"] = [kw_fn(d, h) * 12, 12]
        return out

    def test_recent_days_weigh_more(self):
        now = datetime(2026, 10, 7, 12, 0)  # Wednesday
        # Weekdays: 1.0 kW in the last week, 0.2 kW before that.
        hours = self._hours(now.date(), 28, lambda d, h: 1.0 if (now.date() - d).days <= 7 else 0.2)
        prof = self._coord(hours).get_house_load_profile(weekend=False, now=now)
        assert 0.6 < prof[18] < 1.0

    def test_falls_back_to_ema_without_history(self):
        now = datetime(2026, 10, 7, 12, 0)
        hours = self._hours(now.date(), 2, lambda d, h: 3.0)
        prof = self._coord(hours).get_house_load_profile(weekend=False, now=now)
        assert prof[18] == 0.5

    def test_today_correction_window_and_clamp(self):
        now = datetime(2026, 10, 7, 17, 5)
        hours = self._hours(now.date(), 28, lambda d, h: 0.5)
        for h in range(11, 17):  # today ran at 4x the forecast
            hours[f"{now.date().isoformat()}T{h:02d}"] = [2.0 * 12, 12]
        c = self._coord(hours)
        assert c._house_today_factor(now) == pytest.approx(2 ** 0.5, abs=0.001)
        assert c._house_today_factor(now.replace(hour=12)) == 1.0

    def test_scorecard_logs_at_17_and_scores_next_day(self):
        day = datetime(2026, 10, 7, 17, 0)
        hours = self._hours(day.date(), 28, lambda d, h: 0.5)
        for h in range(11, 24):
            hours[f"{day.date().isoformat()}T{h:02d}"] = [0.5 * 12, 12]
        c = self._coord(hours)
        c._update_house_forecast_scorecard(day)
        c._update_house_forecast_scorecard(day + timedelta(hours=8))
        summary = c.get_house_forecast_summary()
        assert summary["house_forecast_samples"] == 1
        assert summary["house_forecast_mae_new"] == pytest.approx(0.0, abs=0.01)

    def test_zero_reading_is_not_recorded(self):
        c = self._coord({})
        now = datetime(2026, 10, 7, 15, 46)
        c._record_house_load_hour(now, 0.0)
        c._record_house_load_hour(now, 1.2)
        assert c._stored["house_load_hours"]["2026-10-07T15"] == [1.2, 1]

    @staticmethod
    def _learn_at(c, when, kw, soc):
        from unittest.mock import patch
        with patch(
            "custom_components.battery_arbitrage.coordinator.datetime",
            wraps=datetime,
        ) as dt_mock:
            dt_mock.now.return_value = when
            c._update_house_load_hourly(kw, soc)

    def test_peak_hour_starting_low_is_not_learned(self):
        # v1.23.2 — 18:00 starts at 25 %: the whole hour is skipped, even after
        # the SoC reads higher later in the hour. 19:00 starts at 40 %: learned.
        c = self._coord({})
        self._learn_at(c, datetime(2026, 10, 7, 18, 0), 0.4, 25.0)
        self._learn_at(c, datetime(2026, 10, 7, 18, 30), 0.4, 35.0)
        self._learn_at(c, datetime(2026, 10, 7, 19, 0), 1.5, 40.0)
        self._learn_at(c, datetime(2026, 10, 7, 19, 30), 1.5, 28.0)
        hours = c._stored["house_load_hours"]
        assert "2026-10-07T18" not in hours
        assert hours["2026-10-07T19"] == [3.0, 2]
        assert c._stored["house_load_weekday"][18] == 0.5  # EMA untouched too

    def test_low_soc_outside_peak_hours_is_learned(self):
        c = self._coord({})
        self._learn_at(c, datetime(2026, 10, 7, 14, 0), 0.8, 15.0)
        self._learn_at(c, datetime(2026, 10, 7, 21, 0), 0.8, 15.0)
        hours = c._stored["house_load_hours"]
        assert "2026-10-07T14" in hours and "2026-10-07T21" in hours

    def test_peak_hour_learned_when_soc_unknown(self):
        c = self._coord({})
        self._learn_at(c, datetime(2026, 10, 7, 17, 0), 0.9, None)
        assert "2026-10-07T17" in c._stored["house_load_hours"]


class TestBridgeBuyContinues:
    """v1.23.2 — a started shortfall buy runs until the shortfall is gone."""

    want = staticmethod(BatteryArbitrageCoordinator._shortfall_buy_wanted)

    def test_small_shortfall_alone_does_not_start_a_buy(self):
        now = datetime(2026, 10, 8, 1, 30)
        assert not self.want(None, now, 0.4, True)

    def test_started_buy_finishes_the_last_half_kwh(self):
        now = datetime(2026, 10, 8, 1, 30)
        until = datetime(2026, 10, 8, 8, 30)
        assert self.want(until, now, 0.4, True)
        assert not self.want(until, now, 0.4, False)  # price gate still applies

    def test_finished_bridge_does_not_carry_over(self):
        until = datetime(2026, 10, 8, 8, 30)
        assert not self.want(until, datetime(2026, 10, 8, 23, 0), 0.4, True)


class TestPeakCover:
    """v1.23.2 — battery holds the 17-21 h forecast plus a learned cover."""

    TZ = timezone(timedelta(hours=2))

    def _coord(self, hours):
        c = object.__new__(BatteryArbitrageCoordinator)
        c._stored = {
            "house_load_hours": hours,
            "house_load_weekday": [0.5] * 24,
            "house_load_weekend": [0.5] * 24,
        }
        c._house_profile_cache = None
        c._peak_cover_cache = None
        c._clear_peak_cover()
        return c

    @staticmethod
    def _hours(today, ndays, kw_fn):
        out = {}
        for k in range(ndays):
            d = today - timedelta(days=k + 1)
            for h in range(24):
                out[f"{d.isoformat()}T{h:02d}"] = [kw_fn(d, h) * 12, 12]
        return out

    def test_cover_is_the_heavy_evening_excess(self):
        # 28 days at 0.5 kW; every 4th day, across weekdays and weekends, the
        # 17-21 h block runs at 1.5 kW: 6 kWh against a forecast of about 3.
        today = datetime(2026, 10, 8, 12, 0)
        heavy = lambda d: (today.date() - d).days % 4 == 0
        hours = self._hours(today.date(), 28,
                            lambda d, h: 1.5 if heavy(d) and 17 <= h < 21 else 0.5)
        c = self._coord(hours)
        cover = c._peak_cover_kwh(today)
        assert 2.0 < cover < 4.0   # p90 lands on a heavy evening
        # an ordinary month has no cover
        flat = self._coord(self._hours(today.date(), 28, lambda d, h: 0.5))
        assert flat._peak_cover_kwh(today) == 0.0

    def test_no_cover_without_enough_days(self):
        today = datetime(2026, 10, 8, 12, 0)
        c = self._coord(self._hours(today.date(), 5, lambda d, h: 2.0))
        assert c._peak_cover_kwh(today) == 0.0

    def _slots(self, start, n, house_kw, solar_kw=0.0):
        return [(start + timedelta(minutes=15 * i), house_kw, 0.25, False, False, solar_kw)
                for i in range(n)]

    def test_shortfall_before_the_block(self):
        # 13:00, no sun, house 0.5 kW, efficiency 1.0, no cover history.
        now = datetime(2026, 10, 8, 13, 0, tzinfo=self.TZ)
        c = self._coord({})
        c._size_peak_cover(now, self._slots(now, 40, 0.5), 1.0)
        assert c._peak_start.hour == 17 and c._peak_end.hour == 21
        # need = 4 h x (0.5 + standby) ; before the block 4 h x 0.5 = 2 kWh drain
        need = 4 * (0.5 + 0.07)
        assert c._peak_need_kwh == pytest.approx(need)
        # 4 kWh now, 2 kWh left at 17:00
        assert c._peak_shortfall_kwh(4.0, 9.0) == pytest.approx(need - 2.0)
        assert c._peak_shortfall_kwh(6.0, 9.0) == 0.0

    def test_sun_before_the_block_fills_it(self):
        now = datetime(2026, 10, 8, 11, 0, tzinfo=self.TZ)
        c = self._coord({})
        slots = self._slots(now, 24, 0.5, 3.0) + self._slots(now + timedelta(hours=6), 16, 0.5)
        c._size_peak_cover(now, slots, 1.0)
        assert c._peak_shortfall_kwh(0.0, 9.0) == 0.0

    def test_nothing_sized_during_the_block(self):
        now = datetime(2026, 10, 8, 18, 0, tzinfo=self.TZ)
        c = self._coord({})
        c._size_peak_cover(now, self._slots(now, 100, 0.5), 1.0)
        assert c._peak_start is None

    def test_forecast_short_of_the_block_end(self):
        now = datetime(2026, 10, 8, 13, 0, tzinfo=self.TZ)
        c = self._coord({})
        c._size_peak_cover(now, self._slots(now, 20, 0.5), 1.0)   # ends 18:00
        assert c._peak_start is None

    def test_price_must_beat_the_block_after_losses_and_wear(self):
        ok = BatteryArbitrageCoordinator._peak_cover_price_ok
        # 1.00 now, block 1.20: 1.00 / 0.9 + 0.10 = 1.21 does not pay
        assert not ok(1.00, 1.05, [1.20] * 16, 0.9, 0.10)
        # block 1.30: pays
        assert ok(1.00, 1.05, [1.30] * 16, 0.9, 0.10)
        # outside the buy window
        assert not ok(1.20, 1.05, [3.00] * 16, 0.9, 0.10)

    def test_expected_buy_slots_cover_the_shortfall_in_time_order(self):
        pick = BatteryArbitrageCoordinator._expected_buy_slots
        t = lambda h, m: datetime(2026, 10, 9, h, m)
        slots = [(t(3, 45), 0.25, 1.0), (t(1, 15), 0.25, 1.0), (t(2, 15), 0.25, 1.0)]
        # 3 kWh at 8 kWh/h: 2 kWh per quarter hour → two slots
        assert pick(slots, 3.0, 8.0) == [t(1, 15), t(2, 15)]
        assert pick(slots, 1.0, 8.0) == [t(1, 15)]
        assert pick(slots, 3.0, 0.0) == [t(1, 15)]   # unknown rate: first slot only
        assert pick([], 3.0, 8.0) == []


class TestPlanRunStarts:
    """v1.23.2 — plan text lists the start time of each buy / sell run."""

    def test_consecutive_slots_merge_into_one_start_time(self):
        from custom_components.battery_arbitrage.coordinator import _plan_run_starts
        tz = timezone(timedelta(hours=2))
        e = lambda h, m, a="CHARGE": {"action": a, "iso": datetime(2026, 10, 9, h, m, tzinfo=tz).isoformat(), "hour": h}
        entries = [e(1, 15), e(1, 30), e(2, 15), e(13, 0), e(13, 15), e(13, 30), e(13, 45), e(19, 0, "EXPORT")]
        runs = _plan_run_starts(entries, "CHARGE")
        day = datetime(2026, 10, 9, tzinfo=tz).astimezone().date()
        assert runs[day] == ["01:15", "02:15", "13:00"]
        assert _plan_run_starts(entries, "EXPORT")[day] == ["19:00"]
        assert _plan_run_starts([], "CHARGE") == {}


class TestModelHealthReserveCap:
    """v1.23.4 — the reserve-cap issue names the cause and a setting that acts."""

    def _coord(self, samples, pct=80):
        c = object.__new__(BatteryArbitrageCoordinator)
        c._stored = {"overnight_ratio_samples": samples, "reserve_percentile_pct": pct,
                     "battery_capacity": 10.0}
        c.config = {}
        c.get_learned_capacity = lambda: None
        c.get_auto_efficiency = lambda: None
        c.get_solar_accuracy_factor = lambda: 1.0
        c.get_prediction_accuracy_summary = lambda: {}
        return c

    def test_cap_message_names_cause_and_percentile(self):
        # p70 of five ordinary nights and three heavy ones lands above 2.0
        issues, _ = self._coord([1.0] * 5 + [2.6] * 3, pct=70)._check_model_health()
        msg = [i for i in issues if "Reserve factor" in i]
        assert len(msg) == 1
        assert "30 % or more" in msg[0] and "Reserve percentile" in msg[0]
        assert "consider raising" not in msg[0]

    def test_no_cap_issue_below_the_cap(self):
        issues, _ = self._coord([1.0] * 8)._check_model_health()
        assert not [i for i in issues if "Reserve factor" in i]


class TestHouseLoadWithoutCar:
    """v1.23.5 — the car is taken out of house load once, in every live-data mode."""

    f = staticmethod(BatteryArbitrageCoordinator._house_load_kw)

    def test_hybrid_subtracts_the_evcc_car_from_the_inverter_load(self):
        # inverter load 5 kW includes a 3 kW car on an EVCC loadpoint
        assert self.f(5000, 3000, 3000, "hybrid") == pytest.approx(2.0)

    def test_evcc_home_power_already_excludes_the_car(self):
        # EVCC homePower = grid + PV + battery - charge power: 2 kW house
        assert self.f(2000, 3000, 3000, "evcc") == pytest.approx(2.0)

    def test_evcc_mode_still_subtracts_a_car_evcc_does_not_see(self):
        # car on the embedded OCPP server, unknown to EVCC
        assert self.f(5000, 3000, 0, "evcc") == pytest.approx(2.0)

    def test_foxess_only_with_own_charger_backend(self):
        assert self.f(5000, 3000, 0, "foxess") == pytest.approx(2.0)


class TestScheduledOnPlugIn:
    """v1.23.7 — a plug-in returns to the default mode; Scheduled only survives
    the first plug-in after it was chosen."""

    def _coord(self, mode, connected):
        c = object.__new__(BatteryArbitrageCoordinator)
        c._stored = {"ev_default_mode": "pv", "ev_active_mode": mode}
        c.config = {}
        c._ev_active_mode = mode
        c._ev_prev_connected = connected
        return c

    def _tick(self, c, connected):
        plugged = c._ev_mode_on_plug_in(connected)
        c._ev_prev_connected = connected
        return plugged

    def test_scheduled_chosen_while_connected_resets_on_the_next_plug_in(self):
        # Recorded case: Scheduled chosen with the car in, car leaves, comes back.
        c = self._coord("scheduled", True)
        self._tick(c, False)            # unplugged in the morning
        assert self._tick(c, True)      # plugged in again in the afternoon
        assert c._ev_active_mode == "pv"

    def test_scheduled_chosen_before_the_car_comes_home_is_kept(self):
        # car away, Scheduled chosen (set_ev_mode clears the unplugged flag)
        c = self._coord("scheduled", False)
        c._stored["ev_scheduled_unplugged"] = False
        self._tick(c, True)
        assert c._ev_active_mode == "scheduled"
        self._tick(c, False)
        self._tick(c, True)
        assert c._ev_active_mode == "pv"

    def test_other_modes_still_return_to_the_default(self):
        c = self._coord("full", False)
        self._tick(c, True)
        assert c._ev_active_mode == "pv"

    def test_restart_mid_schedule_keeps_scheduled(self):
        # After a restart the first tick looks like a plug-in.
        c = self._coord("scheduled", False)
        self._tick(c, True)
        assert c._ev_active_mode == "scheduled"

    @staticmethod
    def _restart(c):
        # what async_load_storage does with the stored state
        n = object.__new__(BatteryArbitrageCoordinator)
        n._stored = c._stored
        n.config = {}
        n._ev_active_mode = n._stored.get("ev_active_mode", "locked")
        n._ev_prev_connected = bool(n._stored.get("ev_prev_connected", False))
        return n

    def _tick_stored(self, c, connected):
        plugged = c._ev_mode_on_plug_in(connected)
        c._set_ev_prev_connected(connected)
        return plugged

    def test_restart_with_the_car_plugged_in_keeps_a_manual_mode(self):
        # Recorded case: a restart reset a manual Full to the PV default.
        c = self._coord("full", False)
        self._tick_stored(c, True)            # plug-in → default pv
        c._ev_active_mode = c._stored["ev_active_mode"] = "full"   # user picks Full
        self._tick_stored(c, True)
        c = self._restart(c)
        assert not self._tick_stored(c, True)
        assert c._ev_active_mode == "full"

    def test_car_plugged_in_during_a_restart_gets_the_default(self):
        c = self._coord("full", False)
        self._tick_stored(c, False)           # car away when HA went down
        c = self._restart(c)
        assert self._tick_stored(c, True)
        assert c._ev_active_mode == "pv"

    def test_first_start_after_the_upgrade_takes_a_baseline(self):
        # No stored plug state yet: the first reading is not a plug-in.
        c = self._coord("full", None)
        assert not self._tick_stored(c, True)
        assert c._ev_active_mode == "full"
        assert c._stored["ev_prev_connected"] is True


class TestSellAndBuyBack:
    """v1.24.0 — buy windows sized by the sustained charge rate; the night
    floor credits a buy-back that beats the sale."""

    TZ = timezone(timedelta(hours=2))

    def _t(self, h, m=0, day=0):
        return datetime(2026, 10, 17, h, m, tzinfo=self.TZ) + timedelta(days=day)

    def test_window_widens_for_a_slow_battery(self):
        lim = BatteryArbitrageCoordinator._buy_window_limit
        slots = [(self._t(1), 0.25, 1.00), (self._t(2), 0.25, 1.10), (self._t(3), 0.25, 1.30)]
        # 2 kWh at 8 kWh/h: one quarter hour does it -> cheapest x 1.05
        assert lim(slots, 2.0, 8.0) == pytest.approx(1.05)
        # same 2 kWh at 4 kWh/h (cold battery): two slots needed
        assert lim(slots, 2.0, 4.0) == pytest.approx(1.10)
        # more than all slots can take: every slot
        assert lim(slots, 9.0, 4.0) == pytest.approx(1.30)
        assert lim([], 2.0, 4.0) is None

    def test_negative_prices_are_bought(self):
        lim = BatteryArbitrageCoordinator._buy_window_limit
        slots = [(self._t(1), 0.25, -0.40), (self._t(2), 0.25, -0.30), (self._t(3), 0.25, 0.20)]
        # cheapest -0.40, allowance 5 % of its size upward: -0.38
        assert lim(slots, 1.0, 8.0) == pytest.approx(-0.38)
        assert -0.40 <= lim(slots, 1.0, 8.0)          # the cheapest slot qualifies
        assert lim(slots, 2.0, 4.0) == pytest.approx(-0.30)   # two 1 kWh quarter hours
        ok = BatteryArbitrageCoordinator._peak_cover_price_ok
        assert ok(-0.40, -0.38, [1.5] * 16, 0.9, 0.05)

    def _coord(self):
        c = object.__new__(BatteryArbitrageCoordinator)
        c._stored = {}
        c.get_house_load_profile = lambda *a, **k: [0.5] * 24
        c._refill_buy_price = None
        return c

    def _refill(self, sell, night_price=1.0, ev_kw=0.0):
        slots = []
        t = self._t(18)
        while t < self._t(8, day=1):
            p = night_price if self._t(0, day=1) <= t < self._t(4, day=1) else 2.0
            slots.append((t, 0.25, p))
            t += timedelta(minutes=15)
        return {"sell": sell, "wear": 0.05, "rate_kw": 8.0, "grid_max_kw": 17.0,
                "ev_kw_by_hour": [ev_kw] * 24, "slots": slots}

    def _bridge_slots(self):
        out, t = [], self._t(18)
        while t < self._t(8, day=1):
            out.append((t, 0.5, 0.25, False, False, 0.0))
            t += timedelta(minutes=15)
        return out

    def test_credit_when_the_night_price_beats_the_sale(self):
        c = self._coord()
        credit, need = c._night_refill_credit(
            self._t(18), self._bridge_slots(), 0, self._t(8, day=1), 0.9, self._refill(2.2))
        assert credit >= 14 * 0.57 / 0.9 ** 0.5               # covers the night's need
        assert need == pytest.approx(6 * 0.57 / 0.9 ** 0.5, rel=0.01)   # 18:00-00:00
        assert c._refill_buy_price == pytest.approx(1.0)

    def test_no_credit_when_buying_back_does_not_pay(self):
        c = self._coord()
        # selling at 1.20 allows a buy-back up to (1.20 x 0.949 - 0.05) x 0.949 = 1.03
        credit, _ = c._night_refill_credit(
            self._t(18), self._bridge_slots(), 0, self._t(8, day=1), 0.9,
            self._refill(1.2, night_price=1.1))
        assert credit == 0.0

    def test_car_at_night_limits_the_buy_back(self):
        c = self._coord()
        full, _ = c._night_refill_credit(
            self._t(18), self._bridge_slots(), 0, self._t(8, day=1), 0.9, self._refill(2.2))
        with_car, _ = c._night_refill_credit(
            self._t(18), self._bridge_slots(), 0, self._t(8, day=1), 0.9,
            self._refill(2.2, ev_kw=15.5))   # leaves 0.5 kW of the 17 kW limit
        assert with_car < full

    def _floor_coord(self):
        c = self._coord()
        c.get_solar_confidence_factor_for_hour = lambda h: 1.0
        c._bridge_solar_kw = lambda st, kw: kw
        c._physical_floor_soc = lambda: 13.0
        c._reserve_factor = lambda: 1.0
        c._optimizer_plan = []
        c._size_peak_cover = lambda *a: None
        return c

    def _solar(self):
        out, t = [], self._t(18)
        while t < self._t(14, day=1):
            out.append((t, 0.25, t.hour, t.minute, 3000.0 if 9 <= t.hour < 14 and t.day != 17 else 0.0))
            t += timedelta(minutes=15)
        return out

    def test_floor_keeps_only_the_need_until_the_buy_back(self):
        kw = dict(now=self._t(18), capacity_kwh=10.0, efficiency=0.9,
                  solar_slot_data=self._solar(), grid_charge_kw=8.0)
        without = self._floor_coord()._compute_dynamic_floor_soc(**kw)
        selling = self._floor_coord()._compute_dynamic_floor_soc(**kw, refill=self._refill(2.2))
        cheap_sale = self._floor_coord()._compute_dynamic_floor_soc(
            **kw, refill=self._refill(1.2, night_price=1.1))
        assert without == 85.0                     # whole night does not fit: capped
        # 18:00-00:00 at 0.57 kW / 0.949 = 3.6 kWh on 10 kWh above a 13 % floor
        assert selling == pytest.approx(13 + 36.0, abs=1.0)
        assert cheap_sale == without               # buy-back would not pay

    def test_floor_reports_whether_grid_buys_hold_the_night(self):
        kw = dict(now=self._t(18), capacity_kwh=10.0, efficiency=0.9,
                  solar_slot_data=self._solar(), grid_charge_kw=8.0)
        c = self._floor_coord()
        c._compute_dynamic_floor_soc(**{**kw, "capacity_kwh": 20.0})
        assert c._floor_grid_credited is False     # whole night held in the battery
        c = self._floor_coord()
        c._compute_dynamic_floor_soc(**kw)
        assert c._floor_grid_credited is True      # v1.30.1: capped, the bridge buys the rest
        c = self._floor_coord()
        c._compute_dynamic_floor_soc(**kw, refill=self._refill(2.2))
        assert c._floor_grid_credited is True      # buy-back counted

    def test_need_counts_until_the_slot_the_top_up_will_actually_use(self):
        # 22:00 pays (1.90) but 03:00-05:00 is cheaper (1.00) and covers the
        # night: the top-up buys at 03:00, so the house runs on the battery
        # until then, not until 22:00.
        c = self._coord()
        r = self._refill(2.2)
        r["slots"] = [(st, d, 1.90 if st == self._t(22) else
                       (1.00 if self._t(3, day=1) <= st < self._t(5, day=1) else 2.0))
                      for st, d, _p in r["slots"]]
        credit, need = c._night_refill_credit(
            self._t(18), self._bridge_slots(), 0, self._t(8, day=1), 0.9, r)
        assert need == pytest.approx(9 * 0.57 / 0.9 ** 0.5, rel=0.01)   # 18:00-03:00
        assert c._refill_buy_price == pytest.approx(1.00)

    def test_throttled_force_charge_does_not_teach_the_rate(self):
        from custom_components.battery_arbitrage.const import WORK_MODE_FORCE_CHARGE
        c = object.__new__(BatteryArbitrageCoordinator)
        c._stored = {"charge_samples": {}, "charge_rates": {}}
        c._calibrate_charge_rate(18.0, 5.0, 50.0, WORK_MODE_FORCE_CHARGE, throttled=True)
        assert c._stored["charge_samples"] == {}
        c._calibrate_charge_rate(18.0, 7.0, 50.0, WORK_MODE_FORCE_CHARGE)
        assert sum(len(v) for v in c._stored["charge_samples"].values()) == 1


    def test_buy_back_needs_the_minimum_arbitrage_spread(self):
        c = self._coord()
        r = self._refill(2.2)                     # 2.2 - 1.0 / 0.949 = 1.15
        r["min_spread"] = 1.8
        assert c._night_refill_credit(
            self._t(18), self._bridge_slots(), 0, self._t(8, day=1), 0.9, r)[0] == 0.0
        r["min_spread"] = 0.3
        assert c._night_refill_credit(
            self._t(18), self._bridge_slots(), 0, self._t(8, day=1), 0.9, r)[0] > 0.0


class TestSolarRefilledSale:
    """v1.24.0 — energy the sun will replace sells above the minimum export
    price; the minimum arbitrage spread does not block it."""

    TZ = timezone(timedelta(hours=2))

    def test_sun_refilled_sale_ignores_a_high_minimum_spread(self):
        c = object.__new__(BatteryArbitrageCoordinator)
        c._stored = {"battery_degradation_cost": 0.05}
        c.get_solar_hour_percentile = lambda h, p: None
        c.get_short_term_solar_factor = lambda h: 1.0
        c._compute_buy_price = lambda **k: 1.0
        now = datetime(2026, 10, 17, 18, 0, tzinfo=self.TZ)
        # sell 1.0 for the first hour, 0.2 after; sun from 08:00 next day
        grid = [(now + timedelta(minutes=15 * i), 0.25,
                 (now + timedelta(minutes=15 * i)).hour,
                 (now + timedelta(minutes=15 * i)).minute,
                 1.0 if i < 4 else 0.2) for i in range(96)]
        solar = [(now + timedelta(minutes=15 * i), 0.25, 0, 0,
                  4000.0 if 14 * 4 <= i < 20 * 4 else 0.0) for i in range(96)]
        plan = c._dp_solve(
            now, grid, solar, 1.0, 100.0, 10.0, 40, 10, 0, 100, 1.0, 5.0, 17.0,
            [0.3] * 24, [0.0] * 24, 0.0, 1.25, [0.0] * 24, 0.0, 0.0,
            0.0, 0.0, 0.03, 1.8, 10.0,
        )
        assert any(s["action"] == "EXPORT" for s in plan[:4])

    def test_low_price_sale_needs_the_spread_when_grid_buys_hold_the_night(self):
        # Night grid buys counted against the reserve: the "solar" sale would be
        # refilled from the grid, so the user's spread applies again.
        c = object.__new__(BatteryArbitrageCoordinator)
        c._stored = {"battery_degradation_cost": 0.05}
        c.get_solar_hour_percentile = lambda h, p: None
        c.get_short_term_solar_factor = lambda h: 1.0
        c._compute_buy_price = lambda **k: 1.0
        now = datetime(2026, 10, 17, 18, 0, tzinfo=self.TZ)
        grid = [(now + timedelta(minutes=15 * i), 0.25,
                 (now + timedelta(minutes=15 * i)).hour,
                 (now + timedelta(minutes=15 * i)).minute,
                 1.0 if i < 4 else 0.2) for i in range(96)]
        solar = [(now + timedelta(minutes=15 * i), 0.25, 0, 0,
                  4000.0 if 14 * 4 <= i < 20 * 4 else 0.0) for i in range(96)]
        plan = c._dp_solve(
            now, grid, solar, 1.0, 100.0, 10.0, 40, 10, 0, 100, 1.0, 5.0, 17.0,
            [0.3] * 24, [0.0] * 24, 0.0, 1.25, [0.0] * 24, 0.0, 0.0,
            0.0, 0.0, 0.03, 1.8, 10.0, solar_sale_needs_spread=True,
        )
        assert not any(s["action"] == "EXPORT" for s in plan[:4])

    def test_grid_refilled_sale_needs_a_gain_not_a_sell_price(self):
        # v1.30.1 — sell 2.0 is above a 1.8 minimum, but buying it back at
        # 1.0 gains only 1.0. With grid buys holding the night it must not sell.
        c = object.__new__(BatteryArbitrageCoordinator)
        c._stored = {"battery_degradation_cost": 0.05}
        c.get_solar_hour_percentile = lambda h, p: None
        c.get_short_term_solar_factor = lambda h: 1.0
        c._compute_buy_price = lambda **k: 1.0
        now = datetime(2026, 10, 17, 18, 0, tzinfo=self.TZ)
        grid = [(now + timedelta(minutes=15 * i), 0.25,
                 (now + timedelta(minutes=15 * i)).hour,
                 (now + timedelta(minutes=15 * i)).minute,
                 2.0 if i < 4 else 0.2) for i in range(96)]
        solar = [(now + timedelta(minutes=15 * i), 0.25, 0, 0,
                  4000.0 if 14 * 4 <= i < 20 * 4 else 0.0) for i in range(96)]
        plan = c._dp_solve(
            now, grid, solar, 1.0, 100.0, 10.0, 40, 10, 0, 100, 1.0, 5.0, 17.0,
            [0.3] * 24, [0.0] * 24, 0.0, 1.25, [0.0] * 24, 0.0, 0.0,
            0.0, 0.0, 0.03, 1.8, 10.0, solar_sale_needs_spread=True,
        )
        assert not any(s["action"] == "EXPORT" for s in plan[:4])


class TestDecisionFixes1244:
    """v1.24.4 — decision-logic fixes."""

    TZ = timezone(timedelta(hours=2))

    def test_partial_slot_top_up_before_the_peak(self):
        # 91 % full, a 15-min slot adds 21 %: only 9 % fits. Paying for the
        # whole slot and selling the overshoot back made this top-up a loss.
        c = object.__new__(BatteryArbitrageCoordinator)
        c._stored = {"battery_degradation_cost": 0.05}
        c.get_solar_hour_percentile = lambda h, p: None
        c.get_short_term_solar_factor = lambda h: 1.0
        now = datetime(2026, 10, 18, 16, 45, tzinfo=self.TZ)
        c._compute_buy_price = lambda **k: 1.5 if k["slot_start_dt"] < now + timedelta(minutes=15) else 2.2
        grid = [(now + timedelta(minutes=15 * i), 0.25,
                 (now + timedelta(minutes=15 * i)).hour,
                 (now + timedelta(minutes=15 * i)).minute,
                 0.9) for i in range(24)]
        solar = [(now + timedelta(minutes=15 * i), 0.25, 0, 0, 0.0) for i in range(24)]
        load = [0.0] * 24
        for h in (17, 18, 19, 20):
            load[h] = 3.0
        plan = c._dp_solve(
            now, grid, solar, 1.0, 91.0, 10.0, 10, 10, 0, 100, 1.0, 8.4, 17.0,
            load, [0.0] * 24, 0.0, 1.0, [0.0] * 24, 0.0, 0.0,
            0.0, 0.0, 0.03, 1.8, 10.0, house_load_weekend=load,
        )
        assert plan[0]["action"] == "CHARGE"

    def test_full_car_that_is_not_drawing_is_not_planned(self):
        kw = dict(connected=True, charging_now=False, effective_mode="full",
                  requested_mode="pv", live_kw=0.0, max_kw=10.4)
        assert BatteryArbitrageCoordinator._ev_session_demand_kw(
            **kw, drew_recently=False) == 0.0
        assert BatteryArbitrageCoordinator._ev_session_demand_kw(
            **kw, drew_recently=True) == 10.4

    def test_grid_energy_is_tracked_and_used_first(self):
        from custom_components.battery_arbitrage.const import MODE_GRID_CHARGING, MODE_NORMAL
        c = object.__new__(BatteryArbitrageCoordinator)
        c._stored = {}
        c._grid_track_soc = None
        c._physical_floor_soc = lambda: 13.0
        c._current_mode = MODE_GRID_CHARGING
        c._track_grid_energy(50.0, 10.0, 1.0, True)
        c._track_grid_energy(70.0, 10.0, 1.2, True)
        assert c._stored["grid_kwh"] == pytest.approx(2.0)
        assert c._stored["grid_kwh_cost"] == pytest.approx(1.2)
        c._current_mode = MODE_NORMAL
        c._track_grid_energy(65.0, 10.0, 2.0, True)
        assert c._stored["grid_kwh"] == pytest.approx(1.5)
        assert c._stored["grid_kwh_cost"] == pytest.approx(1.2)

    def test_grid_bought_energy_needs_the_minimum_gain_to_sell(self):
        # The sun refills tomorrow, so the sale at 1.0 would pass as spare
        # solar; 4 kWh in the battery came from the grid and need 1.5.
        c = object.__new__(BatteryArbitrageCoordinator)
        c._stored = {"battery_degradation_cost": 0.05}
        c.get_solar_hour_percentile = lambda h, p: None
        c.get_short_term_solar_factor = lambda h: 1.0
        c._compute_buy_price = lambda **k: 1.0
        now = datetime(2026, 10, 17, 18, 0, tzinfo=self.TZ)
        grid = [(now + timedelta(minutes=15 * i), 0.25,
                 (now + timedelta(minutes=15 * i)).hour,
                 (now + timedelta(minutes=15 * i)).minute,
                 1.0 if i < 4 else 0.2) for i in range(96)]
        solar = [(now + timedelta(minutes=15 * i), 0.25, 0, 0,
                  4000.0 if 14 * 4 <= i < 20 * 4 else 0.0) for i in range(96)]
        args = (now, grid, solar, 1.0, 100.0, 10.0, 40, 10, 0, 100, 1.0, 5.0, 17.0,
                [0.3] * 24, [0.0] * 24, 0.0, 1.25, [0.0] * 24, 0.0, 0.0,
                0.0, 0.0, 0.03, 1.8, 10.0)
        plan = c._dp_solve(*args)
        assert any(s["action"] == "EXPORT" for s in plan[:4])
        plan = c._dp_solve(*args, grid_min_sell=1.5, grid_sell_floor_soc=60.0,
                           grid_gate_until=now + timedelta(hours=12))
        assert not any(s["action"] == "EXPORT" for s in plan[:4])

    def test_midday_bridge_waits_for_tomorrows_prices(self):
        c = object.__new__(BatteryArbitrageCoordinator)
        c._physical_floor_soc = lambda: 13.0
        c.get_house_load_profile = lambda weekend=False: [0.5] * 24
        day = datetime(2026, 10, 19, 0, 0, tzinfo=self.TZ)
        c._bridge_end = day + timedelta(days=1, hours=9)
        today = [(day + timedelta(minutes=15 * i), 0.25, 0, 0, 1.0) for i in range(96)]
        both = [(day + timedelta(minutes=15 * i), 0.25, 0, 0, 1.0) for i in range(192)]
        eleven = day + timedelta(hours=11)
        assert c._bridge_waits_for_prices(eleven, today, 50.0, 10.0, 0.93) is True
        # after the prices are due, or once they cover the bridge: no wait
        assert c._bridge_waits_for_prices(day + timedelta(hours=14), today, 50.0, 10.0, 0.93) is False
        assert c._bridge_waits_for_prices(eleven, both, 50.0, 10.0, 0.93) is False
        # the battery would run short before 13:30: buy now
        assert c._bridge_waits_for_prices(eleven, today, 14.0, 10.0, 0.93) is False
