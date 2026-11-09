# Evaluation notes

The project ships original fictional sample documents and unit/API tests that exercise ingestion, source IDs, deletion, validation, privacy-safe activity summaries and holdout forecasting calculations. Passing these checks demonstrates implementation behavior only.

Run the repeatable synthetic retrieval check with `pytest -q tests/test_rag.py tests/test_api.py`. This checks that a known phrase from a fictional document returns the corresponding source record and that an unknown query does not receive a fabricated citation. It is not a labeled retrieval benchmark and no general Hit@k quality claim is made.

Forecast evaluation creates a time-ordered holdout from user-supplied observations: the first approximately 80% is used to fit the linear model and the final at least three observations are reserved for comparison. Both candidates are scored with MAE and RMSE; the chosen baseline is refit on all observations for the displayed future values. This is a small demonstration, not a walk-forward study, and its error does not promise future performance.

Text analysis uses fixed word lists and regular expressions. No precision, recall, F-score, language coverage or calibration metric is reported because no independent annotation set was used. CSV statistics and vision measurements are deterministic descriptions, not predictive metrics.
