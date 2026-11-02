"""Hash-verified, research-only queries for the dual-delay campaign students."""

import argparse
import hashlib
import io
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np

from tools.opportunity_research import FEATURES
from tools.reliability_decision_api import _time

STUDENTS = ('ridge_dual_delay', 'extra_trees_dual_delay')


def decide(run, student, observation, *, mode='historical', now=None):
    if student not in STUDENTS or mode not in ('historical', 'paper'):
        raise ValueError('Registered student and mode required')
    if not isinstance(observation, dict) or set(observation) != {'available_at', 'ready', 'features'}:
        raise ValueError('Exact causal observation schema required')
    if type(observation['ready']) is not bool:
        raise ValueError('Boolean ready required')
    features = observation['features']
    if not isinstance(features, dict) or set(features) != set(FEATURES):
        raise ValueError('Exact 18-feature causal state required')
    values = [features[k] for k in FEATURES]
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise ValueError('Finite numeric features required')
    available = _time(observation['available_at'])
    age = None
    if mode == 'paper':
        current = datetime.now(UTC) if now is None else now
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError('Aware clock required')
        age = (current - available).total_seconds()
        if age < 0 or age > 120:
            raise ValueError('Future or stale state')
    run = Path(run).resolve()
    if '2025' in str(run):
        raise ValueError('Sealed path forbidden')
    manifest = json.loads((run / 'manifest.json').read_text())
    protocol_path = run / 'protocol.json'
    model_path = run / (student + '.joblib')
    source_path = run / 'source_hashes.json'
    protocol_bytes, model_bytes = protocol_path.read_bytes(), model_path.read_bytes()
    source_bytes = source_path.read_bytes()
    hashes = manifest.get('files_sha256', {})
    protocol_hash = hashlib.sha256(protocol_bytes).hexdigest()
    model_hash = hashlib.sha256(model_bytes).hexdigest()
    if (not manifest.get('completed') or hashes.get('protocol.json') != protocol_hash or
            hashes.get(model_path.name) != model_hash or
            hashes.get('source_hashes.json') != hashlib.sha256(source_bytes).hexdigest()):
        raise ValueError('Incomplete or altered student campaign')
    source_hashes = json.loads(source_bytes)
    source_root = Path(__file__).resolve().parents[1]
    for name, relative in {
        'cloud_campaign01.py': 'tools/cloud_campaign01.py',
        'CLOUD_CAMPAIGN01.json': 'docs/CLOUD_CAMPAIGN01.json',
        'causal_execution.py': 'tools/causal_execution.py',
        'shared_game_state.py': 'tools/shared_game_state.py',
    }.items():
        if hashlib.sha256((source_root / relative).read_bytes()).hexdigest() != source_hashes[name]:
            raise ValueError('Campaign source changed: ' + name)
    protocol = json.loads(protocol_bytes)
    if student not in protocol['candidates'] or protocol['version'] != 'mnq-cloud-dual-delay-value-v1':
        raise ValueError('Unregistered student campaign')
    bundle = joblib.load(io.BytesIO(model_bytes))
    if (bundle['id'] != student or bundle['features'] != FEATURES or
            bundle['plan_sha256'] != source_hashes['CLOUD_CAMPAIGN01.json']):
        raise ValueError('Student checkpoint identity mismatch')
    cutoff = _time(bundle['training_cutoff'])
    if available <= cutoff:
        raise ValueError('Observation overlaps training')
    prediction = np.asarray(bundle['model'].predict(np.asarray([values], dtype=float)))
    if prediction.shape != (1, 2) or not np.isfinite(prediction).all():
        raise ValueError('Two finite delay predictions required')
    immediate, delayed = map(float, prediction[0])
    if not observation['ready']:
        action, reason = 'abstain', 'Causal state unready'
    elif immediate > 6 and delayed > 6:
        action, reason = 'enter_long', 'Both gross forecasts strictly exceed $6'
    elif immediate < -6 and delayed < -6:
        action, reason = 'enter_short', 'Both gross forecasts are strictly below -$6'
    else:
        action, reason = 'abstain', 'Dual-delay gross margin not met'
    return {'schema_version': 'cloud-student-decision-v1', 'candidate': student,
            'available_at': available.isoformat(), 'mode': mode, 'paper_age_seconds': age,
            'action': action, 'reason': reason,
            'predicted_gross_usd': {'next_open': immediate, 'one_bar_delay': delayed},
            'stress_round_trip_cost_usd': 6, 'holding_limit_bars': 10,
            'training_cutoff': cutoff.isoformat(),
            'model_hashes': {'protocol.json': protocol_hash, model_path.name: model_hash,
                             'source_hashes.json': hashes['source_hashes.json']},
            'hash_lineage': {'protocol.json': protocol_hash, model_path.name: model_hash,
                             'source_hashes.json': hashes['source_hashes.json']},
            'input_state': dict(features), 'selected': False, 'research_only': True,
            'live_authorized': False, 'orders_submitted': 0,
            'uncertainty': 'Exploratory dual-delay forecasts failed registered economics; no calibrated confidence or independent confirmation.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--student', choices=STUDENTS, required=True)
    p.add_argument('--mode', choices=('historical', 'paper'), default='historical')
    p.add_argument('--observation', type=Path, required=True)
    a = p.parse_args()
    result = decide(a.run, a.student, json.loads(a.observation.read_text()), mode=a.mode)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
