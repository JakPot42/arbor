"""Ported from dib_monitor/tests/test_monte_carlo.py."""
import pytest
from engines.monte_carlo import run_gbm_distress, estimate_drift_and_vol, distress_level_label


class TestRunGbmDistress:
    def test_returns_three_horizons(self):
        result = run_gbm_distress(100.0, 20.0)
        assert set(result.keys()) == {"prob_1yr", "prob_2yr", "prob_3yr"}

    def test_probabilities_between_zero_and_one(self):
        result = run_gbm_distress(100.0, 20.0)
        for val in result.values():
            assert 0.0 <= val <= 1.0

    def test_healthy_company_low_distress(self):
        result = run_gbm_distress(500.0, 10.0, drift=0.05, volatility=0.10)
        assert result["prob_1yr"] < 0.05

    def test_distressed_company_high_probability(self):
        result = run_gbm_distress(25.0, 24.0, drift=0.0, volatility=0.40)
        assert result["prob_3yr"] > 0.30

    def test_negative_ebitda_returns_all_ones(self):
        result = run_gbm_distress(-10.0, 5.0)
        assert result["prob_1yr"] == 1.0
        assert result["prob_2yr"] == 1.0
        assert result["prob_3yr"] == 1.0

    def test_deterministic_with_same_seed(self):
        r1 = run_gbm_distress(100.0, 30.0, seed=99)
        r2 = run_gbm_distress(100.0, 30.0, seed=99)
        assert r1 == r2

    def test_different_seeds_different_results(self):
        r1 = run_gbm_distress(50.0, 45.0, drift=0.0, volatility=0.35, seed=1)
        r2 = run_gbm_distress(50.0, 45.0, drift=0.0, volatility=0.35, seed=2)
        assert r1["prob_1yr"] != r2["prob_1yr"]

    def test_higher_volatility_increases_distress(self):
        low_vol = run_gbm_distress(100.0, 40.0, drift=0.02, volatility=0.05)
        high_vol = run_gbm_distress(100.0, 40.0, drift=0.02, volatility=0.50)
        assert high_vol["prob_1yr"] > low_vol["prob_1yr"]

    def test_distress_increases_with_horizon(self):
        result = run_gbm_distress(80.0, 50.0, drift=0.0, volatility=0.20)
        assert result["prob_3yr"] >= result["prob_2yr"] >= result["prob_1yr"]


class TestEstimateDriftAndVol:
    def test_returns_tuple(self):
        drift, vol = estimate_drift_and_vol([100, 110, 121])
        assert isinstance(drift, float)
        assert isinstance(vol, float)

    def test_falls_back_on_single_value(self):
        drift, vol = estimate_drift_and_vol([100])
        assert drift == 0.02
        assert vol == 0.15

    def test_positive_growth_gives_positive_drift(self):
        drift, _ = estimate_drift_and_vol([100, 110, 121, 133])
        assert drift > 0


class TestDistressLevelLabel:
    def test_critical(self):
        assert distress_level_label(0.35) == "CRITICAL"

    def test_high(self):
        assert distress_level_label(0.20) == "HIGH"

    def test_medium(self):
        assert distress_level_label(0.08) == "MEDIUM"

    def test_low(self):
        assert distress_level_label(0.02) == "LOW"
