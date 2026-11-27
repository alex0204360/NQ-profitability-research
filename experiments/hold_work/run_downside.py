"""Evaluate the frozen quantile forecasts on the archived first-decision ledger."""
import argparse
import heapq
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .downside import TailMemory, scales


def roughness(tape):
    rows = []
    for (_, _), day in tape.groupby(['panel', 'date']):
        previous = time = level = None
        for bar in day.sort_values('bar_start').itertuples():
            if (time is None or bar.bar_start - time != pd.Timedelta(minutes=1)
                    or not np.isfinite(bar.forecast) or not np.isfinite(previous)):
                level = None
            else:
                delta = abs(bar.forecast - previous)
                level = delta if level is None else 0.875 * level + 0.125 * delta
            rows.append((bar.panel, bar.bar_start, bar.forecast, level))
            previous, time = bar.forecast, bar.bar_start
    return pd.DataFrame(rows, columns=['panel', 'bar_start', 'tape_forecast', 'roughness'])


def projections(group):
    memory = TailMemory()
    pending = []
    rows = []
    for i, trade in enumerate(group.sort_values('bar_start').itertuples()):
        issued = trade.bar_start + pd.Timedelta(minutes=1)
        while pending and pending[0][0] < issued:
            _, _, scale, loss = heapq.heappop(pending)
            memory.observe(scale, loss)
        alternate = issued + pd.Timedelta(minutes=trade.delay)
        cutoff = pd.Timestamp(trade.date + ' 15:55', tz='America/New_York')
        available = (cutoff - alternate).total_seconds() / 60
        scale = scales(trade.entry_scale, trade.forecast,
                       None if pd.isna(trade.roughness) else trade.roughness, available)
        forecast = memory.predict(scale)
        record = dict(trade_id=trade.trade_id, date=trade.date, source=trade.source,
                      delay=int(trade.delay), decision_utc=issued, alternate_utc=alternate,
                      prior_count=memory.count, entry_scale=trade.entry_scale,
                      parent_forecast=trade.forecast, roughness=trade.roughness, clock_minutes=available,
                      predicted_duration=(scale['distance']/trade.entry_scale)**2)
        for name in scale:
            record['q_' + name] = forecast[name] if forecast is not None else np.nan
        # Future values join the queue after issuance. Delayed labels cannot affect the current forecast.
        loss = max(0.0, -trade.realized_hold_pts) if pd.notna(trade.realized_hold_pts) else np.nan
        if np.isfinite(loss):
            assert alternate == trade.next_executable_time and alternate <= trade.original_exit_time
            heapq.heappush(pending, (trade.original_exit_time, i, scale, loss))
        record.update(realized_duration=(trade.original_exit_time-alternate).total_seconds()/60,
                      loss_pts=loss)
        rows.append(record)
    return pd.DataFrame(rows)


def summarize(rows, all_dates):
    scored = rows.dropna(subset=['q_distance', 'loss_pts']).copy()
    dates = [date for date in all_dates if date >= scored.date.min()]
    n = len(dates)
    start = np.random.default_rng(2711).integers(n, size=(10000, (n+4)//5, 1))
    blocks = ((start + np.arange(5)) % n).reshape(10000, -1)[:, :n]
    counts = scored.groupby('date').size().reindex(dates, fill_value=0).to_numpy()
    totals = counts[blocks].sum(axis=1)
    valid = totals > 0
    models = {}
    for name in ['constant', 'range', 'clock', 'distance']:
        q = scored['q_' + name]
        residual = scored.loss_pts - q
        pinball = np.maximum(0.8*residual, -0.2*residual)
        scored['pinball_' + name] = pinball
        models[name] = dict(pinball_pts=float(pinball.mean()),
                            exceedance=float((residual > 0).mean()), mean_prediction=float(q.mean()))
    deltas = {}
    for control in ['constant', 'range', 'clock']:
        diff = scored.pinball_distance - scored['pinball_' + control]
        daily = diff.groupby(scored.date).sum().reindex(dates, fill_value=0).to_numpy()
        sampled = daily[blocks].sum(axis=1)[valid]/totals[valid]
        deltas[control] = dict(mean=float(diff.mean()),
                               interval95=np.quantile(sampled, [.025,.975]).tolist())
    return dict(eligible=len(rows), scored=len(scored), sessions_in_bootstrap=n,
                mean_downside=float(scored.loss_pts.mean()), models=models,
                spearman_duration=float(spearmanr(scored.predicted_duration,scored.realized_duration).statistic),
                paired_distance_minus_control=deltas)


def run(bundle, output):
    decisions = pd.read_csv(bundle/'first-decisions.csv.gz')
    tape = pd.read_csv(bundle/'equity.csv.gz', usecols=['panel','date','model','delay','bar_start','forecast'])
    tape = tape.loc[tape.model.eq('original') & tape.delay.eq(0)].copy()
    tape['bar_start'] = pd.to_datetime(tape.bar_start, utc=True)
    for column in ['bar_start','next_executable_time','original_exit_time']:
        decisions[column] = pd.to_datetime(decisions[column], utc=True)
    merged = decisions.merge(roughness(tape), how='left', on=['panel','bar_start'], validate='many_to_one')
    np.testing.assert_allclose(merged.forecast, merged.tape_forecast)
    archives = []
    summary = {}
    merged['source'] = np.where(merged.panel.eq('external'), 'external60', 'discovery40')
    for (source, delay), group in merged.groupby(['source','delay']):
        session_dates = sorted(tape.loc[tape.panel.eq('external') == (source == 'external60'), 'date'].unique())
        rows = projections(group)
        summary.setdefault(source, {})[int(delay)] = summarize(rows, session_dates)
        archives.append(rows)
    output.mkdir(parents=True, exist_ok=True)
    pd.concat(archives).to_csv(output/'forecasts.csv.gz', index=False,
                               compression={'method':'gzip', 'mtime':0})
    (output/'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    run(args.bundle,args.output)
