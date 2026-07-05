"""
engines/monte_carlo.py — ported verbatim from
dib_monitor/dib_monitor/monte_carlo.py. No config imports (n_paths/seed
passed in by the caller from configs/dib.py), so nothing to fix here.

GBM-style Monte Carlo simulation for DIB supplier financial distress probability.

Model: EBITDA follows Geometric Brownian Motion.
Distress event: simulated EBITDA falls below annual debt-service obligation.

This is a simplified illustration model, not a professional valuation. The
outputs should be read directionally, not as precise probability estimates.
"""
from __future__ import annotations
import numpy as np


def run_gbm_distress(
    current_ebitda_mm: float,
    debt_service_annual_mm: float,
    drift: float = 0.03,
    volatility: float = 0.15,
    n_paths: int = 10_000,
    seed: int = 42,
) -> dict[str, float]:
    """
    Estimate probability that EBITDA falls below the debt-service threshold
    at 1, 2, and 3 years.

    drift      — expected annual EBITDA growth rate (e.g., 0.03 = 3%)
    volatility — annual EBITDA standard deviation as a fraction (e.g., 0.15)
    """
    if current_ebitda_mm <= 0:
        return {"prob_1yr": 1.0, "prob_2yr": 1.0, "prob_3yr": 1.0}

    rng = np.random.default_rng(seed)
    results: dict[str, float] = {}

    for years in [1, 2, 3]:
        # GBM closed-form: S(T) = S(0) * exp((μ - σ²/2)*T + σ*√T*Z)
        Z = rng.standard_normal(n_paths)
        ebitda_T = current_ebitda_mm * np.exp(
            (drift - 0.5 * volatility**2) * years
            + volatility * np.sqrt(years) * Z
        )
        p_distress = float(np.mean(ebitda_T < debt_service_annual_mm))
        results[f"prob_{years}yr"] = round(p_distress, 4)

    return results


def estimate_drift_and_vol(revenue_history: list[float]) -> tuple[float, float]:
    """
    Estimate drift and volatility from a list of annual revenue figures
    (oldest first). Returns (drift, volatility).
    Falls back to conservative defaults if fewer than 2 data points.
    """
    if len(revenue_history) < 2:
        return 0.02, 0.15

    arr = np.array(revenue_history, dtype=float)
    log_returns = np.diff(np.log(arr))
    drift = float(np.mean(log_returns))
    volatility = float(np.std(log_returns, ddof=1))
    return round(drift, 4), round(max(volatility, 0.05), 4)


def distress_level_label(prob: float) -> str:
    if prob >= 0.30:
        return "CRITICAL"
    if prob >= 0.15:
        return "HIGH"
    if prob >= 0.05:
        return "MEDIUM"
    return "LOW"
