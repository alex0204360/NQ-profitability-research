"""Verified public aggregate and readable dashboard for the fixed path experiment."""
from __future__ import annotations

import html
import json
from pathlib import Path

from tools.mnq_oracle_prepare import sha256
from tools.opportunity_research import verify_manifest

ROOT = Path('/workspace')
PRIVATE = ROOT / 'mnq-private-results/cloud_campaign09_retry1'
CODE = ROOT / 'mnq-oracle-code'
OUT = ROOT / 'outputs'
SUMMARY = OUT / 'mnq_path_representation_summary.json'
PAGE = OUT / 'mnq_path_representation_dashboard.html'


def aggregate() -> dict:
    verify_manifest(PRIVATE, {})
    hashes = json.loads((PRIVATE / 'source_hashes.json').read_text())
    if sha256(CODE / 'docs/CLOUD_CAMPAIGN09.json') != hashes['CLOUD_CAMPAIGN09.json']:
        raise ValueError('Frozen campaign09 protocol changed')
    result = json.loads((PRIVATE / 'results.json').read_text())
    if result['status'] != 'complete_development' or len(result['windows']) != 4:
        raise ValueError('Incomplete campaign09 matrix')
    windows = []
    for w in result['windows']:
        models = {}
        for name, m in w['models'].items():
            cells = []
            for delay in (0, 1):
                costs = {e['cost']: e for e in m['evaluations'] if e['delay'] == delay}
                if set(costs) != {'base', 'stress', 'extreme'}:
                    raise ValueError('Incomplete cost matrix')
                stress = costs['stress']
                cells.append({'delay': delay, 'trades': stress['metrics']['trades'],
                              'base_net_usd': costs['base']['metrics']['net'],
                              'stress_net_usd': stress['metrics']['net'],
                              'extreme_net_usd': costs['extreme']['metrics']['net'],
                              'stress_drawdown_usd': stress['metrics']['max_drawdown_bar_close'],
                              'stress_drawdown_pct_account': 100 * stress['metrics']['max_drawdown_bar_close'] / 25000,
                              'gap_exits': stress['metrics']['gap_unresolved_trades'],
                              'active_sessions': stress['session_bootstrap']['active_sessions'],
                              'bootstrap_lower_usd_per_trade': stress['session_bootstrap']['lower_2_5_percentile_usd_per_trade']})
            models[name] = {'prediction': m['prediction'], 'signals': m['signals'], 'execution': cells}
        gate = [{'delay': e['delay'], 'cost': e['cost'], 'trades': e['metrics']['trades'],
                 'net_usd': e['metrics']['net'], 'drawdown_usd': e['metrics']['max_drawdown_bar_close']}
                for e in w['frozen_8_gate']]
        windows.append({'id': w['id'], 'observed_sessions': w['observed_sessions'],
                        'eligible_opportunities': w['eligible_opportunities'],
                        'models': models, 'unchanged_8_gate': gate})
    original = windows[:2]
    gains = [w['models']['path_pca_ridge']['prediction']['mean_spearman'] -
             w['models']['snapshot_ridge']['prediction']['mean_spearman'] for w in original]
    screen = {'rank_gain_at_least_0_02_both_original_windows': all(g >= .02 for g in gains),
              'positive_rank_both_original_windows': all(w['models']['path_pca_ridge']['prediction']['mean_spearman'] > 0 for w in original),
              'positive_delayed_stress_both_upload_windows': all(w['models']['path_pca_ridge']['execution'][1]['stress_net_usd'] > 0 for w in windows[2:]),
              'more_delayed_stress_than_snapshot_and_gate_both_upload_windows': all(
                  w['models']['path_pca_ridge']['execution'][1]['stress_net_usd'] >
                  w['models']['snapshot_ridge']['execution'][1]['stress_net_usd'] and
                  w['models']['path_pca_ridge']['execution'][1]['stress_net_usd'] >
                  next(e['net_usd'] for e in w['unchanged_8_gate'] if e['delay'] == 1 and e['cost'] == 'stress')
                  for w in windows[2:]),
              'at_least_50_delayed_upload_trades': sum(w['models']['path_pca_ridge']['execution'][1]['trades'] for w in windows[2:]) >= 50,
              'at_least_10_active_upload_sessions': sum(w['models']['path_pca_ridge']['execution'][1]['active_sessions'] for w in windows[2:]) >= 10,
              'positive_extreme_net_both_delays_both_upload_windows': all(
                  e['extreme_net_usd'] > 0 for w in windows[2:] for e in w['models']['path_pca_ridge']['execution']),
              'positive_bootstrap_lower_both_delays_both_upload_windows': all(
                  e['bootstrap_lower_usd_per_trade'] is not None and e['bootstrap_lower_usd_per_trade'] > 0
                  for w in windows[2:] for e in w['models']['path_pca_ridge']['execution']),
              'drawdown_below_1500_both_delays_both_upload_windows': all(
                  e['stress_drawdown_usd'] < 1500 for w in windows[2:] for e in w['models']['path_pca_ridge']['execution']),
              'rank_gains_original_windows': gains}
    screen['passed'] = all(v for k, v in screen.items() if k not in ('rank_gains_original_windows', 'passed'))
    return {'status': 'rejected_development' if not screen['passed'] else 'screen_passed_development_only',
            'screen': screen, 'training_rows': result['training']['rows'],
            'pca_explained_variance_ratio': result['training']['pca_explained_variance_ratio'],
            'windows': windows, 'account_reference_usd': 25000,
            'drawdown_reference_usd': 1500, 'firm_rule_verified': False,
            'limitations': ['Opened development windows; no untouched confirmation',
                            'Yahoo-labeled candles have unverified contract, roll, and minute convention',
                            'Single-contract time exits have no hard loss bound',
                            'Model estimates are not calibrated probabilities; minute targets overlap'],
            'live_authorized': False, 'broker_orders': 0, 'sealed_2025_access': False}


def render(data: dict) -> str:
    esc = lambda x: html.escape(str(x))
    money = lambda x: f'{x:+,.2f}'
    sections = []
    for w in data['windows']:
        rows = []
        for name in ('snapshot_ridge', 'path_pca_ridge'):
            m = w['models'][name]
            a, b = m['execution']
            rows.append(f'<tr><td>{esc(name)}</td><td>{m["prediction"]["mean_spearman"]:.3f}</td><td>{m["signals"]}</td>'
                        f'<td>{a["trades"]}</td><td>{money(a["stress_net_usd"])}</td>'
                        f'<td>{money(b["stress_net_usd"])}</td><td>{money(a["extreme_net_usd"])}</td>'
                        f'<td>{a["stress_drawdown_usd"]:.2f}</td><td>{a["active_sessions"]}</td>'
                        f'<td>{money(a["bootstrap_lower_usd_per_trade"]) if a["bootstrap_lower_usd_per_trade"] is not None else "—"}</td></tr>')
        if w['unchanged_8_gate']:
            gate = w['unchanged_8_gate']
            immediate = next(e for e in gate if e['delay'] == 0 and e['cost'] == 'stress')
            delayed = next(e for e in gate if e['delay'] == 1 and e['cost'] == 'stress')
            extreme = next(e for e in gate if e['delay'] == 0 and e['cost'] == 'extreme')
            rows.append(f'<tr><td>unchanged $8 gate</td><td>—</td><td>—</td><td>{immediate["trades"]}</td>'
                        f'<td>{money(immediate["net_usd"])}</td><td>{money(delayed["net_usd"])}</td>'
                        f'<td>{money(extreme["net_usd"])}</td><td>{immediate["drawdown_usd"]:.2f}</td><td>—</td><td>—</td></tr>')
        rows.append('<tr><td>no trade</td><td>—</td><td>0</td><td>0</td><td>+0.00</td><td>+0.00</td>'
                    '<td>+0.00</td><td>0.00</td><td>0</td><td>—</td></tr>')
        sections.append(f'<h2>{esc(w["id"])} · {w["observed_sessions"]} sessions</h2>'
                        '<div class="scroll"><table><thead><tr><th>Agent</th><th>Mean rank</th><th>Signals</th>'
                        '<th>Trades</th><th>Immediate stress $</th><th>Delayed stress $</th>'
                        '<th>Immediate extreme $</th><th>Immediate DD $</th><th>Active sessions</th>'
                        '<th>Bootstrap lower $/trade</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>')
    gains = data['screen']['rank_gains_original_windows']
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MNQ path information experiment</title><style>
body{{font-family:system-ui,sans-serif;background:#0d1727;color:#ebf3ff;margin:0}}main{{max-width:1180px;margin:auto;padding:28px 22px 70px}}h1{{font-size:2.5rem}}h2{{margin-top:34px}}p{{color:#bfd0e5;line-height:1.6}}.lead{{font-size:1.2rem}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}.card{{background:#172841;border:1px solid #385270;border-radius:12px;padding:18px}}.card b{{font-size:1.7rem;display:block}}.scroll{{overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:.86rem}}th,td{{border-bottom:1px solid #344b68;padding:10px;text-align:left;white-space:nowrap}}th{{background:#203754}}.flow{{display:flex;gap:8px;flex-wrap:wrap}}.flow span{{border:1px solid #466488;background:#1b304b;border-radius:8px;padding:12px}}.warning{{border-left:4px solid #ffc167;background:#302b29;padding:14px}}small{{color:#a9bdd5}}</style></head><body><main>
<h1>Does a learned price and volume path add MNQ edge?</h1><p class="lead"><b>No defensible advantage found.</b> The frozen eight-component path representation improved rank correlation by only {gains[0]:.3f} and {gains[1]:.3f} on the two original October windows, below the predeclared 0.020 gain required in each. The path student lost on the 14-session upload under both fill timings.</p>
<div class="grid"><div class="card"><b>{data['training_rows']:,}</b>identical training rows for both agents</div><div class="card"><b>{money(data['windows'][2]['models']['path_pca_ridge']['execution'][0]['stress_net_usd'])}</b>path agent · 14-session immediate stress</div><div class="card"><b>{money(data['windows'][2]['models']['path_pca_ridge']['execution'][1]['stress_net_usd'])}</b>path agent · delayed stress</div><div class="card"><b>6%</b>$1,500 of $25,000 reference</div></div>
<h2>Read the agents left to right</h2><div class="flow"><span>Completed minute OHLCV</span><span>18 causal snapshot features</span><span>Optional 32-minute path → frozen PCA(8)</span><span>Ridge estimates long and short net value</span><span>Choose larger value if positive; else abstain</span><span>Next-open entry, ten-bar exit, costs and delayed-fill stress</span></div>
<p>The future ten-bar outcome teaches each agent during training only. Its decision trace contains completed-bar availability time, both predicted values, readiness, and action. The models do not expose calibrated confidence probabilities; uncertainty here is measured by rank stability, session bootstrap, delay sensitivity, and drawdown.</p>
{''.join(sections)}
<div class="warning"><b>Research status: NOT READY.</b> The path student failed the predeclared predictive and economic screens. The unchanged $8 gate remains a comparison baseline: its 14-session immediate stressed drawdown was $816.50, below the $1,500 reference, while one-bar-delayed drawdown was $1,657.00. The firm’s exact rule is unverified.</div>
<p><small>All windows were previously opened development observations. The Yahoo-labeled candle feed has unverified contract, roll, and timestamp conventions. Trades are simulated one-contract MNQ outcomes, not live fills. Raw 2025 data stayed sealed; no broker orders were sent. Aggregate data: mnq_path_representation_summary.json.</small></p>
</main></body></html>'''


def run() -> dict:
    data = aggregate()
    OUT.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')
    PAGE.write_text(render(data), encoding='utf-8')
    return data


if __name__ == '__main__':
    run()
