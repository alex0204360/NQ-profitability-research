"""Load the frozen discovery replay and hash-pinned external MNQ bars.

The discovery source is the OHLCV array embedded in the archived replay.  Its
panel/date labels come from the original discovery daily ledger, rather than
from assumptions about calendar windows.  External bars are read only from the
archived public source and validated by response_evidence.source.external.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DISCOVERY_HTML = Path("experiments/reservoir_lab/response_evidence/results/discovery/replay.html")
DISCOVERY_DAILY = Path("experiments/reservoir_lab/response_evidence/results/discovery/daily.csv")
DISCOVERY_HTML_SHA256 = "de3a53aa1e88cb4f26fa47248ba7182dec86623e6abee3e9564323efc09f6a8a"
EXTERNAL_SHA256 = {
    "MNQ.csv": "129623f45308a98a1a345473ac5fe4d03d5d53f7dd177a608d946eb3d3d6ea99",
    "MNQ_5min.csv": "1e42bc9a8a682c19e7cd460ab003b522b8643bda23b70e5f8235633d1ccf08f4",
}
NY = "America/New_York"
OHLCV = ["open", "high", "low", "close", "volume"]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _load_discovery(root: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    html_path = root / DISCOVERY_HTML
    daily_path = root / DISCOVERY_DAILY
    html_sha = _sha256(html_path)
    if html_sha != DISCOVERY_HTML_SHA256:
        raise ValueError(f"discovery replay source hash mismatch: {html_sha}")

    html = html_path.read_text(encoding="utf-8")
    match = re.search(
        r'<script id="replay-data" type="application/json">(.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    if not match:
        raise ValueError("replay-data JSON script not found")
    payload = json.loads(match.group(1))
    sessions = payload.get("sessions")
    if not isinstance(sessions, list) or not sessions:
        raise ValueError("replay-data has no sessions")

    daily = pd.read_csv(daily_path, usecols=["panel", "date"])
    labels = daily.drop_duplicates().copy()
    labels["date"] = pd.to_datetime(labels["date"], errors="raise").dt.strftime("%Y-%m-%d")
    if labels["date"].duplicated().any():
        raise ValueError("daily ledger assigns a date to multiple panels")
    panel_by_date = dict(zip(labels.date, labels.panel))

    rows: list[dict[str, Any]] = []
    seen_dates: list[str] = []
    # The archived HTML groups sessions by experiment panel, so its array is
    # not a market-time sequence. Reassemble by the original session date.
    sessions = sorted(sessions, key=lambda session: str(session.get("date", "")))
    for session in sessions:
        date = str(session.get("date", ""))
        if date not in panel_by_date:
            raise ValueError(f"session date absent from original daily ledger: {date}")
        seen_dates.append(date)
        bars = session.get("bars")
        if not isinstance(bars, list) or len(bars) not in (389, 390):
            raise ValueError(f"unexpected OHLCV bar count for {date}: {len(bars) if isinstance(bars, list) else 'missing'}")
        for item in bars:
            if not isinstance(item, list) or len(item) < 6:
                raise ValueError(f"malformed bar in session {date}")
            minute, op, hi, lo, cl, vol = item[:6]
            rows.append({
                "timestamp": pd.Timestamp(date, tz=NY) + pd.Timedelta(minutes=int(minute)),
                "panel": panel_by_date[date],
                "date": date,
                "open": float(op), "high": float(hi), "low": float(lo),
                "close": float(cl), "volume": float(vol),
            })
    if seen_dates != sorted(seen_dates) or len(set(seen_dates)) != len(seen_dates):
        raise ValueError("replay sessions are not unique and in chronological order")
    if set(seen_dates) != set(panel_by_date) or len(seen_dates) != 40:
        raise ValueError("replay sessions do not exactly cover the original 40-session daily ledger")

    frame = pd.DataFrame(rows).set_index("timestamp").sort_index()
    frame.index.name = "timestamp"
    if not frame.index.is_unique or str(frame.index.tz) != NY:
        raise ValueError("discovery timestamps are duplicate or not New York timezone-aware")
    if not np.isfinite(frame[OHLCV].to_numpy(dtype=float)).all():
        raise ValueError("non-finite discovery OHLCV")
    if (frame.volume < 0).any() or (frame.high < frame[["open", "close"]].max(axis=1)).any() or (frame.low > frame[["open", "close"]].min(axis=1)).any():
        raise ValueError("invalid discovery OHLCV bounds")
    missing_minutes: dict[str, list[str]] = {}
    for date, group in frame.groupby("date", sort=False):
        expected = pd.date_range(f"{date} 09:30", periods=390, freq="min", tz=NY)
        if len(group) not in (389, 390) or group.index[0] != expected[0] or group.index[-1] != expected[-1]:
            raise ValueError(f"unexpected New York session span for {date}")
        absent = expected.difference(group.index)
        if len(absent) > 1 or not group.index.is_monotonic_increasing:
            raise ValueError(f"unexpected timestamp sequence for {date}")
        if len(absent):
            missing_minutes[date] = [stamp.isoformat() for stamp in absent]

    provenance = {
        "source": str(DISCOVERY_HTML),
        "sha256": html_sha,
        "daily_labels_source": str(DISCOVERY_DAILY),
        "session_count": len(seen_dates),
        "bar_count": len(frame),
        "timezone": NY,
        "missing_minutes": missing_minutes,
        "sessions": [{"date": d, "panel": panel_by_date[d]} for d in seen_dates],
    }
    return frame, provenance


def _load_external(root: Path, market_dir: Path) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Verify source hashes and QA through the repository's existing helper."""
    for name, expected in EXTERNAL_SHA256.items():
        path = market_dir / name
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(f"external source hash mismatch for {name}: {actual}")

    helper_path = root / "experiments/reservoir_lab/response_evidence/source.py"
    spec = importlib.util.spec_from_file_location("hold_work_response_source", helper_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load existing source validator at {helper_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    qa_dir = market_dir / "qa"
    minute_result = module.external(market_dir, qa_dir)

    # The existing helper hash-checks and jointly validates both files. Return
    # both resolutions, indexed on UTC-converted New York wall time.
    frames: dict[str, pd.DataFrame] = {"MNQ.csv": minute_result["external"]}
    five = pd.read_csv(market_dir / "MNQ_5min.csv")
    five.index = pd.DatetimeIndex(pd.to_datetime(five.pop("datetime"), utc=True)).tz_convert(NY)
    if not five.index.is_monotonic_increasing or not five.index.is_unique:
        raise ValueError("ambiguous five-minute timestamps")
    frames["MNQ_5min.csv"] = five
    qa = json.loads((qa_dir / "source.json").read_text(encoding="utf-8"))
    return frames, qa


def load_sources(
    repo_root: str | Path | None = None,
    market_dir: str | Path = "/workspace/work/market",
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], dict[str, Any]]:
    """Return (discovery bars, external bars, provenance).

    Discovery columns are ``panel``, ``date``, then OHLCV.  Its index is the
    original New York minute timestamp.  The external mapping is keyed by the
    two archived filenames; its OHLCV indexes are likewise New York-aware.
    """
    root = Path(repo_root).resolve() if repo_root is not None else ROOT
    discovery, discovery_provenance = _load_discovery(root)
    external, external_provenance = _load_external(root, Path(market_dir).resolve())
    provenance = {
        "discovery": discovery_provenance,
        "external": external_provenance,
        "external_hashes": EXTERNAL_SHA256.copy(),
        "external_source_commit": "60abd3fb6369c6ce0b6a4a65b0f2562fc96b1264",
    }
    return discovery, external, provenance
