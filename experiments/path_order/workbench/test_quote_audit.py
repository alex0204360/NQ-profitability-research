import pandas as pd
import pytest

from quote_audit import audit


CONTRACT = "MNQZ26"
BASE = pd.Timestamp("2026-11-03 15:00:00", tz="UTC")


def ledger(side="long", reason="signal"):
    return pd.DataFrame([{"signal_time": BASE - pd.Timedelta(minutes=1),
                          "entry_time": BASE, "exit_time": BASE + pd.Timedelta(seconds=10),
                          "side": side, "entry": 100.0, "exit": 101.0,
                          "gross_usd": 2.0, "net_usd": -1.0, "reason": reason}])


def qdf(times=None, bids=None, asks=None):
    times = times or [BASE + pd.Timedelta(seconds=i) for i in range(21)]
    bids = bids or [100.0 + (i // 10) * 1 for i in range(len(times))]
    asks = asks or [b + 0.5 for b in bids]
    return pd.DataFrame({"timestamp_utc": times, "bid": bids, "ask": asks, "contract": CONTRACT})


def test_long_short_quote_sides_fees_and_tick_sensitivity():
    trades, summary = audit(ledger(), qdf(), CONTRACT)
    row = trades.iloc[0]
    assert row.status == "matched"
    assert row.base_entry_fill == 100.5
    assert row.base_exit_fill == 101.0
    assert row.base_net_usd == pytest.approx(-1.0)
    assert row.one_tick_net_usd == pytest.approx(-2.0)
    assert summary["coverage_complete"]
    short, _ = audit(ledger(side="short"), qdf(), CONTRACT)
    assert short.iloc[0].base_entry_fill == 100.0
    assert short.iloc[0].base_exit_fill == 101.5


def test_no_lookahead_and_stale_quote_unmatched():
    # At arrival :09, only the :08 quote is eligible; :10 is future data.
    quotes = qdf(times=[BASE + pd.Timedelta(seconds=8), BASE + pd.Timedelta(seconds=10)],
                 bids=[100, 110], asks=[100.5, 110.5])
    out, _ = audit(ledger(), quotes, CONTRACT)
    assert out.iloc[0].entry_quote_time_utc == BASE + pd.Timedelta(seconds=8)
    # Exit arrival :19 has no quote at or before it within one second.
    assert out.iloc[0].status == "unmatched"
    assert pd.isna(out.iloc[0].base_net_usd)


def test_time_exit_is_scheduled_at_cutoff_and_gap_is_unpriced():
    t = ledger(reason="time")
    t.loc[0, "entry_time"] = pd.Timestamp("2026-11-03 20:54:40", tz="UTC")
    t.loc[0, "exit_time"] = pd.Timestamp("2026-11-03 20:55:00", tz="UTC")
    quotes = qdf(times=[pd.Timestamp("2026-11-03 20:54:49", tz="UTC"), pd.Timestamp("2026-11-03 20:55:00", tz="UTC")],
                 bids=[100, 101], asks=[100.5, 101.5])
    out, _ = audit(t, quotes, CONTRACT, latency_seconds=9)
    assert out.iloc[0].exit_arrival_utc == t.iloc[0].exit_time
    gap, summary = audit(ledger(reason="gap"), qdf(), CONTRACT)
    assert gap.iloc[0].status == "unmatched"
    assert summary["base_net_usd_matched"] != summary["base_net_usd_matched"]


def test_empty_ledger_is_complete_zero_aggregate():
    empty = ledger().iloc[:0]
    out, summary = audit(empty, qdf(), CONTRACT)
    assert out.empty
    assert summary["coverage_complete"]
    assert summary["base_net_usd_matched"] == 0


@pytest.mark.parametrize("mutator", [
    lambda q: q.iloc[::-1].reset_index(drop=True),
    lambda q: pd.concat([q, q.iloc[[0]]], ignore_index=True),
    lambda q: q.assign(ask=q["bid"] - 0.25),
    lambda q: q.assign(bid=q["bid"] + 0.1),
    lambda q: q.assign(contract="OTHER"),
])
def test_rejects_invalid_quote_tape(mutator):
    with pytest.raises(ValueError):
        audit(ledger(), mutator(qdf()), CONTRACT)


def test_latency_contract_and_timezone_validation():
    with pytest.raises(ValueError):
        audit(ledger(), qdf(), CONTRACT, latency_seconds=10)
    with pytest.raises(ValueError):
        audit(ledger(), qdf().assign(timestamp_utc=lambda q: q.timestamp_utc.dt.tz_localize(None)), CONTRACT)
    with pytest.raises(ValueError):
        audit(ledger(), qdf(), contract="OTHER")


def test_rejects_off_grid_price_at_high_nominal_level():
    quotes = qdf().assign(bid=lambda q: q.bid + 0.1)
    with pytest.raises(ValueError, match="tick grid"):
        audit(ledger(), quotes, CONTRACT)


def test_mixed_fractional_iso_timestamps_and_empty_quote_tape():
    quotes = qdf(times=["2026-11-03T15:00:08Z", "2026-11-03T15:00:10.123456789Z"],
                 bids=[100, 110], asks=[100.5, 110.5])
    out, _ = audit(ledger(), quotes, CONTRACT)
    assert out.iloc[0].entry_quote_time_utc == BASE + pd.Timedelta(seconds=8)

    empty = qdf().iloc[:0]
    out, summary = audit(ledger(), empty, CONTRACT)
    assert out.iloc[0].status == "unmatched"
    assert summary["unmatched_count"] == 1
    assert pd.isna(summary["base_net_usd_matched"])


def test_daily_loss_exit_uses_signal_latency():
    t = ledger()
    t["reason"] = "daily loss"
    out, _ = audit(t, qdf(), CONTRACT)
    expected = pd.to_datetime(t.exit_time, utc=True) + pd.Timedelta(seconds=9)
    assert list(out.exit_arrival_utc) == list(expected)
