from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from tools.cloud_paper_feed import submit
from tools.paper_decision_service import PaperRecorder


def test_append_only_feed_builds_causal_state_and_rejects_rewritten_prefix(tmp_path):
    start = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
    rows = []
    for i in range(63):
        price = 25000 + i * .25
        rows.append({"timestamp_utc": (start + timedelta(minutes=i)).isoformat(),
                     "open": price, "high": price + .5, "low": price - .5,
                     "close": price + .25, "volume": 100 + i})
    path = tmp_path / "feed.csv"
    state_path = tmp_path / "state.json"
    now = start + timedelta(minutes=61, seconds=10)

    def fake_engine(_root, _family, _fold, _observation, *, mode, now):
        assert mode == "paper"
        return {"action": "enter_long", "reason": "Test-only", "hash_lineage": {"test": "a" * 64},
                "live_authorized": False, "orders_submitted": 0}

    recorder = PaperRecorder(tmp_path / "journal.jsonl", tmp_path, "test", "test",
                             gate_usd=None, engine=fake_engine, clock=lambda: now)
    pd.DataFrame(rows[:61]).to_csv(path, index=False)
    first = submit(path, state_path, recorder, "audited-feed")
    assert first["event"]["status"] == "accepted"
    assert first["event"]["orders_submitted"] == 0
    now = start + timedelta(minutes=62, seconds=10)
    pd.DataFrame(rows[:62]).to_csv(path, index=False)
    second = submit(path, state_path, recorder, "audited-feed")
    assert second["event"]["status"] == "accepted"
    assert '"status": "paper_fill"' in recorder.journal.read_text()
    changed = rows[:63]
    changed[0] = {**changed[0], "volume": 999}
    pd.DataFrame(changed).to_csv(path, index=False)
    with pytest.raises(ValueError, match="Previously recorded feed bars changed"):
        submit(path, state_path, recorder, "audited-feed")
