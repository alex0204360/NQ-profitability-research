"""Non-live, one-session quote re-pricing for a frozen next-open ledger."""
from __future__ import annotations

from math import isfinite

import numpy as np
import pandas as pd

FEE_USD = 2.0
POINT_VALUE_USD = 2.0  # MNQ
TICK = 0.25
MAX_QUOTE_AGE = pd.Timedelta(seconds=1)
QUOTE_COLUMNS = {"timestamp_utc", "bid", "ask", "contract"}
TRADE_COLUMNS = {"entry_time", "exit_time", "side", "entry", "exit", "reason"}


def audit(trades: pd.DataFrame, quotes: pd.DataFrame, contract: str,
          latency_seconds: float = 9):
    """Reprice an immutable execution.replay ledger against one-day quotes.

    Returns ``(trade_audit, summary)``. Missing/stale quote matches remain rows
    with ``status='unmatched'`` and NaN P&L; summary totals use matched trades
    only and explicitly expose coverage. ``reason == 'gap'`` is unpriced.
    The ``time`` exit assumes a pre-scheduled order arrives at the 15:55
    deadline exactly (latency is not added to that exit).
    """
    if not isinstance(trades, pd.DataFrame) or not isinstance(quotes, pd.DataFrame):
        raise TypeError("trades and quotes must be DataFrames")
    if not isinstance(contract, str) or not contract.strip():
        raise ValueError("contract must be a nonempty string")
    if isinstance(latency_seconds, (bool, np.bool_)):
        raise ValueError("latency_seconds must be finite and in [0, 10)")
    latency_seconds = float(latency_seconds)
    if not isfinite(latency_seconds) or not 0 <= latency_seconds < 10:
        raise ValueError("latency_seconds must be finite and in [0, 10)")
    if not TRADE_COLUMNS.issubset(trades.columns):
        raise ValueError(f"trades missing columns: {sorted(TRADE_COLUMNS - set(trades.columns))}")
    if not QUOTE_COLUMNS.issubset(quotes.columns):
        raise ValueError(f"quotes missing columns: {sorted(QUOTE_COLUMNS - set(quotes.columns))}")

    q = quotes.copy()
    if q["contract"].isna().any() or not q["contract"].eq(contract).all():
        raise ValueError("quotes must all belong to the requested contract")
    try:
        # utc=True handles ISO-8601 strings with mixed fractional precision and
        # offsets. Naive inputs are rejected below by checking source awareness.
        raw_times = q["timestamp_utc"]
        parsed = pd.to_datetime(raw_times, errors="raise", utc=True, format="mixed")
        qtimes = pd.DatetimeIndex(parsed)
    except Exception as exc:
        raise ValueError("quote timestamps must be valid timezone-aware UTC timestamps") from exc
    if any(pd.isna(v) or pd.Timestamp(v).tzinfo is None for v in raw_times):
        raise ValueError("quote timestamps must be timezone-aware UTC timestamps")
    qtimes = qtimes.tz_convert("UTC")
    if qtimes.has_duplicates or not qtimes.is_monotonic_increasing:
        raise ValueError("quotes must be sorted by timestamp with no duplicates")
    q["_time"] = qtimes
    bid = pd.to_numeric(q["bid"], errors="coerce").to_numpy(dtype=float)
    ask = pd.to_numeric(q["ask"], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(bid).all() or not np.isfinite(ask).all() or (bid <= 0).any() or (ask <= 0).any():
        raise ValueError("quote prices must be finite and positive")
    if (bid > ask).any():
        raise ValueError("crossed quotes are invalid")
    if not np.isclose(bid / TICK, np.round(bid / TICK), atol=1e-8, rtol=0).all() or not np.isclose(ask / TICK, np.round(ask / TICK), atol=1e-8, rtol=0).all():
        raise ValueError("quote prices must lie on the MNQ 0.25 tick grid")
    q["_bid"], q["_ask"] = bid, ask

    t = trades.copy().reset_index(drop=True)
    for col in ("entry_time", "exit_time"):
        try:
            idx = pd.DatetimeIndex(pd.to_datetime(t[col], errors="raise"))
        except Exception as exc:
            raise ValueError(f"{col} must contain valid timezone-aware timestamps") from exc
        if len(idx) and idx.tz is None:
            raise ValueError(f"{col} must be timezone-aware")
        t[col] = idx.tz_convert("UTC") if len(idx) else pd.DatetimeIndex([], tz="UTC")
    if not t["side"].isin(["long", "short"]).all():
        raise ValueError("side must be long or short")
    if not t["reason"].isin(["signal", "daily loss", "time", "gap"]).all():
        raise ValueError("unsupported exit reason")
    if len(t):
        ny_dates = set(t["entry_time"].dt.tz_convert("America/New_York").dt.date) | set(t["exit_time"].dt.tz_convert("America/New_York").dt.date)
        if len(ny_dates) != 1:
            raise ValueError("trade ledger must cover one New York session date")
        if len(q):
            quote_dates = set(q["_time"].dt.tz_convert("America/New_York").dt.date)
            if not quote_dates.issubset(ny_dates):
                raise ValueError("quotes must belong to the ledger's New York session date")

    times = q["_time"].array.as_unit("ns").asi8
    def match(arrival):
        if pd.isna(arrival) or not len(times):
            return None
        ns = arrival.value
        i = int(np.searchsorted(times, ns, side="right") - 1)
        if i < 0 or ns - times[i] > MAX_QUOTE_AGE.value:
            return None
        return float(bid[i]), float(ask[i]), q["_time"].iloc[i]

    rows = []
    latency = pd.Timedelta(seconds=latency_seconds)
    for _, tr in t.iterrows():
        entry_arrival = tr.entry_time + latency
        scheduled = tr.reason == "time"
        exit_arrival = tr.exit_time if scheduled else tr.exit_time + latency
        em = match(entry_arrival)
        xm = None if tr.reason == "gap" else match(exit_arrival)
        status = "matched" if em is not None and xm is not None else "unmatched"
        out = {"entry_arrival_utc": entry_arrival, "exit_arrival_utc": exit_arrival,
               "entry_quote_time_utc": pd.NaT if em is None else em[2],
               "exit_quote_time_utc": pd.NaT if xm is None else xm[2],
               "status": status, "exit_timing_assumption": "pre-scheduled arrival at 15:55 deadline" if scheduled else ("gap exit unpriced" if tr.reason == "gap" else "signal exit plus latency")}
        for suffix, m in (("entry", em), ("exit", xm)):
            out[f"{suffix}_quote_bid"] = np.nan if m is None else m[0]
            out[f"{suffix}_quote_ask"] = np.nan if m is None else m[1]
        if status == "matched":
            long = tr.side == "long"
            # Marketable quote-side fills; sensitivity adds one adverse tick at each leg.
            entry_px = em[1] if long else em[0]
            exit_px = xm[0] if long else xm[1]
            side = 1 if long else -1
            out["base_entry_fill"] = entry_px
            out["base_exit_fill"] = exit_px
            out["base_net_usd"] = side * (exit_px - entry_px) * POINT_VALUE_USD - FEE_USD
            out["one_tick_entry_fill"] = entry_px + TICK if long else entry_px - TICK
            out["one_tick_exit_fill"] = exit_px - TICK if long else exit_px + TICK
            out["one_tick_net_usd"] = side * (out["one_tick_exit_fill"] - out["one_tick_entry_fill"]) * POINT_VALUE_USD - FEE_USD
        else:
            for key in ("base_entry_fill", "base_exit_fill", "base_net_usd", "one_tick_entry_fill", "one_tick_exit_fill", "one_tick_net_usd"):
                out[key] = np.nan
        rows.append(out)
    result = pd.concat([t, pd.DataFrame(rows)], axis=1) if rows else t.assign(
        entry_arrival_utc=pd.Series(dtype="datetime64[ns, UTC]"), exit_arrival_utc=pd.Series(dtype="datetime64[ns, UTC]"),
        entry_quote_time_utc=pd.Series(dtype="datetime64[ns, UTC]"), exit_quote_time_utc=pd.Series(dtype="datetime64[ns, UTC]"),
        status=pd.Series(dtype="object"), exit_timing_assumption=pd.Series(dtype="object"))
    matched = result[result["status"] == "matched"]
    summary = {"contract": contract, "trade_count": len(result), "matched_count": len(matched),
               "unmatched_count": len(result) - len(matched), "coverage_complete": len(result) == len(matched),
               "base_net_usd_matched": float(matched["base_net_usd"].sum()) if len(matched) else (0.0 if len(result) == 0 else np.nan),
               "one_tick_net_usd_matched": float(matched["one_tick_net_usd"].sum()) if len(matched) else (0.0 if len(result) == 0 else np.nan)}
    return result, summary
