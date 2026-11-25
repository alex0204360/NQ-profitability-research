# A four-minute MNQ risk capacitor

The exposure-clock neuron passed the registered **risk measurement** screen across two discovery windows and a separate five-session historical panel. None of the new trading strategies passed the economic screen. The simplest physical risk band retained a lower quantile loss in every window. The replication is on disjoint dates from the same vendor, with overlapping four-minute outcomes. Independent, executable financial validations remain at zero.

[Download the neuron and offline replay](capacitor-review.zip) · [Interactive risk chart](risk-replay.html) · [Separate November 24 paper session](../paper_sessions/2026-11-24/)

## What the surgery changed

1. **Deliver stored displacement.** Measure voltage in MNQ points. At each bar consume the lesser of the old voltage magnitude and favorable price travel. Leak the remaining voltage by 7/8 and inject 7/8 of signed release times its current scale. The unloaded control shares the same point units. The loaded circuit made $294.50 on the earlier 20 sessions and lost $671 on the 14 November sessions, after $6 per round trip. In the earlier window removing the best day turned the result negative. The five-date replay lost $1,285. [Circuit](capacitor.py) · [Freeze](protocol.md)
2. **Let matured outcomes redistribute charge.** Three hypotheses retain persistent bias, discharge that bias as price moves, or assume zero bias. Their normalized charge shares determine a four-minute prediction. Separate delayed feedback phases allow only matured next-open-to-open outcomes to update the probabilities. A fixed uniform mixture and zero-bias physical model serve as controls. The adaptive bridge improved log loss over the raw reservoir in all three panels but lost to the fixed mixture in November and to zero bias in all three. In all 215 continuous phase segments, its cumulative log loss was within ln(3) of the best component by the marginal-likelihood identity. That mathematical property concerns probability scores. The bridge earned −$132, +$970.50 and −$771 in the three respective trading replays. [Equation and target](learning_protocol.md) · [Weights](bridge_weights.json)
3. **Predict travel before predicting profit.** Issue a band in points for the maximum absolute excursion from the next open through four held bars and the exit open. Use high/low extrema and include the terminal open. The physical starting point is a Brownian reflection-principle bound multiplied by the causal range scale. Each escaped path charges an error capacitor; each contained path leaks a smaller amount. The single capacitor hit its coverage target but paid too much in band width. [Risk protocol](risk_protocol.md)
4. **Correct for overlapping exposure.** Adjacent miss indicators had correlations of 0.56 and 0.53 in the two discovery windows. One unusual minute could charge the controller four times. Route each matured error to the origin's minute modulo four. Read the mean of the four log-widths. For a given sequence of issued misses the combined readout is algebraically a scalar integrator with one-quarter of the gain. The factor of four came from the forecast horizon and was committed before replay. All eligibility, costs, controls and pass criteria stayed fixed. [Derivation](overlap_protocol.md) · [Circuit](overlap.py)

In symbols, at issuance the half-width in points is the previous mean bar range times exp(mean(u)). Once that path matures, its plate adds (ln(2)/8) × (overflow − 0.1). The initial normalized half-width is 1.95996398454 × sqrt(4π/8). The normalization assumes a diffusion model; the measurements test how closely market paths follow it. At one MNQ a band of B points gives a modeled reserve of 2B + $6. Larger excursions, gaps and slippage can exceed this reserve.

## What passed

The risk screen required 87–93% coverage **in each panel** and quantile loss within 5% of the better of the fixed physical band and an empirical rolling 90th percentile. Quantile loss charges 0.9 points per point of underestimated travel and 0.1 per point of overestimation. Arbitrarily wide bands cannot win this screen.

| Window | Mature paths | Clock coverage | Mean radius (pts) | Clock loss | Physical loss | Rolling loss | Loss reduction vs first capacitor |
|---|---:|---:|---:|---:|---:|---:|---:|
| Earlier 20 discovery sessions | 6,852 | 90.00% | 38.75 | 2.951 | 2.886 | 3.047 | 6.25% |
| November 14 discovery sessions | 4,900 | 89.98% | 81.02 | 5.308 | 5.250 | 5.506 | 5.77% |
| Five-date historical replication | 1,750 | 89.43% | 50.43 | 3.633 | 3.536 | 3.488 | 6.52% |

The five replication sessions were October 26–29 and November 2. All candidates were frozen before those bars were opened for this study. October 30 was already known to be incomplete and was excluded at registration. On the five-date panel the first capacitor's loss was 3.887. The corrected capacitor's loss was 4.16% above the better simple control. The strongest excursion exceeded the forecast band by 123.61 points. Coverage across individual replication sessions ranged from 88.86% to 90.29%. Five sessions do not establish precision across future markets. The original preregistered six-day replication in the earlier project remains incomplete.

## Economic comparison

Each cell is net / maximum modeled OHLC drawdown in dollars. One MNQ, $6 per round trip, 15:55 ET flatten, next-open proxies. The $1,500 funded-position test starts afresh in each panel and carries equity across that panel's dates.

| Panel | Original | Original with learned reserve | Original with fixed physical reserve |
|---|---:|---:|---:|
| Earlier 20 | -847.5 / 2,297 | -1,038 / 1,475 | -1,038 / 1,470 |
| November 14 | 2,112.5 / 1,803 | 1,076 / 1,354 | 1,075 / 1,339 |
| Replication five | -592.5 / 1,559.5 | -1,261 / 1,454 | -1,247.5 / 1,443.5 |

On replication the learned reserve strategy earned −$21.02 per trade over 60 trades. It surrendered more money than the frozen original. A risk measurement can be useful while the signal using it has negative expectancy. The scorecards retain $9 round-trip sensitivity on the same fills, daily outcomes, drawdown bounds and exclusions. Cash earned zero throughout. Position-size qualification remains unmet.

## What the November 24 source audit discovered

The after-close original lost $988.50 on 17 modeled trades. The registered daily guard lost $524 on three trades. The full session contained 390 bars. The previous first-seen recorder retained only 214 bars through the 13:03 bar start. All 214 saved calls were reproduced from their first-seen inputs. Four bars had distinct intrabar prices and initially zero reported volume, followed by final reported volumes of 13,610, 7,681, 10,285 and 5,063. Those four were all the moving zero-volume bars in the retained prefix.

Replaying the same frozen brain on first-seen versus final inputs changed 59 close actions or 85 action/position pairs. The common-prefix marked equity moved from −$2,200.50 to −$1,203. Replacing just the volumes reproduced the final action sequence and marked equity. Replacing just OHLC reproduced the first-seen action sequence and marked equity. This is an attribution with hindsight. It establishes a $997.50 simulation difference and does not establish recoverable trading profit. No candidate from this research was scored on Nov 23 or 24. None of 183 eligible saved forecasts was computed within nine seconds of its theoretical close. [Reconciliation](../paper_sessions/2026-11-24/reconciliation.json)

## The next forward track

The new recorder carries the four learned plates and the rolling control across the 18 remaining registered full sessions, starting cold on November 25. It saves first-issued risk widths and original forecasts, source hashes, receipt times and model computation times. It marks directional inputs after a moving zero-volume bar until the next encoder reset, and counts calls issued before their path ended. Late batch calculations can receive bar-model scores without qualifying as timely predictions. The daily ledger is append-only and rejects mismatched source or model signatures. A missing registered date blocks cumulative qualification. Point it at a separate journal for each data source. [Frozen forward agreement](forward_protocol.md)

In the extracted kit use `python record.py --out paper-audit --watch`. From the repository directory, run `python forward.py --out /private/forward-audit --watch` for the current registered session. Supply `--csv finalized-bars.csv` for a growing file from an authorized feed with timestamp_utc, contract and OHLCV fields. Use minute-start timezone-qualified timestamps. Without the flag it polls the dated delayed Yahoo feed. Successful collection depends on the process and host staying up. Current forecasts and diagnostics are emitted to latest.json. The journal also records calls before the path matures. Nothing submits orders.

Over the next year the meaningful advances are testable. First establish the locked four-minute calibration on new sessions from first-seen bars. Then reconcile an exchange-sourced volume stream with a synchronized bid/ask tape and executable nine-second fills. Only advance a directional candidate after it beats cash and simple controls out of sample, remains positive without its best day and meets the risk budget. Repeat the frozen comparison across contract rolls and changing volatility before evaluating size. These are evidence gates, not a forecast of profitability by a particular date.

## Reproduce

Python 3.10+, NumPy and pandas. Private discovery and replication captures follow the same hashed layout as the prior reservoir lab. Output directories must be new. Run feedback_study.py for both voltage and probabilistic results, and risk_study.py for both the scalar and four-clock heads.

```sh
python -m pytest -q test_physics.py
python feedback_study.py /path/to/scratch /tmp/discovery-feedback
python risk_study.py /path/to/scratch /tmp/discovery-scalar
python risk_study.py /path/to/scratch /tmp/discovery-clock --clock
python feedback_study.py /path/to/scratch /tmp/replication-feedback --track replication
python risk_study.py /path/to/scratch /tmp/replication-scalar --track replication
python risk_study.py /path/to/scratch /tmp/replication-clock --track replication --clock
```

Keep the controls in any later report. Full activations and predictions are in results. The repository contains exact weights, causal prefix tests, chronological fills and cash comparisons. The downloadable package includes the forward runner and weights, the interactive historical dashboard and the November 24 original replay. Development commits 48f3070, a48de84, f2d1787 and 58bd8b3 froze each surgical decision, with ac5e1b9 locking scoring before the replication panel.
