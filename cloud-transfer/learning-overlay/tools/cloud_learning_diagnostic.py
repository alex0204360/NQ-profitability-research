"""Aggregate, leakage-aware audit of the frozen dual-delay students.

No model is fitted and no signal or threshold is changed by this diagnostic.
The opened October upload remains development evidence only.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from tools.cloud_campaign01 import targets
from tools.mnq_oracle_prepare import load_candles, sha256
from tools.opportunity_research import read_records, verify_manifest

ROOT = Path("/workspace")
PRIOR = ROOT / "mnq-private-results"
OUTPUT = ROOT / "outputs/mnq_learning_diagnostic.json"
START = pd.Timestamp("2026-10-13T00:00:00Z")
END = pd.Timestamp("2026-10-30T00:00:00Z")
CANDIDATES = ("ridge_dual_delay", "extra_trees_dual_delay")
STRESS_ROUND_TRIP_USD = 6.0


def aligned_arrays(rows: list[dict], bars: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Reject stale/reordered decisions before joining predictions to outcomes."""
    expected = np.flatnonzero(((bars.timestamp >= START) & (bars.timestamp < END)).to_numpy())
    indices = np.asarray([row["index"] for row in rows], dtype=int)
    if len(indices) != len(expected) or not np.array_equal(indices, expected):
        raise ValueError("Decision index coverage differs from frozen evaluation candles")
    for row, index in zip(rows, indices):
        if pd.Timestamp(row["available_at"]) != bars.timestamp.iloc[index] + pd.Timedelta(minutes=1):
            raise ValueError("Decision availability differs from completed candle")
    ready = np.asarray([row["ready"] for row in rows], dtype=bool)
    predicted = np.asarray([[row["predicted_gross_usd_immediate"],
                             row["predicted_gross_usd_delayed"]] for row in rows], dtype=float)
    actions = np.asarray([row["action"] for row in rows], dtype=int)
    if predicted.shape != (len(rows), 2) or not np.isfinite(predicted).all():
        raise ValueError("Invalid dual-delay predictions")
    if not np.isin(actions, [-1, 0, 1]).all() or (actions[~ready] != 0).any():
        raise ValueError("Invalid or unready actions")
    return indices, predicted, actions


def score(predicted: np.ndarray, realized: np.ndarray) -> dict:
    """Quintile means are descriptive; overlapping minute labels are dependent."""
    if len(predicted) < 20 or len(predicted) != len(realized):
        raise ValueError("Too few aligned observations")
    order = np.argsort(predicted, kind="stable")
    quintiles = []
    for part in np.array_split(order, 5):
        quintiles.append({"count": len(part), "predicted_mean_usd": float(predicted[part].mean()),
                          "realized_mean_usd": float(realized[part].mean())})
    denominator = float(np.square(realized - realized.mean()).sum())
    return {"count": len(predicted), "predicted_range_usd": [float(predicted.min()), float(predicted.max())],
            "realized_mean_usd": float(realized.mean()),
            "mean_absolute_error_usd": float(np.abs(predicted - realized).mean()),
            "pearson": float(np.corrcoef(predicted, realized)[0, 1]),
            "spearman": float(spearmanr(predicted, realized).statistic),
            "r2": float(1 - np.square(predicted - realized).sum() / denominator),
            "quintiles": quintiles}


def evaluate(rows: list[dict], bars: pd.DataFrame, realized: np.ndarray, valid: np.ndarray) -> dict:
    indices, predicted, actions = aligned_arrays(rows, bars)
    ready = np.asarray([row["ready"] for row in rows], dtype=bool)
    eligible = ready & valid[indices]
    if not eligible.any():
        raise ValueError("No mature contiguous ready outcomes")
    selected = eligible & (actions != 0)
    if not selected.any():
        raise ValueError("No selected mature outcomes")
    direction = actions[selected, None]
    net = direction * realized[indices[selected]] - STRESS_ROUND_TRIP_USD
    return {"decision_count": len(rows), "ready_count": int(ready.sum()),
            "mature_contiguous_ready_count": int(eligible.sum()),
            "selected_mature_count": int(selected.sum()),
            "selected_long_count": int((actions[selected] == 1).sum()),
            "selected_short_count": int((actions[selected] == -1).sum()),
            "immediate": {**score(predicted[eligible, 0], realized[indices[eligible], 0]),
                          "selected_opportunity_mean_stress_net_usd": float(net[:, 0].mean()),
                          "selected_opportunity_positive_stress_fraction": float((net[:, 0] > 0).mean())},
            "delayed": {**score(predicted[eligible, 1], realized[indices[eligible], 1]),
                        "selected_opportunity_mean_stress_net_usd": float(net[:, 1].mean()),
                        "selected_opportunity_positive_stress_fraction": float((net[:, 1] > 0).mean())}}


def run(output: Path = OUTPUT) -> dict:
    hashes: dict[str, str] = {}
    verify_manifest(PRIOR / "cloud_campaign01_retry2", hashes)
    upload = PRIOR / "fresh01/normalized_PRIVATE.csv"
    manifest = json.loads((PRIOR / "fresh01/manifest.json").read_text())
    if manifest["status"] != "blocked_data_integrity" or sha256(upload) != manifest["files_sha256"][upload.name]:
        raise ValueError("Frozen upload hash/status mismatch")
    bars, audit = load_candles([upload])
    bars = bars[bars.timestamp < END].reset_index(drop=True)
    realized, valid = targets(bars, END)
    report = {"status": "exploratory_development_diagnostic", "source": audit,
              "input_manifest_sha256": {"fresh01": sha256(PRIOR / "fresh01/manifest.json"),
                                        "campaign01": sha256(PRIOR / "cloud_campaign01_retry2/manifest.json")},
              "method": "Frozen 10-bar immediate/delayed predictions aligned to matured, gap-free upload outcomes; $6 stress round trip. Each minute opportunity overlaps others; counts are not independent trades or significance tests.",
              "limitations": ["Opened October development observations", "Yahoo contract/roll/timestamp identity unverified",
                              "Gross opportunity labels exclude occupancy; replay trade net is separate",
                              "No live or prospective result"], "candidates": {}}
    for name in CANDIDATES:
        rows = read_records(PRIOR / f"cloud_campaign01_retry2/{name}_decisions_PRIVATE.jsonl.gz")
        report["candidates"][name] = evaluate(rows, bars, realized, valid)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return report


if __name__ == "__main__":
    run()
