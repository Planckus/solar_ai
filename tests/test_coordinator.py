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
        assert _temp_bucket(0.0) == "0_to_10"

    def test_mid_bucket(self):
        assert _temp_bucket(15.0) == "10_to_20"

    def test_upper_bucket(self):
        assert _temp_bucket(25.0) == "20_to_35"

    def test_above_35(self):
        assert _temp_bucket(40.0) == "above_35"

    def test_boundary_35(self):
        assert _temp_bucket(35.0) == "above_35"

    def test_boundary_10(self):
        assert _temp_bucket(10.0) == "10_to_20"


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
    """get_house_load_profile returns the requested day type with layered
    fallback (own → legacy combined → other type → rolling mean)."""

    def _call(self, stored, weekend):
        import types
        from custom_components.battery_arbitrage.coordinator import (
            BatteryArbitrageCoordinator,
        )
        stub = types.SimpleNamespace(_stored=stored)
        return BatteryArbitrageCoordinator.get_house_load_profile(stub, weekend=weekend)

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


# ------------------------------------------------------------------ #
# v0.47.0 — dynamic discharge floor: self-learning margin              #
# ------------------------------------------------------------------ #

class TestDischargeMargin:
    """_update_discharge_margin bumps the reserve margin up on a day where the
    battery hit the hard floor, and relaxes it down on a clean day."""

    def _run(self, stored, soc, now):
        import types
        from custom_components.battery_arbitrage.coordinator import (
            BatteryArbitrageCoordinator,
        )
        stub = types.SimpleNamespace(_stored=stored)
        BatteryArbitrageCoordinator._update_discharge_margin(stub, now, soc)
        return stored

    def test_first_observation_no_change(self):
        import datetime as dt
        stored = {"discharge_reserve_margin": 1.10}
        self._run(stored, 60.0, dt.datetime(2026, 6, 1, 12, tzinfo=dt.timezone.utc))
        assert stored["discharge_reserve_margin"] == 1.10  # no prior day → no adjust
        assert stored["dynamic_floor_day"] == \
            dt.datetime(2026, 6, 1, 12, tzinfo=dt.timezone.utc).astimezone().date().isoformat()

    def test_undershoot_bumps_margin_up(self):
        import datetime as dt
        stored = {
            "discharge_reserve_margin": 1.10,
            "dynamic_floor_day": "2000-01-01",
            "dynamic_floor_undershot": True,
        }
        self._run(stored, 60.0, dt.datetime(2026, 6, 1, 12, tzinfo=dt.timezone.utc))
        assert stored["discharge_reserve_margin"] == round(1.10 * 1.05, 3)
        assert stored["dynamic_floor_undershot"] is False

    def test_clean_day_relaxes_margin_down(self):
        import datetime as dt
        stored = {
            "discharge_reserve_margin": 1.10,
            "dynamic_floor_day": "2000-01-01",
            "dynamic_floor_undershot": False,
        }
        self._run(stored, 60.0, dt.datetime(2026, 6, 1, 12, tzinfo=dt.timezone.utc))
        assert stored["discharge_reserve_margin"] == round(1.10 * 0.98, 3)

    def test_low_soc_sets_undershoot_flag(self):
        import datetime as dt
        # Same day (no rollover) but SoC at the hard floor → flag set.
        today = dt.datetime(2026, 6, 1, 12, tzinfo=dt.timezone.utc).astimezone().date().isoformat()
        stored = {"discharge_reserve_margin": 1.10, "dynamic_floor_day": today}
        self._run(stored, 21.0, dt.datetime(2026, 6, 1, 13, tzinfo=dt.timezone.utc))
        assert stored["dynamic_floor_undershot"] is True

    def test_margin_clamped(self):
        import datetime as dt
        stored = {
            "discharge_reserve_margin": 1.58,
            "dynamic_floor_day": "2000-01-01",
            "dynamic_floor_undershot": True,
        }
        self._run(stored, 60.0, dt.datetime(2026, 6, 1, 12, tzinfo=dt.timezone.utc))
        assert stored["discharge_reserve_margin"] <= 1.60  # clamped at MAX


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
              soc=66.0, ev_hours=range(11, 17), ev_pv_stop_kw=1.38, tail_kw=None):
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
            ev_pv_stop_kw=ev_pv_stop_kw,
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
