import numpy as np
import pandas as pd
import pytest

from tools.physics_signal import diffusion_probability, filtered_signals


def test_probability_uses_only_32_completed_contiguous_closes():
    close = 100 + np.arange(50, dtype=float) + np.sin(np.arange(50))
    bars = pd.DataFrame({"close": close, "segment": np.ones(50, int)})
    side = np.ones(50, int)
    first, _, _ = diffusion_probability(bars, side)
    assert np.isnan(first[:31]).all()
    assert np.isfinite(first[31:]).all()
    bars.loc[40:, "close"] += 1000
    second, _, _ = diffusion_probability(bars, side)
    np.testing.assert_allclose(first[:40], second[:40], equal_nan=True)
    bars.loc[35:, "segment"] = 2
    third, _, _ = diffusion_probability(bars, side)
    assert np.isnan(third[35:50]).all()


def test_hysteresis_requires_previous_same_side_in_segment():
    gate = np.array([1, 1, -1, -1, 1, 1, 1])
    segments = np.array([1, 1, 1, 1, 1, 2, 2])
    probability = np.array([.7, .7, .7, .4, .7, .7, .7])
    result = filtered_signals(gate, probability, segments)
    np.testing.assert_array_equal(result["persistent_2bar"], [0, 1, 0, -1, 0, 0, 1])
    np.testing.assert_array_equal(result["persistent_and_diffusion"], [0, 1, 0, 0, 0, 0, 1])
    with pytest.raises(ValueError):
        filtered_signals(gate[:-1], probability, segments)
