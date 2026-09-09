"""Public feed-agnostic matcher contract; synthetic bars are not financial evidence."""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
import pytest

import nqprofit.matcher as matcher_module
from nqprofit.matcher import PolicyMatcher


def bars(count=61, start="2024-01-02 12:04:00+00:00"):
    prices = 16000.0 + np.arange(count) * 0.25
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(start, periods=count, freq="min"),
            "open": prices,
            "high": prices + 1.0,
            "low": prices - 1.0,
            "close": prices + 0.25,
            "volume": np.arange(count) + 20.0,
        }
    )


@pytest.fixture
def library(tmp_path, monkeypatch):
    """Stub learned policies so these tests isolate causal serving and routing."""
    (tmp_path / "patterns").mkdir()
    (tmp_path / "models").mkdir()
    model = {
        "policy_id": "synthetic_policy",
        "n_states": 1,
        "fixture_actions": [
            {
                "action_id": "long_h45",
                "action_index": 0,
                "direction": 1,
                "tp_atr": 2.0,
                "sl_atr": 1.0,
                "horizon": 45,
                "predicted_net_points": 2.5,
                "ranking_score": 2.0,
            },
            {
                "action_id": "short_h1",
                "action_index": 1,
                "direction": -1,
                "tp_atr": 0.5,
                "sl_atr": 0.5,
                "horizon": 1,
                "predicted_net_points": 0.7,
                "ranking_score": 0.2,
            },
        ]
    }
    (tmp_path / "models" / "fixture.json").write_text(json.dumps(model))
    encoder_fixture = {"fixture": True, "family": "synthetic_policy", "n_states": 1}
    (tmp_path / "models" / "encoder.json").write_text(json.dumps(encoder_fixture))
    payload = {"schema_version": 2, "qualified_policies": [], "diagnostic_policies": []}
    path = tmp_path / "patterns" / "library.json"

    def write(*, qualified=False, diagnostic=False):
        entry = {
            "policy_id": "synthetic_policy",
            "model_path": "models/fixture.json",
            "encoder_path": "models/encoder.json",
            "model_sha256": hashlib.sha256((tmp_path / "models/fixture.json").read_bytes()).hexdigest(),
            "encoder_sha256": hashlib.sha256((tmp_path / "models/encoder.json").read_bytes()).hexdigest(),
            "stats": {"n": 41, "mean_net_points": 0.6, "fixture": True},
            "qualified": qualified,
            "status": "historically_qualified" if qualified else "diagnostic_unqualified",
        }
        payload["qualified_policies"] = [entry] if qualified else []
        payload["diagnostic_policies"] = [entry] if diagnostic else []
        path.write_text(json.dumps(payload))
        return path

    def encode(features, timestamps, encoder):
        assert features["valid"].all()
        assert encoder == encoder_fixture
        assert pd.DatetimeIndex(timestamps).tz is not None
        return np.zeros(len(features), dtype=int)

    def select(model, state, max_horizon=45):
        assert state == 0
        return next((a for a in model["fixture_actions"] if a["horizon"] <= max_horizon), None)

    monkeypatch.setattr(matcher_module, "encode_states", encode)
    monkeypatch.setattr(matcher_module, "select_action", select)
    return write, payload, path


def test_empty_library_abstains_and_requires_explicit_diagnostic_mode(library):
    write, _, _ = library
    path = write(diagnostic=True)
    assert PolicyMatcher(path).match(bars()) == []
    result = PolicyMatcher(path, diagnostic=True).match(bars())
    assert len(result) == 1
    assert result[0]["qualified"] is False
    assert result[0]["status"] == "diagnostic_unqualified"


def test_recommendation_offsets_forecasts_and_historical_stats(library):
    write, _, _ = library
    result = PolicyMatcher(write(qualified=True)).match(bars())[0]
    assert result["policy_id"] == "synthetic_policy"
    assert result["direction"] == "long"
    assert result["tp_points"] == 4.0
    assert result["sl_points"] == 2.0
    assert result["horizon"] == 45
    assert result["predicted_net_points"] == 2.5
    assert result["ranking_score"] == 2.0
    assert result["historical_stats"]["n"] == 41
    assert pd.Timestamp(result["decision_time"]) == pd.Timestamp("2024-01-02 13:05Z")
    assert result["intended_entry_time"] == result["decision_time"]
    assert len(result["model_provenance"]["model_sha256"]) == 64
    assert len(result["model_provenance"]["encoder_sha256"]) == 64
    assert "entry_price" not in result
    assert "take_profit_price" not in result


def test_no_trade_when_occupied_or_off_clock_or_warmup(library):
    write, _, _ = library
    matcher = PolicyMatcher(write(qualified=True))
    assert matcher.match(bars(), flat=False) == []
    assert matcher.match(bars(62)) == []
    assert matcher.match(bars(60)) == []
    assert matcher.match(bars(0)) == []


def test_known_close_filters_actions_before_selection(library):
    write, _, _ = library
    matcher = PolicyMatcher(write(qualified=True))
    result = matcher.match(bars(), known_close="2024-01-02T13:06:30Z")[0]
    assert result["direction"] == "short"
    assert result["horizon"] == 1
    assert result["tp_points"] == 1.0
    assert matcher.match(bars(), known_close="2024-01-02T13:05:59Z") == []
    assert matcher.match(bars(), known_close="2024-01-02T13:00:00Z") == []
    with pytest.raises(ValueError, match="timezone|aware"):
        matcher.match(bars(), known_close="2024-01-02T14:00:00")


def test_encoder_receives_completed_bar_time_and_latest_features(library, monkeypatch):
    write, _, _ = library
    calls = []

    def record(features, timestamps, encoder):
        calls.append((features.copy(), pd.DatetimeIndex(timestamps)))
        return np.zeros(len(features), dtype=int)

    monkeypatch.setattr(matcher_module, "encode_states", record)
    PolicyMatcher(write(qualified=True)).match(bars())
    assert len(calls) == 1
    assert len(calls[0][0]) == 1
    assert calls[0][1][0] == pd.Timestamp("2024-01-02 13:05Z")


@pytest.mark.parametrize("column", ["contract", "segment_id"])
def test_identifier_change_restarts_warmup(library, column):
    write, _, _ = library
    sample = bars()
    sample[column] = "a"
    sample.loc[60, column] = "b"
    assert PolicyMatcher(write(qualified=True)).match(sample) == []


def test_gap_restarts_warmup_without_rejecting_valid_bar_input(library):
    write, _, _ = library
    sample = bars(66).drop(index=50)
    assert PolicyMatcher(write(qualified=True)).match(sample) == []


def test_stream_matches_batch_prefixes_and_recovers_after_gap(library):
    write, _, _ = library
    path = write(qualified=True)
    stream = PolicyMatcher(path)
    batch = PolicyMatcher(path)
    sample = bars(141).drop(index=65).reset_index(drop=True)
    for i, row in sample.iterrows():
        assert stream.update(row.to_dict()) == batch.match(sample.iloc[: i + 1])
    assert stream.match(sample) != []


def test_stream_rejects_repeated_bar_without_poisoning_buffer(library):
    write, _, _ = library
    matcher = PolicyMatcher(write(qualified=True))
    sample = bars(66)
    for _, row in sample.iloc[:61].iterrows():
        matcher.update(row.to_dict())
    with pytest.raises(ValueError, match="increasing|duplicate|order"):
        matcher.update(sample.iloc[60].to_dict())
    for _, row in sample.iloc[61:].iterrows():
        result = matcher.update(row.to_dict())
    assert len(result) == 1


@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda df: df.drop(columns="volume"), "column"),
        (lambda df: df.assign(timestamp=df.timestamp.dt.tz_localize(None)), "aware"),
        (lambda df: df.assign(timestamp=df.timestamp + pd.Timedelta(seconds=1)), "minute"),
        (lambda df: pd.concat([df, df.iloc[-1:]], ignore_index=True), "increasing|duplicate"),
        (lambda df: df.iloc[::-1], "increasing"),
        (lambda df: df.assign(open=np.nan), "finite"),
        (lambda df: df.assign(close=-1), "positive"),
        (lambda df: df.assign(volume=-1), "nonnegative"),
        (lambda df: df.assign(high=df.low - 1), "geometry|OHLC"),
        (lambda df: df.assign(open=df.open + 0.01), "tick"),
    ],
)
def test_invalid_ohlcv_is_rejected(library, mutation, message):
    write, _, _ = library
    with pytest.raises(ValueError, match=message):
        PolicyMatcher(write(qualified=True)).match(mutation(bars()))


def test_aware_other_timezone_and_nonunique_row_index_are_equivalent(library):
    write, _, _ = library
    matcher = PolicyMatcher(write(qualified=True))
    sample = bars()
    expected = matcher.match(sample)
    sample["timestamp"] = sample.timestamp.dt.tz_convert("America/New_York")
    sample.index = [7] * len(sample)
    assert matcher.match(sample) == expected


@pytest.mark.parametrize("bad_path", ["../outside.json", "/tmp/outside.json"])
def test_model_path_cannot_escape_project(library, bad_path):
    write, payload, path = library
    write(qualified=True)
    payload["qualified_policies"][0]["model_path"] = bad_path
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="path|project|relative"):
        PolicyMatcher(path)


def test_symlink_escape_is_rejected(library, tmp_path):
    write, payload, path = library
    write(qualified=True)
    outside = tmp_path.parent / f"{tmp_path.name}-outside.json"
    outside.write_text("{}")
    link = tmp_path / "models" / "outside.json"
    link.symlink_to(outside)
    payload["qualified_policies"][0]["encoder_path"] = "models/outside.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="path|project|relative"):
        PolicyMatcher(path)


@pytest.mark.parametrize("version", [1, 3, None])
def test_unknown_library_schema_is_rejected(library, version):
    write, payload, path = library
    write()
    payload["schema_version"] = version
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="schema"):
        PolicyMatcher(path)


def test_diagnostic_entry_cannot_claim_qualification(library):
    write, payload, path = library
    write(diagnostic=True)
    payload["diagnostic_policies"][0]["qualified"] = True
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="qualified|qualification"):
        PolicyMatcher(path, diagnostic=True)


def test_duplicate_policy_ids_are_rejected(library):
    write, payload, path = library
    write(qualified=True)
    payload["qualified_policies"] *= 2
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="duplicate"):
        PolicyMatcher(path)


def test_selected_action_may_abstain(library, monkeypatch):
    write, _, _ = library
    monkeypatch.setattr(matcher_module, "select_action", lambda *args, **kwargs: None)
    assert PolicyMatcher(write(qualified=True)).match(bars()) == []


@pytest.mark.parametrize("horizon", [0, 46, 1.5])
def test_matcher_never_emits_an_invalid_holding_cap(library, monkeypatch, horizon):
    write, _, _ = library
    monkeypatch.setattr(
        matcher_module,
        "select_action",
        lambda *args, **kwargs: {"horizon": horizon, "direction": 1},
    )
    with pytest.raises(ValueError, match="horizon|holding|scope"):
        PolicyMatcher(write(qualified=True)).match(bars())


def test_returned_stats_do_not_mutate_future_matches(library):
    write, _, _ = library
    matcher = PolicyMatcher(write(qualified=True))
    result = matcher.match(bars())[0]
    result["historical_stats"]["n"] = -1
    assert matcher.match(bars())[0]["historical_stats"]["n"] == 41


def test_real_policy_serving_uses_frozen_encoder_and_feasible_action(tmp_path):
    (tmp_path / "patterns").mkdir()
    (tmp_path / "models").mkdir()
    table = {
        "supported": True,
        "sample_size": 300,
        "date_count": 25,
        "predicted_net_points": [2.0, 1.0],
        "ranking_scores": [1.5, 0.5],
    }
    model = {
        "policy_id": "regime8",
        "n_states": 8,
        "actions": [
            {"action_id": "long", "direction": 1, "tp_atr": 2, "sl_atr": 1, "horizon": 45},
            {"action_id": "short", "direction": -1, "tp_atr": 1, "sl_atr": 1, "horizon": 1},
        ],
        "global": table,
        "states": [table] * 8,
    }
    encoder = {"family": "regime8", "n_states": 8, "volatility_median": 0.002}
    (tmp_path / "models" / "policy.json").write_text(json.dumps(model))
    (tmp_path / "models" / "encoder.json").write_text(json.dumps(encoder))
    path = tmp_path / "patterns" / "library.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "qualified_policies": [],
                "diagnostic_policies": [
                    {
                        "policy_id": "regime8",
                        "model_path": "models/policy.json",
                        "encoder_path": "models/encoder.json",
                        "model_sha256": hashlib.sha256((tmp_path / "models/policy.json").read_bytes()).hexdigest(),
                        "encoder_sha256": hashlib.sha256((tmp_path / "models/encoder.json").read_bytes()).hexdigest(),
                        "stats": {"fixture": True},
                        "qualified": False,
                        "status": "synthetic_unqualified",
                    }
                ],
            }
        )
    )
    matcher = PolicyMatcher(path, diagnostic=True)
    assert matcher.match(bars())[0]["horizon"] == 45
    choice = matcher.match(bars(), known_close="2024-01-02T13:06Z")[0]
    assert choice["direction"] == "short"
    assert choice["horizon"] == 1
    assert choice["predicted_net_points"] == 1.0
    assert choice["qualified"] is False


def test_edited_model_cannot_inherit_qualified_statistics(library, tmp_path):
    write, _, path = library
    write(qualified=True)
    model = tmp_path / 'models/fixture.json'
    model.write_text(model.read_text() + ' ')
    with pytest.raises(ValueError, match='hash'):
        PolicyMatcher(path)


def test_swapped_identity_cannot_inherit_qualified_statistics(library, tmp_path):
    write, payload, path = library
    write(qualified=True)
    model = tmp_path / 'models/fixture.json'
    content = json.loads(model.read_text())
    content['policy_id'] = 'another_policy'
    model.write_text(json.dumps(content))
    payload['qualified_policies'][0]['model_sha256'] = hashlib.sha256(model.read_bytes()).hexdigest()
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match='identity'):
        PolicyMatcher(path)
