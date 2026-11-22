"""Score frozen return-map heads on exposed MNQ panels with source audit.

The optional November tape is admitted only after its exact capture receipt (or
an explicitly declared revision) and the archived reservoir replay are checked.
No prospective source is loaded by this program.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PATH_ORDER = HERE.parent / "path_order"
sys.path.insert(0, str(PATH_ORDER))

from brain import activations  # noqa: E402
from data import HASHES, discovery, regular_hours  # noqa: E402
from evaluate import describe, paired  # noqa: E402
from execution import replay  # noqa: E402
from circuit import encode  # noqa: E402


WINDOWS = {
    "extension1": ("2026-11-03", "2026-11-06", "november-extension/capture-1.json"),
    "extension2": ("2026-11-09", "2026-11-13", "november-extension/capture-2.json"),
    "november": ("2026-11-16", "2026-11-20", "november/capture-receipt.json"),
}
REISSUED_HASHES = {
    "extension1": "7075895d804ccbd0c075b9873f505fb1635453160e9907807a5d20e1c0588dc3",
    "extension2": "2ae01b6cc21b1acee76c42679e52a74eb3e26129283a52eabb9e37762699d45b",
    "november": "77617fd542ace63e7ab60e081280a980489ed7ee06bf516925096b114fdd128d",
}
ARCHIVE = {"extension": PATH_ORDER / "november-extension", "november": PATH_ORDER / "november"}
FEES = (3.0, 6.0)
DELAYS = (0, 1)
LEDGER_FIELDS = ["signal_time", "entry_time", "exit_time", "side", "entry", "exit",
                 "gross_usd", "net_usd", "reason"]
FILL_FIELDS = ["entry", "exit", "gross_usd", "net_usd"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_dates(start: str, end: str) -> list[str]:
    return [x.strftime("%Y-%m-%d") for x in pd.bdate_range(start, end)]


def checked_window(path: Path, key: str, reissued: bool) -> tuple[pd.DataFrame, dict]:
    start, end, receipt_file = WINDOWS[key]
    receipt = json.loads((PATH_ORDER / receipt_file).read_text())
    actual = digest(path)
    expected = receipt["csv_sha256"]
    if actual != expected and not reissued:
        raise ValueError(f"{key}: CSV SHA-256 {actual} differs from receipt {expected}; use --reissued to label a revised tape")
    if actual != expected and actual != REISSUED_HASHES[key]:
        raise ValueError(f"{key}: unregistered reissue SHA-256 {actual}; expected {REISSUED_HASHES[key]}")
    bars = regular_hours(pd.read_csv(path), start, end)
    counts = bars.groupby(bars.index.strftime("%Y-%m-%d")).size().to_dict()
    dates = expected_dates(start, end)
    if list(counts) != dates or any(counts[day] != 390 for day in dates):
        raise ValueError(f"{key}: expected exactly 390 regular-hours bars on each of {dates}; got {counts}")
    for day in dates:
        t = bars.loc[day].index
        if t[0].strftime("%H:%M") != "09:30" or t[-1].strftime("%H:%M") != "15:59" or not (t[1:] - t[:-1] == pd.Timedelta(minutes=1)).all():
            raise ValueError(f"{key}: incomplete regular-hours minute grid on {day}")
    return bars, {"window": key, "path": f"{key}/bars.csv", "csv_sha256": actual,
                  "receipt_csv_sha256": expected, "receipt_source_sha256": receipt.get("source_sha256"),
                  "receipt_url": receipt.get("url"), "identity": "exact_receipt" if actual == expected else "reissued",
                  "dates": dates, "regular_hours_bars": len(bars)}


def compare_ledger(actual: pd.DataFrame, archived_path: Path) -> dict:
    archived = pd.read_csv(archived_path)
    def rows(frame):
        return Counter(tuple(round(float(row[k]), 8) if k in FILL_FIELDS else str(row[k])
                             for k in LEDGER_FIELDS) for _, row in frame.iterrows())
    current_rows, archived_rows = rows(actual), rows(archived)
    matching = sum((current_rows & archived_rows).values())
    return {"actual_trades": len(actual), "archived_trades": len(archived),
            "exact_matching_trade_rows": matching,
            "exact_ledger_match": current_rows == archived_rows}


def verify_reservoir(bars: pd.DataFrame, archive: Path, require_exact: bool) -> dict:
    signal = activations(bars, "reservoir")["reservoir"]
    saved = json.loads((archive / "results.json").read_text())
    if len(bars) != saved["bars"] or [str(d) for d in np.unique(bars.index.date)] != saved["dates"]:
        raise ValueError(f"reservoir archive coverage differs from {archive}")
    audit = {}
    for delay in DELAYS:
        for fee in FEES:
            label = f"delay{delay}_cost{int(fee)}"
            trades, marks = replay(bars, signal, delay=delay, cost=fee)
            summary, daily = describe(trades, marks, np.unique(bars.index.date))
            old = saved["replays"][label]["reservoir"]
            fields = ("trades", "gross", "net", "drawdown")
            metrics_match = all(np.isclose(summary[field], old[field], rtol=0, atol=1e-8) for field in fields)
            prior_daily = pd.read_csv(archive / f"{label}-daily.csv")
            daily_match = bool(np.allclose(daily.to_numpy(dtype=float), prior_daily["reservoir"].to_numpy(dtype=float), rtol=0, atol=1e-8))
            ledger = None
            if fee == 3:
                ledger = compare_ledger(trades, archive / f"reservoir-delay{delay}.csv")
            exact = metrics_match and daily_match and (ledger is None or ledger["exact_ledger_match"])
            if require_exact and not exact:
                raise ValueError(f"reservoir {label} differs from frozen archive {archive}")
            audit[label] = {"archived": {field: old[field] for field in fields},
                            "actual": {field: summary[field] for field in fields},
                            "actual_minus_archived": {field: summary[field] - old[field] for field in fields},
                            "daily_exact_match": daily_match, "ledger": ledger,
                            "exact_reproduction": exact}
    return audit


def prepare_panels(discovery_dir: Path, november_dir: Path | None, reissued: bool) -> tuple[dict, dict]:
    bars = discovery(discovery_dir)
    audit = {"discovery": {"identity": "exact_receipt", "source_commit": "8336fe8",
                           "files": [{"path": f"MNQ_Yahoo_1m_20260913_20261012_part{i:02d}.csv", "sha256": h}
                                     for i, h in enumerate(HASHES, 1)],
                           "dates": [str(d) for d in np.unique(bars.index.date)], "regular_hours_bars": len(bars)}}
    audit["discovery"]["reservoir_reproduction"] = verify_reservoir(bars, PATH_ORDER / "discovery", True)
    panels = {"discovery": bars}
    if november_dir is None:
        return panels, audit
    windows = {}
    for key in ("extension1", "extension2", "november"):
        windows[key], audit[key] = checked_window(november_dir / key / "bars.csv", key, reissued)
    extension = pd.concat([windows["extension1"], windows["extension2"]])
    # Reproduce exact captures. Quantify revision sensitivity on pinned reissues.
    audit["reservoir_reproduction"] = {
        "extension": verify_reservoir(extension, ARCHIVE["extension"],
                                      all(audit[k]["identity"] == "exact_receipt" for k in ("extension1", "extension2"))),
        "november": verify_reservoir(windows["november"], ARCHIVE["november"],
                                     audit["november"]["identity"] == "exact_receipt"),
    }
    panels["extension"] = extension
    panels["november"] = windows["november"]
    panels["november_all"] = pd.concat([extension, windows["november"]])
    panels["combined34"] = pd.concat([bars, extension, windows["november"]])
    audit["november_identity"] = "exact_receipt" if all(audit[k]["identity"] == "exact_receipt" for k in WINDOWS) else "reissued"
    audit["reproduction_interpretation"] = ("Frozen archive reproduced" if audit["november_identity"] == "exact_receipt"
                                            else "Reissued vendor tape differs from frozen archive; temporal re-score only, not archive replication")
    return panels, audit


def score_panel(panel: str, bars: pd.DataFrame) -> tuple[list[dict], list[dict], list[pd.DataFrame]]:
    states = encode(bars)
    if not states.index.equals(bars.index):
        raise ValueError(f"{panel}: encoded index must match bars")
    required = {"return_map", "equal_mass"}
    if not required.issubset(states.columns):
        raise ValueError(f"{panel}: circuit.encode lacks {required - set(states.columns)}")
    heads = ["return_map", "equal_mass"]
    heads.extend(k for k in ("confirmed", "confirmed_equal") if k in states.columns)
    baseline = activations(bars, "reservoir")
    signals = {"cash": pd.Series(0.0, index=bars.index), "reservoir": baseline["reservoir"]}
    signals.update({k: states[k].astype(float) for k in heads})
    calendar = np.unique(bars.index.date)
    summaries, daily_rows, ledgers = [], [], []
    for delay in DELAYS:
        for fee in FEES:
            daily = {}
            for name, signal in signals.items():
                trades, marks = replay(bars, signal, delay=delay, cost=fee)
                result, daily[name] = describe(trades, marks, calendar)
                summaries.append({"panel": panel, "delay": delay, "cost_usd": fee, "head": name,
                                  **{k: v for k, v in result.items() if k != "by_side"}})
                if name != "cash" and fee == 3 and panel in {"discovery", "extension", "november"}:
                    activation = (baseline if name == "reservoir" else states).reindex(trades.signal_time)
                    activation.index = trades.index
                    ledger = pd.concat([trades, activation.add_prefix("state_")], axis=1)
                    ledger.insert(0, "head", name)
                    ledger.insert(0, "cost_usd", fee)
                    ledger.insert(0, "delay", delay)
                    ledger.insert(0, "panel", panel)
                    ledgers.append(ledger)
            for name in signals:
                for date, value in daily[name].items():
                    daily_rows.append({"panel": panel, "delay": delay, "cost_usd": fee,
                                       "head": name, "et_date": str(date), "net_change_usd": float(value)})
            for row in summaries:
                if row["panel"] == panel and row["delay"] == delay and row["cost_usd"] == fee:
                    name = row["head"]
                    for reference in ("cash", "reservoir", "equal_mass", "confirmed_equal"):
                        if reference in daily and name != reference:
                            comparison = paired(daily[name], daily[reference])
                            row[f"vs_{reference}_mean_usd_per_day"] = comparison["mean_usd_per_day"]
                            row[f"vs_{reference}_block95"] = json.dumps(comparison["block95"])
    return summaries, daily_rows, ledgers


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discovery", type=Path, default=Path("/tmp/mnq-exposed/discovery"))
    parser.add_argument("--november-dir", type=Path, help="directory containing november, extension1 and extension2/bars.csv")
    parser.add_argument("--reissued", action="store_true", help="score the three pinned reissued CSVs and measure baseline revisions")
    parser.add_argument("--out", type=Path, default=Path("/tmp/return-map-score"))
    args = parser.parse_args(argv)
    if args.reissued and args.november_dir is None:
        parser.error("--reissued requires --november-dir")
    panels, audit = prepare_panels(args.discovery, args.november_dir, args.reissued)
    summaries, daily, ledgers = [], [], []
    for name, bars in panels.items():
        s, d, l = score_panel(name, bars)
        summaries.extend(s)
        daily.extend(d)
        ledgers.extend(l)
    args.out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(summaries).to_csv(args.out / "summaries.csv", index=False, float_format="%.9g")
    pd.DataFrame(daily).to_csv(args.out / "daily.csv", index=False, float_format="%.9g")
    if ledgers:
        pd.concat(ledgers, ignore_index=True).to_csv(args.out / "trades.csv", index=False, float_format="%.9g")
    audit["panels"] = {name: {"regular_hours_bars": len(bars), "dates": [str(d) for d in np.unique(bars.index.date)]}
                       for name, bars in panels.items()}
    audit["new_head_source"] = "circuit.encode; decision-time states only"
    audit["execution_source"] = "experiments/path_order/execution.py"
    audit["execution_sha256"] = digest(PATH_ORDER / "execution.py")
    audit["scoring_files_sha256"] = {name: digest(HERE / name) for name in ("circuit.py", "weights.json", "score.py")}
    (args.out / "source_audit.json").write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n")
    print(f"Wrote {args.out} for {', '.join(panels)}")


if __name__ == "__main__":
    main()
