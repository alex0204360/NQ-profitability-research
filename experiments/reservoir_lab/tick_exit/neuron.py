"""One symmetric ReLU layer appended to the frozen point-valued readout."""
import json
from pathlib import Path

import numpy as np
import pandas as pd


def tick_exit(forecast):
    weights = json.loads(Path(__file__).with_name("weights.json").read_text())
    x = forecast.to_numpy(dtype=float).reshape(-1, 1)
    hidden = np.maximum(0., x @ np.asarray(weights["hidden_weight"]).T + weights["hidden_bias"])
    score = hidden @ np.asarray(weights["readout_weight"]).T + weights["readout_bias"]
    return pd.Series(score.ravel(), index=forecast.index, name="tick_exit")
