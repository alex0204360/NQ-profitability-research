import numpy as np
import pytest
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from tools.cloud_campaign05_holdout import decide, linear_trace


def test_decision_freezes_best_positive_action_and_horizon():
    prediction = np.zeros((3, 8))
    prediction[0, 3] = 4.  # short, five bars
    prediction[1, :] = -1.
    prediction[2, 0] = 100.
    signal, horizon, _ = decide(prediction, np.array([True, True, False]))
    np.testing.assert_array_equal(signal, [-1, 0, 0])
    np.testing.assert_array_equal(horizon, [5, 10, 10])


def test_ridge_trace_reconstructs_prediction_without_future_input():
    x = np.arange(80, dtype=float).reshape(40, 2)
    y = np.column_stack([x[:, 0] * (j + 1) for j in range(8)])
    model = make_pipeline(StandardScaler(), Ridge(alpha=10.)).fit(x, y)
    values = np.array([3., 4.])
    predicted = model.predict(values[None, :])[0]
    trace = linear_trace(model, ["a", "b"], values, predicted, 0,
                         "2026-10-01T00:01:00+00:00")
    assert trace["realized_oracle_stress_net_usd_after_maturity"] is None
    assert trace["chosen_action_baseline_usd"] + sum(
        x["contribution_to_chosen_forecast_usd"] for x in trace["feature_contributions_usd"]
    ) == pytest.approx(predicted[0])
