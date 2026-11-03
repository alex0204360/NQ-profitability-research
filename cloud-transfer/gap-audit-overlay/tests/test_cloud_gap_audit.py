from tools.cloud_gap_audit import summarize


def test_gap_profit_is_reported_separately_without_claiming_a_filter():
    trades = [
        {"net": 100.0, "reason": "unresolved_gap_next_observed_open",
         "signal_time": "a", "entry_time": "b", "exit_time": "c"},
        {"net": -20.0, "reason": "time_limit"},
    ]
    row = summarize(trades)
    assert row["reported_net_usd"] == 80
    assert row["gap_trade_net_usd"] == 100
    assert row["net_excluding_gap_trades_usd"] == -20
    assert row["gap_trades"] == 1
