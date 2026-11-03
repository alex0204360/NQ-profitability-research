import numpy as np
import pandas as pd

from tools.cloud_campaign08 import calibration_diagnostic


def test_diffusion_calibration_uses_mature_contiguous_execution_labels():
    bars = pd.DataFrame({"timestamp": pd.date_range("2026-10-13T00:00Z", periods=40, freq="min"),
                         "segment": np.ones(40, int), "open": np.full(40, 100.),
                         "close": np.full(40, 100.)})
    gate = np.ones(40, int)
    probability = np.full(40, .5)
    result = calibration_diagnostic(bars, gate, probability,
                                    pd.Timestamp("2026-10-13T00:00Z"),
                                    pd.Timestamp("2026-10-13T00:40Z"))
    assert result["count"] < len(bars)
    assert result["observed_positive_rate"] == 0.
    assert result["brier"] == .25
    assert result["base_rate_brier"] == 0.
    bars.loc[11:, "segment"] = 2
    changed = calibration_diagnostic(bars, gate, probability,
                                     pd.Timestamp("2026-10-13T00:00Z"),
                                     pd.Timestamp("2026-10-13T00:40Z"))
    assert changed["count"] < result["count"]
