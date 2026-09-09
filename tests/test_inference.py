"""Profit evidence tests use explicit synthetic trades, never market outcomes."""

from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from nqprofit.inference import (
    bootstrap_evidence,
    daily_arrays,
    holm,
    summarize_trades,
)


def trade(gross, bars=1, reason="tp", minute=0, **kwargs):
    entry = pd.Timestamp("2024-01-02T14:00:00Z") + pd.Timedelta(minutes=minute)
    result = {
        "entry_time": entry.isoformat(),
        "exit_time": (entry + pd.Timedelta(minutes=bars)).isoformat(),
        "exit_reason": reason,
        "gross_points": gross,
        "net_points": gross - 1,
        "resolution_bars": bars,
        "ambiguous": False,
        "policy_id": "example",
        "state": 0,
        "action_id": "long_tp1_sl1_h45",
    }
    result.update(kwargs)
    return result


def daily(pnl, count=None, start="2024-01-01"):
    pnl = np.asarray(pnl, dtype=float)
    return pd.DataFrame(
        {
            "day": pd.date_range(start, periods=len(pnl), freq="D").strftime("%Y-%m-%d"),
            "pnl": pnl,
            "count": np.ones(len(pnl), dtype=int) if count is None else count,
        }
    )


def test_summary_accounts_for_costs_censoring_drawdown_and_resolution():
    records = [
        trade(5),
        trade(-2, 3, "sl", 5, ambiguous=True),
        trade(1, 45, "timeout", 10),
        trade(4, 10, "tp", 60),
        trade(-5, 2, "sl", 75),
        trade(100, 4, "censored", 80),
    ]
    summary = summarize_trades(list(reversed(records)))
    assert summary["n"] == summary["priced_trades"] == 5
    assert summary["attempted_trades"] == 6
    assert summary["censored_trades"] == 1
    assert summary["coverage"] == pytest.approx(5 / 6)
    assert summary["dates"] == summary["weeks"] == 1
    assert summary["exit_counts"] == {"tp": 2, "sl": 2, "timeout": 1, "censored": 1}
    assert summary["ambiguous_trades"] == 1
    assert summary["hit_rate"] == summary["tp_rate"] == 0.4
    assert summary["hit_rate_ci95"] == pytest.approx([0.1176207742, 0.7692757187])
    assert summary["mean_net_points"] == pytest.approx(-0.4)
    assert summary["total_net_points"] == -2
    assert summary["total_gross_points"] == 3
    assert summary["profit_factor"] == pytest.approx(7 / 9)
    assert summary["max_drawdown_points"] == 6
    assert summary["cost_scenarios"]["nq_primary"]["total_dollars"] == -40
    assert summary["cost_scenarios"]["nq_stress"]["mean_points"] == pytest.approx(-1.4)
    assert summary["cost_scenarios"]["mnq_proxy_primary"]["mean_points"] == pytest.approx(-0.9)
    assert summary["cost_scenarios"]["mnq_proxy_stress"]["total_dollars"] == -19
    resolution = summary["resolution"]["overall"]
    assert resolution["mean"] == pytest.approx(12.2)
    assert resolution["median"] == 3
    assert resolution["p10"] == pytest.approx(1.4)
    assert resolution["max"] == 45
    assert resolution["histogram"] == {"1": 1, "2": 1, "3": 1, "10": 1, "45": 1}
    assert summary["resolution"]["timeout"]["mean"] == 45
    assert summary["state_breakdown"]["0"]["low_confidence"] is True
    assert summary["action_breakdown"]["long_tp1_sl1_h45"]["n"] == 5


def test_drawdown_includes_zero_start_and_uses_exit_order():
    summary = summarize_trades([trade(5, minute=10), trade(-2, minute=0)])
    assert summary["max_drawdown_points"] == 3
    assert summarize_trades([trade(4)])["profit_factor"] is None
    assert summarize_trades([trade(4)])["loss_free"] is True


def test_empty_and_only_censored_summary_have_no_invented_rates():
    for records in ([], [trade(0, reason="censored", exit_time=None)]):
        summary = summarize_trades(records)
        assert summary["n"] == 0
        assert summary["mean_net_points"] is None
        assert summary["hit_rate"] is None
        assert summary["hit_rate_ci95"] is None
        assert summary["profit_factor"] is None
        assert summary["resolution"]["overall"]["mean"] is None
        assert summary["resolution"]["overall"]["histogram"] == {}
        assert summary["total_net_points"] == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"entry_time": "2024-01-01T10:00:00"},
        {"net_points": np.nan},
        {"resolution_bars": 46},
        {"resolution_bars": 0},
        {"exit_reason": "guaranteed_win"},
        {"exit_time": "2024-01-02T13:59:00Z"},
    ],
)
def test_invalid_priced_trades_are_not_silently_omitted(changes):
    with pytest.raises(ValueError):
        summarize_trades([trade(4, **changes)])


def test_calendar_days_include_weekends_and_dst_and_book_entry_day():
    records = [
        trade(
            3,
            entry_time="2024-03-09T23:50:00-05:00",
            exit_time="2024-03-10T00:10:00-05:00",
            resolution_bars=20,
        ),
        trade(
            -1,
            entry_time="2024-03-11T23:59:00-04:00",
            exit_time="2024-03-12T00:00:00-04:00",
        ),
        trade(7, reason="censored", entry_time="2024-03-10T10:00:00-04:00"),
    ]
    frame = daily_arrays(records, "2024-03-09T00:00:00-05:00", "2024-03-12T00:00:00-04:00")
    assert frame["day"].tolist() == ["2024-03-09", "2024-03-10", "2024-03-11"]
    assert frame["pnl"].tolist() == [2, 0, -2]
    assert frame["count"].tolist() == [1, 0, 1]
    assert summarize_trades(records)["weeks"] == 2


def test_daily_arrays_fail_if_trade_entry_is_outside_period_or_bounds_not_midnight():
    with pytest.raises(ValueError, match="period"):
        daily_arrays([trade(3)], "2024-01-03", "2024-01-04")
    with pytest.raises(ValueError, match="midnight"):
        daily_arrays([], "2024-01-02T01:00:00-05:00", "2024-01-03")
    with pytest.raises(ValueError):
        daily_arrays([], "2024-01-03", "2024-01-02")


def test_bootstrap_constant_profit_has_positive_mean_but_identical_pair_fails():
    policy = daily(np.repeat(2.0, 80))
    evidence = bootstrap_evidence([(policy, policy.copy())], draws=999, seed=13)
    assert evidence["observed_mean_net_per_trade"] == 2
    assert evidence["observed_mean_daily_advantage"] == 0
    assert evidence["lower_bounds_positive"] is False
    assert evidence["p_value"] == 1
    for result in evidence["block_results"]:
        assert result["mean_net_per_trade_ci95"] == [2, 2]
        assert result["daily_advantage_ci95"] == [0, 0]
        assert result["mean_net_per_trade_p_value"] == 0.001
        assert result["daily_advantage_p_value"] == 1


def test_bootstrap_joint_counts_ratio_and_paired_difference():
    counts = np.tile([0, 1, 3, 0, 2], 30)
    policy = daily(2 * counts, counts)
    baseline = daily(counts, counts)
    evidence = bootstrap_evidence([(policy, baseline)], draws=1999, seed=7)
    assert evidence["observed_mean_net_per_trade"] == 2
    assert evidence["observed_mean_daily_advantage"] == pytest.approx(np.mean(counts))
    assert evidence["lower_bounds_positive"] is True
    for result in evidence["block_results"]:
        assert result["mean_net_per_trade_ci95"] == [2, 2]
    assert evidence["p_value"] == pytest.approx(1 / 2000)
    assert evidence == bootstrap_evidence([(policy, baseline)], draws=1999, seed=7)


def test_bootstrap_preserves_fold_weights_and_does_not_mix_period_boundaries():
    first = daily([10] * 7)
    second = daily([-1] * 13, start="2024-02-01")
    periods = [(first, daily([0] * 7, [0] * 7)), (second, daily([0] * 13, [0] * 13, "2024-02-01"))]
    evidence = bootstrap_evidence(periods, draws=199, seed=3)
    assert evidence["observed_mean_net_per_trade"] == pytest.approx(57 / 20)
    for result in evidence["block_results"]:
        assert result["mean_net_per_trade_ci95"] == pytest.approx([2.85, 2.85])


def test_longer_blocks_capture_serial_dependence():
    values = np.repeat([5, -3, 5, -3, 5, -3, 5, -3, 5, -3], 20)
    policy = daily(values)
    baseline = daily(np.zeros(len(values)), np.zeros(len(values)))
    result = bootstrap_evidence([(policy, baseline)], draws=2999, seed=17)
    widths = [np.diff(block["mean_net_per_trade_ci95"])[0] for block in result["block_results"]]
    assert widths[1] > 1.25 * widths[0]


@pytest.mark.parametrize("pnl,count", [([-2] * 40, [1] * 40), ([0] * 40, [0] * 40)])
def test_nonpositive_or_no_trades_cannot_pass(pnl, count):
    policy = daily(pnl, count)
    baseline = daily([0] * 40, [0] * 40)
    evidence = bootstrap_evidence([(policy, baseline)], draws=99)
    assert evidence["p_value"] == 1
    assert evidence["lower_bounds_positive"] is False


def test_zero_count_resamples_are_explicit_and_non_supporting():
    counts = np.zeros(100, dtype=int)
    counts[0] = 1
    policy = daily(100 * counts, counts)
    evidence = bootstrap_evidence([(policy, daily([0] * 100, [0] * 100))], draws=999, seed=8)
    assert all(b["zero_count_resamples"] > 0 for b in evidence["block_results"])
    assert evidence["lower_bounds_positive"] is False
    assert evidence["p_value"] > 0.05


def test_bootstrap_does_not_mutate_inputs():
    policy = daily([1, 2, 3] * 20)
    before = deepcopy(policy)
    bootstrap_evidence([(policy, daily([0] * 60, [0] * 60))], draws=49)
    pd.testing.assert_frame_equal(policy, before)


@pytest.mark.parametrize("failure", ["missing_day", "unpaired", "nan", "negative_count", "cash_without_trade", "overlap"])
def test_malformed_bootstrap_periods_rejected(failure):
    policy = daily([1.0] * 25)
    baseline = daily([0.0] * 25, [0] * 25)
    periods = [(policy, baseline)]
    if failure == "missing_day":
        policy.drop(index=10, inplace=True)
        baseline.drop(index=10, inplace=True)
    elif failure == "unpaired":
        baseline.loc[0, "day"] = "2023-12-31"
    elif failure == "nan":
        policy.loc[0, "pnl"] = np.nan
    elif failure == "negative_count":
        policy.loc[0, "count"] = -1
    elif failure == "cash_without_trade":
        policy.loc[0, "count"] = 0
    else:
        periods.append((policy.copy(), baseline.copy()))
    with pytest.raises(ValueError):
        bootstrap_evidence(periods, draws=9)


@pytest.mark.parametrize("kwargs", [{"draws": 0}, {"draws": 2.5}, {"draws": 9, "block_lengths": ()}, {"draws": 9, "block_lengths": (0,)}])
def test_invalid_bootstrap_configuration_rejected(kwargs):
    frame = daily([1] * 10)
    with pytest.raises(ValueError):
        bootstrap_evidence([(frame, frame)], **kwargs)


def test_holm_accounts_for_failures_in_frozen_family_and_is_order_independent():
    result = holm({"c": 0.03, "a": 0.001, "failure": 1, "b": 0.015})
    assert result == {
        "a": {"adjusted_p": 0.004, "passed": True},
        "b": {"adjusted_p": 0.045, "passed": True},
        "c": {"adjusted_p": 0.06, "passed": False},
        "failure": {"adjusted_p": 1.0, "passed": False},
    }
    assert holm({}) == {}
    assert holm({"a": 0.03, "b": 0.025})["a"]["adjusted_p"] == 0.05


@pytest.mark.parametrize("p", [-0.1, 1.1, np.nan])
def test_invalid_p_value_is_not_silently_accepted(p):
    with pytest.raises(ValueError):
        holm({"invalid": p})
