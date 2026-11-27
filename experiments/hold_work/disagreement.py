"""Attribute the increment from true volume vs unit mass at the first split."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def analyze(replay_dir, output_dir):
    trades = pd.read_csv(replay_dir / 'trades.csv.gz')
    original = pd.read_csv(replay_dir / 'activations.csv.gz', usecols=[
        'model', 'panel', 'delay', 'trade_id', 'bar_start', 'direction', 'eligible',
        'discretionary', 'volume_score', 'price_score', 'next_executable_price',
        'original_exit_price'])
    original = original[original.model.eq('original')]
    key = ['panel', 'delay', 'trade_id']
    # Up to the first request by either cell, both policies occupy this trade.
    wants = original[original.eligible & original.discretionary &
                     ((original.volume_score <= 0) | (original.price_score <= 0))]
    first = wants.sort_values('bar_start').drop_duplicates(key).copy()
    split = first[(first.volume_score <= 0) != (first.price_score <= 0)].copy()
    split['volume_holds'] = split.volume_score > 0
    split['retrospective_hold_pts'] = split.direction * (
        split.original_exit_price - split.next_executable_price)
    split['volume_vs_price_to_original_exit_usd'] = np.where(
        split.volume_holds, 2, -2) * split.retrospective_hold_pts
    ledger = trades[trades.model.isin(['fixed_volume', 'fixed_price'])].pivot(
        index=key, columns='model', values='gross_usd')
    ledger['volume_vs_price_actual_usd'] = ledger.fixed_volume - ledger.fixed_price
    split = split.merge(ledger.reset_index(), on=key, validate='one_to_one')
    # Every realized difference must be explained by a first split.
    unexplained = ledger[~ledger.index.isin(split.set_index(key).index)]
    if (unexplained.volume_vs_price_actual_usd != 0).any():
        raise ValueError('missing policy disagreement')
    split['source_group'] = np.where(split.panel == 'external', 'external60', 'discovery40')
    report = []
    for (panel, delay, holds), rows in split.groupby(['source_group', 'delay', 'volume_holds']):
        effect = rows.volume_vs_price_actual_usd
        report.append(dict(panel=panel, extra_delay=int(delay), volume_holds=bool(holds),
                           trades=len(rows), dates=rows.trade_id.str[:10].nunique(),
                           mean_actual_hold_pts=float(rows.retrospective_hold_pts.mean()),
                           value_vs_hold_to_original_usd=float(rows.volume_vs_price_to_original_exit_usd.sum()),
                           actual_paired_policy_advantage_usd=float(effect.sum()),
                           paired_advantage_without_best_trade_usd=float(effect.sum()-max(0, effect.max())),
                           volume_better=int((effect > 0).sum()), price_better=int((effect < 0).sum())))
    output_dir.mkdir(exist_ok=True, parents=True)
    split.to_csv(output_dir / 'first-disagreements.csv', index=False)
    (output_dir / 'first-disagreements.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('replay_dir', type=Path)
    p.add_argument('output_dir', type=Path)
    a = p.parse_args()
    analyze(a.replay_dir, a.output_dir)
