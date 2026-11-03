import numpy as np
import pandas as pd
import pytest

from tools.cloud_learning_diagnostic import START, aligned_arrays, evaluate, score


def synthetic():
    times = pd.date_range(START, periods=25, freq="min")
    bars = pd.DataFrame({"timestamp": times})
    rows = [{"index": i, "available_at": (time + pd.Timedelta(minutes=1)).isoformat(),
             "ready": True, "action": 1 if i == 0 else 0,
             "predicted_gross_usd_immediate": float(i),
             "predicted_gross_usd_delayed": float(i)} for i, time in enumerate(times)]
    realized = np.full((25, 2), 10., dtype=float)
    realized[0] = [12., 8.]
    valid = np.ones(25, dtype=bool)
    return bars, rows, realized, valid


def test_alignment_rejects_future_availability_and_reorder():
    bars, rows, _, _ = synthetic()
    aligned_arrays(rows, bars)
    rows[0]["available_at"] = bars.timestamp.iloc[0].isoformat()
    with pytest.raises(ValueError, match="availability"):
        aligned_arrays(rows, bars)
    bars, rows, _, _ = synthetic()
    rows[0], rows[1] = rows[1], rows[0]
    with pytest.raises(ValueError, match="index coverage"):
        aligned_arrays(rows, bars)


def test_selected_outcomes_include_both_fill_delays_and_cost():
    bars, rows, realized, valid = synthetic()
    result = evaluate(rows, bars, realized, valid)
    assert result["selected_mature_count"] == 1
    assert result["immediate"]["selected_opportunity_mean_stress_net_usd"] == 6.
    assert result["delayed"]["selected_opportunity_mean_stress_net_usd"] == 2.
    valid[0] = False
    with pytest.raises(ValueError, match="No selected mature"):
        evaluate(rows, bars, realized, valid)


def test_quintiles_do_not_reorder_outcomes_independently():
    predicted = np.arange(20, dtype=float)
    realized = predicted[::-1].copy()
    result = score(predicted, realized)
    assert result["quintiles"][0]["realized_mean_usd"] > result["quintiles"][-1]["realized_mean_usd"]
    assert np.isclose(result["spearman"], -1.)
