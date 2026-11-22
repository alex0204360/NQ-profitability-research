#!/usr/bin/env python3
"""Rebuild the exposed regular-hours MNQ one-minute panel.

Discovery bars are restored from the source GitHub commit recorded by
experiments/path_order/data.py. The three November windows are reissued from
the frozen Yahoo Chart API date bounds in experiments/path_order/capture.py;
those source files are not committed. Only audited regular-hours dates through
2026-11-20 are emitted. Requires authenticated `gh` and Python 3 standard lib.
"""
import base64
import csv
import hashlib
import json
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

REPO = "alex0204360/NQ-profitability-research"
DISCOVERY_REF = "8336fe8"
DISCOVERY_FILES = [f"data/mnq_oracle_2026/MNQ_Yahoo_1m_20260913_20261012_part{i:02d}.csv" for i in range(1, 7)]
DISCOVERY_HASHES = [
    "3430116d80a7e4e2b9e2b2ed34315dc5255d2433620b737c96055556312176f2",
    "a7a64421e57fa8142a7c07f4415c719981c7d6020d50c068749806a0aff3eb34",
    "514249caa15cc110b289c5c48b2c8afa44c1d602d2174e5b7c393bf67a4c4a4b",
    "a218f1228416cd191d38d1841e66a75b2eb677f87448f42b8f9a120388816933",
    "b2777b42a4ef96037c868e4664e9142aac8ecb010abf4e4e65d2b59b6a28bff6",
    "bcf54e4b620996c1f4c28cda92f442f473573e042319c9eb9e1e810dc15a1114",
]
WINDOWS = [
    (1793664000, 1794009600, "2026-11-03", "2026-11-06"),
    (1794182400, 1794614400, "2026-11-09", "2026-11-13"),
    (1794787200, 1795219200, "2026-11-16", "2026-11-20"),
]
SYMBOL = "MNQZ26.CME"
NY = ZoneInfo("America/New_York")
OUT = "/tmp/exposed.csv"
FIELDS = ["time", "open", "high", "low", "close", "volume"]


def gh_file(path):
    result = subprocess.run(["gh", "api", f"repos/{REPO}/contents/{path}?ref={DISCOVERY_REF}"], check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    return base64.b64decode(payload["content"])


def valid_bar(stamp, vals):
    local = stamp.astimezone(NY)
    if local.weekday() >= 5 or local.strftime("%H:%M") < "09:30" or local.strftime("%H:%M") > "15:59":
        return False
    if stamp.second != 0 or stamp.microsecond != 0:
        return False
    return True


def parse_csv_bytes(raw):
    rows = []
    for r in csv.DictReader(raw.decode("utf-8").splitlines()):
        stamp = datetime.fromisoformat(r.get("timestamp_utc") or r["time"]).astimezone(timezone.utc)
        vals = [float(r[k]) for k in ("open", "high", "low", "close", "volume")]
        if valid_bar(stamp, vals):
            rows.append((stamp, *vals))
    return rows


def yahoo_rows(start, end):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}?period1={start}&period2={end}&interval=1m&includePrePost=true"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=45) as response:
        raw = response.read()
    chart = json.loads(raw)["chart"]
    if chart.get("error") or not chart.get("result"):
        raise RuntimeError(f"Yahoo Chart error: {chart.get('error')}")
    item, = chart["result"]
    meta = item["meta"]
    if (meta.get("symbol") != SYMBOL or meta.get("instrumentType") != "FUTURE" or
            meta.get("dataGranularity") != "1m" or meta.get("exchangeTimezoneName") != "America/New_York"):
        raise RuntimeError(f"Unexpected Yahoo series metadata: {meta}")
    quotes, = item["indicators"]["quote"]
    rows = []
    for stamp, *vals in zip(item["timestamp"], *(quotes[k] for k in ("open", "high", "low", "close", "volume")), strict=True):
        if any(v is None for v in vals):
            continue
        t = datetime.fromtimestamp(stamp, timezone.utc)
        if valid_bar(t, vals):
            rows.append((t, *(float(v) for v in vals)))
    return rows, hashlib.sha256(raw).hexdigest()


def main():
    records, provenance = [], []
    for path, expected_hash in zip(DISCOVERY_FILES, DISCOVERY_HASHES, strict=True):
        raw = gh_file(path)
        actual_hash = hashlib.sha256(raw).hexdigest()
        if actual_hash != expected_hash:
            raise RuntimeError(f"Pinned discovery file hash mismatch for {path}: {actual_hash}")
        records.extend(parse_csv_bytes(raw))
        provenance.append({"source": f"gh:{DISCOVERY_REF}:{path}", "sha256": hashlib.sha256(raw).hexdigest()})
    for p1, p2, start, end in WINDOWS:
        rows, digest = yahoo_rows(p1, p2)
        records.extend(rows)
        provenance.append({"source": f"Yahoo Chart API {start}..{end}", "source_sha256": digest, "reissued": True})
    # Preserve canonical regular-hours date windows and validate exactly 390 bars per session.
    allowed = set()
    for lo, hi in [("2026-09-14", "2026-10-09"), ("2026-11-03", "2026-11-06"), ("2026-11-09", "2026-11-13"), ("2026-11-16", "2026-11-20")]:
        from datetime import date, timedelta
        d = date.fromisoformat(lo); stop = date.fromisoformat(hi)
        while d <= stop:
            if d.weekday() < 5: allowed.add(d.isoformat())
            d += timedelta(days=1)
    records = [r for r in records if r[0].astimezone(NY).date().isoformat() in allowed]
    records.sort(key=lambda r: r[0])
    if len({r[0] for r in records}) != len(records):
        raise RuntimeError("duplicate timestamps across restored windows")
    counts = {}
    for r in records:
        day = r[0].astimezone(NY).date().isoformat()
        counts[day] = counts.get(day, 0) + 1
    nov_days = {d for d in allowed if d.startswith("2026-11-")}
    bad = {d: counts.get(d, 0) for d in sorted(nov_days) if counts.get(d, 0) != 390}
    if bad or len(records) != 13256:
        raise RuntimeError(f"Unexpected canonical coverage: November sessions={bad}, total rows={len(records)} (expected 13256)")
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n"); w.writerow(FIELDS)
        for t, *vals in records:
            w.writerow([t.isoformat(), *vals])
    with open(OUT, "rb") as restored:
        if hashlib.sha256(restored.read()).hexdigest() != "5a670be6a46d7460f8a8946ead90aa20582ffea0e09d0554f46aadb9c7907083":
            raise RuntimeError("Restored regular-hours rows differ from the scored edition")
    print(json.dumps({"output": OUT, "rows": len(records), "sessions": len(counts), "sha256": hashlib.sha256(open(OUT,"rb").read()).hexdigest(), "provenance": provenance}, indent=2))

if __name__ == "__main__":
    main()
