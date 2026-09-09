"""Opt-in real research integration, invoked once per published tournament round.

Ordinary unit tests do not access research data. Set NQPROFIT_RUN_ROUND=1 or2
explicitly to execute the corresponding training stage and verify its ledger.
This test is not a profitability assertion and never opens heldout prices.
"""

import json
import os
from pathlib import Path

import pandas as pd
import pytest

from nqprofit.research import CUTOFF, run_round


@pytest.mark.parametrize("number", [1, 2])
def test_recorded_training_round_has_causal_costed_ledger(number):
    if os.environ.get("NQPROFIT_RUN_ROUND") != str(number):
        pytest.skip("explicit research round selection required")
    root = Path(__file__).resolve().parents[1]
    assert not (root / "history/heldout_access.json").exists()
    report = run_round(root, number)
    assert len(report["policies"]) == 2
    for policy in report["policies"]:
        assert policy["status"] in ("retained", "rejected", "failed")
        if policy["status"] != "retained":
            assert policy["reasons"]
        if policy["status"] == "failed":
            continue
        counted = 0
        for fold in range(1, 5):
            ledger = root / "reports/trades" / f"{policy['policy_id']}.fold{fold}.jsonl"
            previous_exit = None
            for line in ledger.read_text().splitlines():
                trade = json.loads(line)
                entry, exit_time = (
                    pd.Timestamp(trade["entry_time"]),
                    pd.Timestamp(trade["exit_time"]),
                )
                assert entry < CUTOFF
                assert 0 < (exit_time - entry).total_seconds() <= 45 * 60
                assert previous_exit is None or entry >= previous_exit
                previous_exit = exit_time
                if trade["exit_reason"] == "censored":
                    assert trade["net_points"] is None
                else:
                    assert trade["gross_points"] - trade["net_points"] == 1.0
                    assert 1 <= trade["resolution_bars"] <= trade["horizon"] <= 45
                    counted += 1
        assert counted == policy["summary"]["n"]
    assert not (root / "history/heldout_access.json").exists()
