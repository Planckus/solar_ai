"""Unit tests for Battery Arbitrage coordinator pure functions."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.battery_arbitrage.coordinator import (
    _forecast_values,
    _predict_house_load,
    _rolling_mean,
    _sum_forecast,
    _temp_bucket,
)


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
# _predict_house_load                                                  #
# ------------------------------------------------------------------ #

class TestPredictHouseLoad:
    def test_vacation_mode_uses_2h(self):
        load = _predict_house_load(0.2, 1.0, vacation_mode=True, hours=24)
        # 0.2 * 1.5 * 24 = 7.2
        assert abs(load - 7.2) < 0.01

    def test_vacation_minimum_floor(self):
        # Very low load → floor at 0.05 kW
        load = _predict_house_load(0.01, 0.01, vacation_mode=True, hours=24)
        assert load == pytest.approx(0.05 * 24, abs=0.01)

    def test_normal_uses_higher_of_short_or_half_long(self):
        # load_2h=0.5, load_28d=2.0 → max(0.5*1.1, 2.0*0.5) = max(0.55, 1.0) = 1.0
        load = _predict_house_load(0.5, 2.0, vacation_mode=False, hours=10)
        assert load == pytest.approx(1.0 * 10, abs=0.01)

    def test_normal_short_term_dominates(self):
        # load_2h=3.0, load_28d=1.0 → max(3.0*1.1, 1.0*0.5) = 3.3
        load = _predict_house_load(3.0, 1.0, vacation_mode=False, hours=1)
        assert load == pytest.approx(3.3, abs=0.01)


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
        # S1 neutrality guarantee: confidence=50 must equal the median, so the
        # default knob value is a no-op vs the prior median behaviour.
        import statistics
        for n in (9, 10, 13, 20):
            samples = [{"f": 1000, "a": 400 + i * 60} for i in range(n)]
            ratios = [s["a"] / s["f"] for s in samples]
            expected = round(max(0.3, min(1.5, statistics.median(ratios))), 3)
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
