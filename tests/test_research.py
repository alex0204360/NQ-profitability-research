"""Research gates and sealed holdout access are independent of attractive results."""

import json
from pathlib import Path

import pytest

from nqprofit.research import (
    check_gate,
    file_hash,
    terminal_validation,
    validate_freeze,
    write_json,
)


def summary():
    return {
        "n": 400,
        "censored_trades": 0,
        "dates": 100,
        "weeks": 30,
        "mean_net_points": 1.25,
        "total_net_points": 500.0,
        "cost_scenarios": {"nq_stress": {"mean_net_points": 0.25}},
    }


def test_training_requires_every_fold_and_positive_three():
    value = summary()
    folds = [{"n": 100, "total_net_points": 125.0} for _ in range(4)]
    assert check_gate(value, folds=folds) == []
    folds[0]["n"] = 29
    assert "fold_support" in check_gate(value, folds=folds)
    folds[0]["total_net_points"] = -1
    folds[1]["total_net_points"] = -1
    assert "fold_consistency" in check_gate(value, folds=folds)


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("n", 199, "sample_size"),
        ("censored_trades", 1, "censored_executions"),
        ("dates", 59, "date_support"),
        ("weeks", 25, "week_support"),
        ("mean_net_points", 0.249, "net_expectancy"),
    ],
)
def test_holdout_fails_any_registered_gate(field, value, reason):
    result = summary()
    result[field] = value
    assert reason in check_gate(result, heldout=True)


def test_cost_stress_derived_from_same_trades():
    value = summary()
    value["mean_net_points"] = 0.75
    assert "stress_expectancy" in check_gate(value, heldout=True)


def test_incomplete_benchmark_cannot_establish_paired_profit_advantage():
    value = summary()
    baseline = summary()
    baseline["censored_trades"] = 1
    assert "baseline_censored_executions" in check_gate(
        value, heldout=True, benchmarks=[baseline]
    )


def test_canonical_json_and_immutable_write(tmp_path):
    path = tmp_path / "result.json"
    write_json(path, {"b": 2, "a": 1}, immutable=True)
    assert json.loads(path.read_text()) == {"a": 1, "b": 2}
    write_json(path, {"a": 1, "b": 2}, immutable=True)
    with pytest.raises(ValueError, match="immutable"):
        write_json(path, {"a": 2}, immutable=True)
    with pytest.raises(ValueError):
        write_json(tmp_path / "bad.json", {"x": float("nan")})


def frozen_project(tmp_path):
    (tmp_path / "history").mkdir()
    (tmp_path / "reports").mkdir()
    item = tmp_path / "model.json"
    item.write_text("{}\n")
    frozen = {"survivors": [], "artifacts": {"model.json": file_hash(item)}}
    write_json(tmp_path / "reports/freeze.json", frozen)
    write_json(
        tmp_path / "history/freeze_publication.json",
        {
            "freeze_sha256": file_hash(tmp_path / "reports/freeze.json"),
            "remote_commit": "1" * 40,
            "verified": True,
        },
    )
    return frozen


def test_freeze_requires_publication_and_unchanged_artifacts(tmp_path):
    frozen_project(tmp_path)
    assert validate_freeze(tmp_path)["survivors"] == []
    (tmp_path / "model.json").write_text('{"changed":true}')
    with pytest.raises(ValueError, match="changed"):
        validate_freeze(tmp_path)


def test_missing_publication_does_not_allow_holdout(tmp_path):
    frozen_project(tmp_path)
    (tmp_path / "history/freeze_publication.json").unlink()
    with pytest.raises(ValueError, match="publication"):
        validate_freeze(tmp_path)


def test_empty_freeze_skips_holdout_without_opening_path(tmp_path):
    frozen_project(tmp_path)
    result = terminal_validation(tmp_path, holdout_path=Path("/nonexistent/never_read.parquet"))
    assert result["status"] == "not_run_no_survivors"
    assert not (tmp_path / "history/heldout_access.json").exists()
    assert json.loads((tmp_path / "reports/stage2.json").read_text())["status"] == result["status"]


def test_frozen_candidate_failure_is_retained_and_other_candidate_runs(tmp_path):
    from nqprofit.research import score_frozen_family
    calls = []
    def evaluate(name):
        calls.append(name)
        if name == 'broken':
            raise ValueError('fixture failure')
        return {'policy_id':name,'summary':summary(),'reasons':[],
                'bootstrap':{'p_value':.001,'lower_bounds_positive':True}}
    results = score_frozen_family(tmp_path, ['broken','working'], evaluate)
    assert calls == ['broken','working']
    assert results[0]['qualified'] is False
    assert results[0]['holm']['adjusted_p'] == 1.0
    assert results[1]['qualified'] is True
    assert results[1]['holm']['adjusted_p'] == .002
    assert 'fixture failure' in (tmp_path/'history/events.jsonl').read_text()


def test_terminal_shared_failure_leaves_terminal_artifact(tmp_path, monkeypatch):
    import nqprofit.research as research
    frozen_project(tmp_path)
    document = json.loads((tmp_path/'reports/freeze.json').read_text())
    document['survivors'] = ['fixture']
    write_json(tmp_path/'reports/freeze.json', document)
    write_json(tmp_path/'history/freeze_publication.json',
               {'freeze_sha256':file_hash(tmp_path/'reports/freeze.json'),
                'verified':True,'remote_commit':'1'*40})
    result = research.terminal_validation(tmp_path, holdout_path=tmp_path/'missing.parquet')
    assert result['status'] == 'failed'
    assert result['qualified'] == []
    assert (tmp_path/'reports/stage2.json').exists()
    assert research.terminal_validation(tmp_path, holdout_path=tmp_path/'missing.parquet') == result
