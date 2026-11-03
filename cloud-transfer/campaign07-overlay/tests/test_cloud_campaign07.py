import numpy as np
import pytest

from tools.cloud_campaign07 import recent_confluence


def test_confluence_requires_same_side_within_three_contiguous_bars():
    setups = np.zeros((7, 2, 2), bool)
    setups[0, 0, 0] = True
    setups[1, 0, 0] = True
    setups[2, 1, 1] = True
    setups[4, 0, 0] = True
    gate = np.array([0, 0, -1, 1, 1, 1, -1])
    segments = np.array([1, 1, 1, 1, 2, 2, 2])
    filtered, reasons = recent_confluence(gate, setups, segments)
    np.testing.assert_array_equal(filtered, [0, 0, -1, 1, 1, 1, 0])
    assert reasons[-1] == "no_recent_same_side_chart_retest"


def test_confluence_rejects_bad_alignment():
    with pytest.raises(ValueError):
        recent_confluence(np.ones(3), np.zeros((2, 2, 2)), np.ones(3))
