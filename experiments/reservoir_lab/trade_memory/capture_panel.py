"""Capture and verify the preregistered six-session MNQ trade-memory panel.

Raw Yahoo chart responses stay in a private scratch directory. This utility
normalizes only the six registered New York RTH sessions into ``bars.csv``.
It never requests any other market dates or evaluates a strategy.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


CONTRACT = "MNQZ26"
SYMBOL = "MNQZ26.CME"
DATES = tuple(date(2026, 10, d) for d in range(26, 31)) + (date(2026, 11, 2),)
NY = ZoneInfo("America/New_York")
UTC = timezone.utc
FIELDS = ("open", "high", "low", "close", "volume")
DEFAULT_OUT = Path("/workspace/scratch/mnq-trade-memory-panel")
DEFAULT_RECEIPT = Path(__file__).with_name("capture_receipt.json")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def session_bounds(day: date) -> tuple[datetime, datetime]:
    return (datetime.combine(day, time(9, 30), NY),
            datetime.combine(day, time(16, 0), NY))


def url_for(start: datetime, end: datetime, host: str) -> str:
    params = urllib.parse.urlencode({
        "period1": int(start.timestamp()),
        "period2": int(end.timestamp()),
        "interval": "1m",
        "includePrePost": "true",
    })
    return f"https://{host}/v8/finance/chart/{urllib.parse.quote(SYMBOL, safe='=.')}?{params}"


def request_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=45) as response:
        return response.read()


def immutable_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"refusing to replace immutable capture {path}")
        return
    with path.open("xb") as f:
        f.write(payload)


def load_chart(payload: bytes) -> tuple[dict, list[int], dict[str, list]]:
    root = json.loads(payload)
    chart = root.get("chart") or {}
    if chart.get("error"):
        raise ValueError(f"Yahoo chart error: {chart['error']}")
    result = chart.get("result") or []
    if len(result) != 1:
        raise ValueError("Yahoo returned no unique chart result")
    item = result[0]
    meta = item.get("meta") or {}
    expected = {
        "symbol": SYMBOL,
        "instrumentType": "FUTURE",
        "exchangeName": "CME",
        "dataGranularity": "1m",
        "exchangeTimezoneName": "America/New_York",
    }
    for field, value in expected.items():
        if meta.get(field) != value:
            raise ValueError(f"unexpected Yahoo metadata for {field}")
    stamps = item.get("timestamp") or []
    quotes = (item.get("indicators", {}).get("quote") or [])
    if len(quotes) != 1:
        raise ValueError("Yahoo response has no unique OHLCV quote block")
    arrays = {name: quotes[0].get(name) or [] for name in FIELDS}
    if any(len(arrays[name]) != len(stamps) for name in FIELDS):
        raise ValueError("timestamp/OHLCV arrays have different lengths")
    return meta, stamps, arrays


def normalize_day(payload: bytes, day: date) -> tuple[list[dict], dict]:
    _, stamps, arrays = load_chart(payload)
    expected_start, _ = session_bounds(day)
    expected = [expected_start + timedelta(minutes=i) for i in range(390)]
    indexed = []
    out_of_session = 0
    incomplete = 0
    for i, epoch in enumerate(stamps):
        stamp = datetime.fromtimestamp(epoch, UTC)
        local = stamp.astimezone(NY)
        if local.date() != day or not (time(9, 30) <= local.time() < time(16, 0)):
            out_of_session += 1
            continue
        values = [arrays[field][i] for field in FIELDS]
        if any(v is None for v in values):
            incomplete += 1
            continue
        try:
            nums = [float(v) for v in values]
        except (TypeError, ValueError):
            incomplete += 1
            continue
        if not all(math.isfinite(v) for v in nums):
            incomplete += 1
            continue
        row = dict(timestamp_utc=stamp, contract=CONTRACT,
                   **dict(zip(FIELDS, nums, strict=True)))
        indexed.append(row)

    times = [row["timestamp_utc"].astimezone(NY) for row in indexed]
    duplicate_count = len(times) - len(set(times))
    sorted_unique = times == sorted(set(times))
    seen = set(times)
    missing = sum(stamp not in seen for stamp in expected)
    expected_set = set(expected)
    extra = sum(stamp not in expected_set for stamp in times)
    valid_values = True
    for row in indexed:
        o, h, l, c, v = (row[k] for k in FIELDS)
        if (v < 0 or l > min(o, c) or h < max(o, c) or
                any(abs(x * 4 - round(x * 4)) > 1e-8 for x in (o, h, l, c))):
            valid_values = False
            break
    ready = (len(indexed) == 390 and duplicate_count == 0 and missing == 0
             and extra == 0 and sorted_unique and valid_values)
    diagnostics = {
        "ready": ready,
        "expected_rth_minutes": 390,
        "valid_rth_rows": len(indexed),
        "outside_rth_or_other_date_rows": out_of_session,
        "incomplete_or_nonfinite_rows": incomplete,
        "missing_grid_minutes": missing,
        "extra_grid_minutes": extra,
        "duplicate_rth_timestamps": duplicate_count,
        "timestamps_sorted_unique": sorted_unique,
        "ohlcv_and_mnq_tick_grid_valid": valid_values,
        "first_rth_utc": indexed[0]["timestamp_utc"].isoformat() if indexed else None,
        "last_rth_utc": indexed[-1]["timestamp_utc"].isoformat() if indexed else None,
    }
    return indexed if ready else [], diagnostics


def rows_csv(rows: list[dict]) -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["timestamp_utc", "contract", *FIELDS])
    for row in rows:
        stamp = row["timestamp_utc"].astimezone(UTC).isoformat().replace("+00:00", "Z")
        writer.writerow([stamp, row["contract"], *(format(row[k], ".12g") for k in FIELDS)])
    return buf.getvalue().encode("utf-8")


def capture_one(day: date, out: Path, attempts: list[dict]) -> dict | None:
    start, end = session_bounds(day)
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        url = url_for(start, end, host)
        try:
            payload = request_bytes(url)
        except Exception as exc:  # record and continue to the prescribed fallback
            attempts.append({"url": url, "status": "request_failed", "error": f"{type(exc).__name__}: {exc}"})
            continue
        raw_path = Path("raw") / f"{day.isoformat()}_{host.split('.')[0]}_single.json"
        immutable_write(out / raw_path, payload)
        try:
            rows, diag = normalize_day(payload, day)
        except Exception as exc:
            attempts.append({"url": url, "raw_path": raw_path.as_posix(),
                             "raw_sha256": sha256(payload), "status": "invalid_response",
                             "error": f"{type(exc).__name__}: {exc}"})
            continue
        attempts.append({"url": url, "raw_path": raw_path.as_posix(),
                         "raw_sha256": sha256(payload), "status": "parsed",
                         "valid_rth_rows": diag["valid_rth_rows"], "ready": diag["ready"]})
        if diag["ready"]:
            return {"rows": rows, "diagnostics": diag, "url": url,
                    "raw_path": raw_path.as_posix(), "raw_sha256": sha256(payload),
                    "raw_bytes": len(payload)}
    return None


def fallback_groups(out: Path, attempts_by_day: dict[str, list[dict]]) -> dict[date, dict]:
    """If single-day requests fail/incomplete, try the permitted five-day span and host fallback."""
    remaining = {date.fromisoformat(s) for s, tries in attempts_by_day.items()
                 if not any(t.get("ready") for t in tries)}
    recovered: dict[date, dict] = {}
    groups = [DATES[:5], DATES[5:]]
    for days in groups:
        pending = [d for d in days if d in remaining]
        if not pending:
            continue
        start = session_bounds(days[0])[0]
        end = session_bounds(days[-1])[1]
        for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
            url = url_for(start, end, host)
            try:
                payload = request_bytes(url)
            except Exception as exc:
                for day in pending:
                    attempts_by_day[day.isoformat()].append({
                        "url": url, "status": "fallback_request_failed",
                        "error": f"{type(exc).__name__}: {exc}"})
                continue
            label = f"{days[0].isoformat()}_to_{days[-1].isoformat()}_{host.split('.')[0]}_fallback.json"
            raw_path = Path("raw") / label
            immutable_write(out / raw_path, payload)
            for day in pending:
                try:
                    rows, diag = normalize_day(payload, day)
                except Exception as exc:
                    attempts_by_day[day.isoformat()].append({
                        "url": url, "raw_path": raw_path.as_posix(), "raw_sha256": sha256(payload),
                        "status": "fallback_invalid_response", "error": f"{type(exc).__name__}: {exc}"})
                    continue
                attempts_by_day[day.isoformat()].append({
                    "url": url, "raw_path": raw_path.as_posix(), "raw_sha256": sha256(payload),
                    "status": "fallback_parsed", "valid_rth_rows": diag["valid_rth_rows"],
                    "ready": diag["ready"]})
                if diag["ready"] and day not in recovered:
                    recovered[day] = {"rows": rows, "diagnostics": diag, "url": url,
                                      "raw_path": raw_path.as_posix(), "raw_sha256": sha256(payload),
                                      "raw_bytes": len(payload)}
            if all(day in recovered for day in pending):
                break
    return recovered


def make_receipt(out: Path, day_results: dict[date, dict], attempts: dict[str, list[dict]],
                 bars_bytes: bytes, captured_at: str) -> dict:
    days = []
    for day in DATES:
        result = day_results.get(day)
        entry = {"date_new_york": day.isoformat(), "attempts": attempts[day.isoformat()]}
        if result:
            entry.update(result["diagnostics"])
            entry.update({"source_url": result["url"], "raw_path": result["raw_path"],
                          "raw_sha256": result["raw_sha256"], "raw_bytes": result["raw_bytes"]})
        else:
            entry.update({"ready": False, "expected_rth_minutes": 390,
                          "valid_rth_rows": 0, "reason": "no complete validated 390-minute source"})
        days.append(entry)
    return {
        "schema_version": 1,
        "captured_at_utc": captured_at,
        "provider": "Yahoo Finance chart endpoint (unofficial; raw responses retained privately)",
        "symbol": SYMBOL,
        "contract": CONTRACT,
        "instrument_type": "FUTURE",
        "exchange": "CME",
        "exchange_timezone": "America/New_York",
        "interval": "1m",
        "bar_timestamp_assumption": "minute start, consistent with registered paper_day helper",
        "rth_local": {"start": "09:30", "end_exclusive": "16:00", "grid_minutes": 390},
        "registered_dates_new_york": [d.isoformat() for d in DATES],
        "panel_ready": all(item.get("ready", False) for item in days),
        "private_output_directory": str(out),
        "normalized_csv": "bars.csv",
        "normalized_csv_sha256": sha256(bars_bytes),
        "normalized_csv_rows": sum(item.get("valid_rth_rows", 0) for item in days),
        "days": days,
    }


def run_capture(out: Path, receipt_path: Path) -> dict:
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"private output is not empty; preserving immutable captures at {out}")
    if receipt_path.exists():
        raise ValueError(f"receipt already exists and is immutable: {receipt_path}")
    out.mkdir(parents=True, exist_ok=True)
    attempts = {d.isoformat(): [] for d in DATES}
    results: dict[date, dict] = {}
    for day in DATES:
        one = capture_one(day, out, attempts[day.isoformat()])
        if one:
            results[day] = one
    recovered = fallback_groups(out, attempts)
    results.update(recovered)

    combined = []
    for day in DATES:
        if day in results:
            combined.extend(results[day]["rows"])
    bars_bytes = rows_csv(combined)
    immutable_write(out / "bars.csv", bars_bytes)
    receipt = make_receipt(out, results, attempts, bars_bytes,
                           datetime.now(UTC).isoformat().replace("+00:00", "Z"))
    receipt_bytes = (json.dumps(receipt, indent=2, allow_nan=False) + "\n").encode()
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    with receipt_path.open("xb") as f:
        f.write(receipt_bytes)
    return receipt


def verify(out: Path, receipt_path: Path) -> dict:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("symbol") != SYMBOL or receipt.get("registered_dates_new_york") != [d.isoformat() for d in DATES]:
        raise ValueError("receipt does not match the registered symbol/date panel")
    day_results = {}
    attempts = {d.isoformat(): [] for d in DATES}
    for item in receipt["days"]:
        day = date.fromisoformat(item["date_new_york"])
        attempts[day.isoformat()] = item.get("attempts", [])
        for attempt in attempts[day.isoformat()]:
            if "raw_path" in attempt:
                data = (out / attempt["raw_path"]).read_bytes()
                if sha256(data) != attempt["raw_sha256"]:
                    raise ValueError(f"attempt hash mismatch for {day}")
                if "ready" in attempt:
                    _, diag = normalize_day(data, day)
                    if (diag["ready"] != attempt["ready"] or
                            diag["valid_rth_rows"] != attempt["valid_rth_rows"]):
                        raise ValueError(f"attempt diagnostics mismatch for {day}")
        path = out / item["raw_path"] if item.get("raw_path") else None
        if path is None or not path.exists():
            if item.get("ready"):
                raise ValueError(f"missing immutable raw capture for {day}")
            continue
        payload = path.read_bytes()
        if sha256(payload) != item.get("raw_sha256"):
            raise ValueError(f"raw capture hash mismatch for {day}")
        rows, diag = normalize_day(payload, day)
        if diag != {k: item.get(k) for k in diag}:
            raise ValueError(f"readiness diagnostics changed for {day}")
        if item.get("ready"):
            day_results[day] = {"rows": rows, "diagnostics": diag}
    combined = [row for day in DATES for row in day_results.get(day, {}).get("rows", [])]
    serialized = rows_csv(combined)
    bars_path = out / "bars.csv"
    if not bars_path.exists() or bars_path.read_bytes() != serialized:
        raise ValueError("normalized bars.csv does not reproduce from the retained raw captures")
    if sha256(serialized) != receipt.get("normalized_csv_sha256"):
        raise ValueError("normalized CSV hash differs from receipt")
    return {"verified": True, "panel_ready": receipt["panel_ready"],
            "days_ready": sum(bool(item.get("ready")) for item in receipt["days"]),
            "days_total": len(DATES), "bars_csv_sha256": sha256(serialized)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--verify", action="store_true", help="verify raw hashes and reproduce bars.csv offline")
    args = parser.parse_args()
    result = verify(args.out, args.receipt) if args.verify else run_capture(args.out, args.receipt)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
