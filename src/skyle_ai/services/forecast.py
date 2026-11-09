from __future__ import annotations

import math

import numpy as np


class ForecastError(ValueError):
    pass


def forecast_series(values: list[float], horizon: int = 7) -> dict:
    if not 1 <= horizon <= 30:
        raise ForecastError("Forecast horizon must be between 1 and 30 steps.")
    series = np.asarray(values, dtype=float)
    if series.ndim != 1 or len(series) < 12:
        raise ForecastError("Provide at least 12 chronological numeric observations.")
    if not np.isfinite(series).all():
        raise ForecastError("Series values must be finite; remove blanks and non-numeric entries first.")
    split = max(8, int(math.floor(len(series) * 0.8)))
    if len(series) - split < 3:
        split = len(series) - 3
    train, test = series[:split], series[split:]
    baseline = np.repeat(train[-1], len(test))
    fit_slope, fit_intercept = _linear_fit(train)
    trend = fit_intercept + fit_slope * np.arange(len(train), len(train) + len(test))
    metrics = {
        "last_value_baseline": _metrics(test, baseline),
        "linear_trend": _metrics(test, trend),
        "train_observations": int(len(train)),
        "holdout_observations": int(len(test)),
        "holdout_policy": (
            "Chronological final 20% (at least 3 observations); model parameters fit on earlier observations only."
        ),
    }
    chosen = (
        "linear_trend"
        if metrics["linear_trend"]["mae"] <= metrics["last_value_baseline"]["mae"]
        else "last_value_baseline"
    )
    if chosen == "linear_trend":
        slope, intercept = _linear_fit(series)
        predictions = intercept + slope * np.arange(len(series), len(series) + horizon)
    else:
        predictions = np.repeat(series[-1], horizon)
    return {
        "model_selected_on_holdout_mae": chosen,
        "holdout_metrics": metrics,
        "forecast": [{"step": step + 1, "value": round(float(value), 6)} for step, value in enumerate(predictions)],
        "observations": int(len(series)),
        "notes": [
            "Only simple last-value and linear-trend baselines are compared; "
            "no seasonality or external regressors are modeled.",
            "Forecast intervals and operational/business validation are not provided.",
        ],
    }


def _linear_fit(train: np.ndarray) -> tuple[float, float]:
    x = np.arange(len(train), dtype=float)
    slope, intercept = np.polyfit(x, train, deg=1)
    return float(slope), float(intercept)


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    errors = actual - predicted
    return {
        "mae": round(float(np.mean(np.abs(errors))), 6),
        "rmse": round(float(np.sqrt(np.mean(errors**2))), 6),
    }
