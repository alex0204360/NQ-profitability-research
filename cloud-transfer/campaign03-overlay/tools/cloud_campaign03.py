"""Frozen $8 entries with one registered causal bracket exit versus time10."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from tools.causal_execution import replay_causal
from tools.fresh_transfer_test import delayed_signal, lower_bound, session_days
from tools.mnq_oracle_prepare import causal_features, load_candles, sha256
from tools.mnq_oracle_research import save_json
from tools.opportunity_research import FEATURES, verify_manifest, write_records
from tools.physics_state import physics_features
from tools.shared_game_state import build_market_states

ROOT = Path("/workspace")
CODE = Path(__file__).resolve().parents[1]
PRIOR = ROOT / "mnq-private-results"
PLAN = CODE / "docs/CLOUD_CAMPAIGN03.json"
OUT = PRIOR / "cloud_campaign03"


def run(out=OUT):
    out = Path(out)
    if out.exists():
        raise ValueError("Output must be new; historical attempts are immutable")
    plan = json.loads(PLAN.read_text())
    out.mkdir(parents=True)
    save_json(out / "protocol.json", plan)
    save_json(out / "source_hashes.json", {p.name: sha256(p) for p in
              (Path(__file__), PLAN, CODE / "tools/causal_execution.py",
               CODE / "tools/shared_game_state.py")})
    result = {"status": "running", "evaluations": [], "fit_count": 0,
              "selection": None, "sealed_2025_access": False, "orders_submitted": 0}
    try:
        hashes = {}
        verify_manifest(PRIOR / "fresh02", hashes)
        verify_manifest(PRIOR / "cloud_fresh03_lineage", hashes)
        reference = json.loads((PRIOR / "fresh02/protocol.json").read_text())
        model_path = PRIOR / "opportunity02/fold3__hist_gradient_boosting.joblib"
        if sha256(model_path) != reference["model_sha256"]:
            raise ValueError("Frozen baseline model changed")
        bundle = joblib.load(model_path)
        if bundle["features"] != FEATURES:
            raise ValueError("Frozen baseline feature schema changed")
        old = json.loads((PRIOR / "fresh02/results.json").read_text())
        for window in plan["windows"]:
            name = window["name"]
            path = (PRIOR / "fresh01/normalized_PRIVATE.csv" if name == "fresh02_oct13_29"
                    else PRIOR / "cloud_fresh03_lineage/normalized_PRIVATE.csv")
            bars, audit = load_candles([path])
            start, end = pd.Timestamp(window["start"]), pd.Timestamp(window["end_exclusive"])
            bars = bars[bars.timestamp < end].reset_index(drop=True)
            states = build_market_states(bars)
            ready = (states.ready & causal_features(bars).feature_ready &
                     physics_features(bars, states).physics_ready).to_numpy(bool)
            features = states.copy()
            features["log1p_atr14_ticks"] = np.log1p(features.atr14 / .25)
            if not np.isfinite(features.loc[ready, FEATURES].to_numpy(float)).all():
                raise ValueError("Invalid causal feature")
            raw = np.zeros(len(bars))
            raw[ready] = bundle["model"].predict(features.loc[ready, FEATURES].to_numpy(float))
            forecast = raw * reference["coefficient"] * states.atr14.fillna(0).to_numpy(float) * 2
            eval_mask = (bars.timestamp >= start).to_numpy()
            signal = np.where(eval_mask & ready & (abs(forecast) > 8), np.sign(forecast), 0).astype(int)
            write_records(out / (name + "_decisions_PRIVATE.jsonl.gz"), (
                {"index": int(i), "available_at": (bars.timestamp.iloc[i] + pd.Timedelta(minutes=1)).isoformat(),
                 "ready": bool(ready[i]), "forecast_usd": float(forecast[i]),
                 "action": int(signal[i]), "live_authorized": False}
                for i in np.flatnonzero(eval_mask)))
            days = sorted(set(session_days(bars.loc[eval_mask, "timestamp"])))
            for rule in ("time10", "atr1_target1.5_time30"):
                for delay in plan["delays_bars"]:
                    entry_signal = delayed_signal(signal, ready, bars.timestamp) if delay else signal
                    for cost_name, costs in plan["costs"].items():
                        metrics, trades, events = replay_causal(bars, entry_signal,
                            states.atr14.to_numpy(float), start, end, rule, costs)
                        if abs(metrics["net"] - sum(t["net"] for t in trades)) > 1e-8:
                            raise ValueError("Trade ledger mismatch")
                        if name == "fresh02_oct13_29" and rule == "time10":
                            previous = next(cell["metrics"] for cell in old["results"] if
                                cell["gate"] == 8 and cell["delay"] == delay and cell["cost"] == cost_name)
                            for metric in ("trades", "net", "max_drawdown_bar_close"):
                                if metrics[metric] != previous[metric]:
                                    raise ValueError("Frozen $8 control reproduction failed: " + metric)
                        key = f"{name}_{rule}_delay{delay}_{cost_name}"
                        write_records(out / (key + "_trades_PRIVATE.jsonl.gz"), trades)
                        write_records(out / (key + "_events_PRIVATE.jsonl.gz"), events)
                        cell = {"window": name, "rule": rule, "delay": delay,
                                "cost": cost_name, "metrics": metrics}
                        if cost_name == "stress":
                            cell["session_bootstrap"] = lower_bound(trades, days)
                        result["evaluations"].append(cell)
                        save_json(out / "results.json", result)
            result.setdefault("input_audits", {})[name] = audit
        if len(result["evaluations"]) != plan["evaluations"]:
            raise ValueError("Incomplete registered evaluation matrix")
        result["status"] = "complete_development_no_selection"
        save_json(out / "results.json", result)
        save_json(out / "manifest.json", {"completed": True,
                  "files_sha256": {p.name: sha256(p) for p in out.iterdir() if p.is_file() and p.name != "manifest.json"}})
        return result
    except Exception as exc:
        result.update(status="failed", error={"type": type(exc).__name__, "detail": str(exc)})
        save_json(out / "results.json", result)
        raise


if __name__ == "__main__":
    run()
