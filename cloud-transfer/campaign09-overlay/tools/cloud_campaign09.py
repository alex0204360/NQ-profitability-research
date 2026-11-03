"""Preregistered causal path-PCA versus snapshot MNQ development experiment."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.decomposition import PCA
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from tools.causal_execution import replay_causal
from tools.cloud_campaign06 import load_original, load_upload
from tools.cloud_campaign07 import frozen_baseline_metrics
from tools.cloud_robust_teacher import robust_teacher
from tools.fresh_transfer_test import delayed_signal, lower_bound, session_days
from tools.mnq_oracle_prepare import causal_features, sha256
from tools.mnq_oracle_research import save_json
from tools.opportunity_research import COSTS, FEATURES, write_records
from tools.physics_state import physics_features
from tools.shared_game_state import build_market_states
from tools.temporal_path_state import completed_path

ROOT = Path('/workspace')
CODE = Path(__file__).resolve().parents[1]
PLAN = CODE / 'docs/CLOUD_CAMPAIGN09.json'
OUT = ROOT / 'mnq-private-results/cloud_campaign09'


def inputs(bars: pd.DataFrame):
    states = build_market_states(bars)
    causal = causal_features(bars)
    path, path_ready = completed_path(bars, states.atr14.to_numpy(float))
    ready = (states.ready & causal.feature_ready & physics_features(bars, states).physics_ready).to_numpy(bool) & path_ready
    snapshot = states.copy()
    snapshot['log1p_atr14_ticks'] = np.log1p(snapshot.atr14 / .25)
    x = snapshot[FEATURES].to_numpy(float)
    if not np.isfinite(x[ready]).all() or not np.isfinite(path[ready]).all():
        raise ValueError('Nonfinite eligible features')
    return states, x, path, ready


def predict(model, x: np.ndarray, ready: np.ndarray) -> np.ndarray:
    output = np.full((len(x), 2), np.nan)
    output[ready] = model.predict(x[ready])
    return output


def decisions(pred: np.ndarray, ready: np.ndarray, window: np.ndarray) -> np.ndarray:
    chosen = np.argmax(np.where(np.isfinite(pred), pred, -np.inf), axis=1)
    positive = np.max(np.where(np.isfinite(pred), pred, -np.inf), axis=1) > 0
    return np.where(ready & window & positive, np.where(chosen == 0, 1, -1), 0).astype(int)


def predictive_scores(pred: np.ndarray, truth: np.ndarray, mask: np.ndarray) -> dict:
    if mask.sum() < 10:
        raise ValueError('Too few matured predictive observations')
    rows = []
    for action, name in enumerate(('long', 'short')):
        observed, estimated = truth[mask, action], pred[mask, action]
        rho = float(spearmanr(observed, estimated).statistic)
        rows.append({'action': name, 'spearman': rho if np.isfinite(rho) else None,
                     'mae_usd': float(mean_absolute_error(observed, estimated)),
                     'r2': float(r2_score(observed, estimated))})
    return {'matured_opportunities': int(mask.sum()), 'by_action': rows,
            'mean_spearman': float(np.mean([r['spearman'] for r in rows])) if all(r['spearman'] is not None for r in rows) else None}


def run(out: Path = OUT) -> dict:
    out = Path(out)
    if out.exists():
        raise ValueError('Campaign09 output exists; use a new immutable directory')
    plan = json.loads(PLAN.read_text())
    out.mkdir(parents=True)
    save_json(out / 'protocol.json', plan)
    save_json(out / 'source_hashes.json', {p.name: sha256(p) for p in
              (PLAN, Path(__file__), CODE / 'tools/temporal_path_state.py',
               CODE / 'tools/causal_execution.py', CODE / 'tools/cloud_robust_teacher.py')})
    result = {'status': 'running', 'training': {}, 'windows': [], 'sealed_2025_access': False,
              'broker_orders': 0, 'live_authorized': False}
    try:
        original, audit = load_original()
        original_state, original_x, original_path, original_ready = inputs(original)
        maturity = pd.Timestamp(plan['training']['target_maturity_cutoff_exclusive'])
        net, valid, _ = robust_teacher(original, maturity)
        train = original_ready & valid & (original.timestamp < maturity).to_numpy()
        if train.sum() < 1000:
            raise ValueError('Too few training rows')
        y = np.min(net[train], axis=2)
        with threadpool_limits(limits=1):
            encoder = make_pipeline(StandardScaler(), PCA(n_components=8, random_state=20261103))
            train_pc = encoder.fit_transform(original_path[train])
            models = {
                'snapshot_ridge': make_pipeline(StandardScaler(), Ridge(alpha=100)),
                'path_pca_ridge': make_pipeline(StandardScaler(), Ridge(alpha=100)),
            }
            models['snapshot_ridge'].fit(original_x[train], y)
            models['path_pca_ridge'].fit(np.column_stack((original_x[train], train_pc)), y)
        joblib.dump({'encoder': encoder, 'models': models, 'features': FEATURES,
                     'plan_sha256': sha256(PLAN), 'training_maturity_cutoff': maturity.isoformat(),
                     'live_authorized': False}, out / 'models_PRIVATE.joblib')
        result['training'] = {'source_audit': audit, 'rows': int(train.sum()),
                              'last_training_signal': original.timestamp[train].iloc[-1].isoformat(),
                              'maturity_cutoff': maturity.isoformat(),
                              'pca_explained_variance_ratio': encoder[-1].explained_variance_ratio_.tolist()}
        save_json(out / 'results.json', result)
        for spec in plan['fixed_development_windows']:
            name = spec['id']
            if name.startswith('original_'):
                bars, states, x, path, ready, source_audit = original, original_state, original_x, original_path, original_ready, audit
            else:
                source = ROOT / 'mnq-private-results' / ('fresh01' if name == 'upload_oct13_29' else 'cloud_fresh03_lineage')
                bars, source_audit = load_upload(source, blocked=name == 'upload_oct13_29')
                states, x, path, ready = inputs(bars)
            start, end = pd.Timestamp(spec['start']), pd.Timestamp(spec['end_exclusive'])
            window = ((bars.timestamp >= start) & (bars.timestamp < end)).to_numpy()
            pc = np.full((len(bars), 8), np.nan)
            with threadpool_limits(limits=1):
                pc[ready] = encoder.transform(path[ready])
                predictions = {
                    'snapshot_ridge': predict(models['snapshot_ridge'], x, ready),
                    'path_pca_ridge': predict(models['path_pca_ridge'], np.column_stack((x, pc)), ready),
                }
            target, valid, _ = robust_teacher(bars, end)
            truth = np.min(target, axis=2)
            scoring = window & ready & valid
            days = sorted(set(session_days(bars.loc[window, 'timestamp'])))
            row = {'id': name, 'source_audit': source_audit, 'observed_sessions': len(days),
                   'eligible_opportunities': int((window & ready).sum()), 'models': {}, 'frozen_8_gate': []}
            if name.startswith('upload_'):
                for delay in (0, 1):
                    for cost_name in COSTS:
                        row['frozen_8_gate'].append({'delay': delay, 'cost': cost_name,
                                                      'metrics': frozen_baseline_metrics(name, delay, cost_name)})
            for model_name, pred in predictions.items():
                signal = decisions(pred, ready, window)
                model_row = {'prediction': predictive_scores(pred, truth, scoring),
                             'signals': int(np.count_nonzero(signal)), 'evaluations': []}
                write_records(out / f'{name}_{model_name}_decisions_PRIVATE.jsonl.gz', (
                    {'index': int(i), 'available_at': (bars.timestamp.iloc[i] + pd.Timedelta(minutes=1)).isoformat(),
                     'ready': bool(ready[i]), 'predicted_robust_stress_net_long_usd': float(pred[i, 0]) if ready[i] else None,
                     'predicted_robust_stress_net_short_usd': float(pred[i, 1]) if ready[i] else None,
                     'action': int(signal[i]), 'live_authorized': False}
                    for i in np.flatnonzero(window)))
                for delay in (0, 1):
                    action = delayed_signal(signal, ready, bars.timestamp) if delay else signal
                    for cost_name, cost in COSTS.items():
                        metrics, trades, events = replay_causal(bars, action, states.atr14.to_numpy(float),
                                                                start, end, 'time10', cost)
                        if abs(metrics['net'] - sum(trade['net'] for trade in trades)) > 1e-8:
                            raise ValueError('Trade journal does not reconcile')
                        key = f'{name}_{model_name}_delay{delay}_{cost_name}'
                        write_records(out / f'{key}_trades_PRIVATE.jsonl.gz', trades)
                        write_records(out / f'{key}_events_PRIVATE.jsonl.gz', events)
                        item = {'delay': delay, 'cost': cost_name, 'metrics': metrics,
                                'gap_exit_net_usd': float(sum(t['net'] for t in trades if t['reason'] == 'unresolved_gap_next_observed_open'))}
                        if cost_name == 'stress':
                            item['session_bootstrap'] = lower_bound(trades, days)
                        model_row['evaluations'].append(item)
                row['models'][model_name] = model_row
            result['windows'].append(row)
            save_json(out / 'results.json', result)
        result['status'] = 'complete_development'
        save_json(out / 'results.json', result)
        save_json(out / 'manifest.json', {'completed': True, 'files_sha256':
                  {p.name: sha256(p) for p in out.iterdir() if p.is_file() and p.name != 'manifest.json'}})
        return result
    except Exception as exc:
        result['status'] = 'failed'
        result['error'] = {'type': type(exc).__name__, 'message': str(exc)}
        save_json(out / 'results.json', result)
        raise


if __name__ == '__main__':
    run()
