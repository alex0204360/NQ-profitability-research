import json

import numpy as np
import pandas as pd
import pytest

from tools.cloud_campaign04 import PLAN, configurations, decision, fold_arrays


def test_exactly_100_unique_reproducible_trials():
    plan = json.loads(PLAN.read_text())
    first, second = configurations(plan), configurations(plan)
    assert len(first) == 100 and first == second
    assert len({tuple(row.values()) for row in first}) == 100


def test_decision_requires_positive_worst_fill_value():
    prediction = np.array([[2., -1.], [-1., 3.], [0., -2.], [2., 3.], [100., -1.]])
    np.testing.assert_array_equal(decision(prediction, np.array([1, 1, 1, 1, 0], bool)),
                                  [1, -1, 0, -1, 0])
    with pytest.raises(ValueError):
        decision(np.array([[float("nan"), 1.]]), np.array([True]))


def test_chronological_fold_purges_training_and_gaps():
    times = pd.date_range("2026-09-20T00:00Z", periods=4000, freq="min")
    bars = pd.DataFrame({"timestamp": times, "segment": np.ones(4000, int),
                         "open": np.full(4000, 100.), "close": np.full(4000, 101.)})
    features = np.arange(4000, dtype=float)[:, None]
    ready = np.ones(4000, bool)
    train_x, _, val_x, _ = fold_arrays(bars, features, ready,
                                      pd.Timestamp("2026-09-21T00:00Z"),
                                      pd.Timestamp("2026-09-21T00:00Z"),
                                      pd.Timestamp("2026-09-22T00:00Z"), 60)
    assert train_x.max() < 1380  # 60-minute purge before September 21
    assert val_x.min() >= 1440
    assert val_x.max() < 2880
