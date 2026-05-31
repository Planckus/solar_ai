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
