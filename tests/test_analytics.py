from __future__ import annotations

from skyle_ai.services.analytics import profile_csv
from skyle_ai.services.forecast import ForecastError, forecast_series


def test_csv_profile_counts_missing_duplicates_and_numeric_summary(client):
    content = b"day,revenue,region\n1,10,east\n2,20,west\n2,20,west\n3,,east\n"
    response = client.post("/api/v1/analyze/csv", files={"file": ("metrics.csv", content, "text/csv")})
    assert response.status_code == 200
    body = response.json()
    assert body["rows"] == 4
    assert body["duplicate_rows"] == 1
    revenue = next(col for col in body["column_profile"] if col["name"] == "revenue")
    assert revenue["missing"] == 1
    assert revenue["summary"]["mean"] == 16.6667
    assert "10,east" not in client.get("/api/v1/activity").text


def test_forecast_holdout_and_baseline_selection():
    values = [5 + i * 1.5 for i in range(30)]
    result = forecast_series(values, horizon=3)
    assert result["observations"] == 30
    assert result["holdout_metrics"]["holdout_observations"] == 6
    assert result["model_selected_on_holdout_mae"] == "linear_trend"
    assert len(result["forecast"]) == 3
    assert abs(result["forecast"][0]["value"] - 50.0) < 1e-5


def test_forecast_rejects_small_and_nonfinite_series():
    try:
        forecast_series([1, 2, 3], horizon=2)
    except ForecastError:
        pass
    else:
        raise AssertionError("expected short series to fail")
    try:
        forecast_series([1.0] * 12 + [float("nan")])
    except ForecastError:
        pass
    else:
        raise AssertionError("expected non-finite series to fail")


def test_forecast_endpoint_sorts_valid_dates_and_rejects_missing_value_column(client):
    rows = "date,value\n" + "\n".join(f"2026-01-{i + 1:02d},{i * 2}" for i in reversed(range(18)))
    response = client.post(
        "/api/v1/forecast",
        files={"file": ("series.csv", rows.encode(), "text/csv")},
        data={"value_column": "value", "date_column": "date", "horizon": "3"},
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["forecast"]) == 3
    bad = client.post(
        "/api/v1/forecast",
        files={"file": ("series.csv", rows.encode(), "text/csv")},
        data={"value_column": "absent", "horizon": "7"},
    )
    assert bad.status_code == 422


def test_csv_profile_rejects_empty_data():
    try:
        profile_csv(b"", max_rows=10)
    except ValueError:
        pass
    else:
        raise AssertionError("expected an empty CSV to fail")
