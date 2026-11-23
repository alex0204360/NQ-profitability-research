# Does a failed recovery justify closing a reservoir trade?

**Research decision.** Retain the frozen original reservoir as reference. The first exit circuit produced a full-strategy November loss. The second recovered much of that profit and reduced November drawdown, but it missed too much upside to qualify as a replacement. Neither hold score is calibrated. Every observed date is discovery for these circuits; November 23 was excluded.

## Two hand-programmed surgeries

The original Forecast (pts) supplies every new-entry decision. The new Hold value (pts) concerns an existing position; positive favors holding either side. Its horizon runs from the next open through four further minute intervals, capped by the original exit, gap or 15:55 ET liquidation. Each completed close re-evaluates the score. These horizon labels are used only for diagnostics. Both strategies and controls use one MNQ, next-open fills, $6 per round trip and half-cost minute-close equity marks. A minute-close drawdown can understate intrabar losses.

1. **Adverse impact**, frozen at 13318e9. Track adverse displacement and displacement per unit of relative volume. A shock requires a move unusually large on both scales. At the next close, favorable motion repays the shock. Remaining debt reduces the side-adjusted original forecast. The price-only exit sets relative volume to one. This circuit debited pressure early and often. On November's original held-bar cohort it generated 495 nonpositive readings averaging −22.97 points; the observed truncated four-bar signed movement averaged +1.23 points on those readings. Adjacent labels overlap. [Weights](../adverse_impact/weights.json) · [Protocol](../adverse_impact/protocol.md)
2. **Failed recovery**, frozen at 6537faa after seeing that failure. Sample the start and end prices of a qualifying adverse shock. A later close halfway back arms the circuit. A full recovery cancels it. A subsequent close beyond the shock's ending price in the adverse direction emits one pulse equal to the move from the attempted recovery's peak to that close. The readout subtracts that single leg from the four-bar directional prior, then clears the event. There are no broker orders or intrabar stop-price assumptions. Volume on an adverse bar is unsigned traded volume; the close displacement supplies its direction. [Weights](weights.json) · [Protocol](protocol.md)

## Economic result

Each cell below is net USD / maximum marked drawdown USD. Each period starts at zero. The other thirteen November dates form one chronological series with November 19 omitted. Fixed mode uses the 299 original entry decisions and both circuits can only shorten original holding periods. Full mode runs raw entries whenever the strategy is free. The original reservoir's volume-based input remains part of all runs. The price control removes volume only from the new exit circuit.

### Adverse impact

| Panel | Original | Fixed volume | Fixed price | Full volume | Full price |
|---|---:|---:|---:|---:|---:|
| Sep–Oct, 20 sessions | -847.50 / 2,269.00 | -1,133.00 / 1,522.50 | -1,310.50 / 1,492.50 | -1,445.50 / 2,251.50 | -1,477.00 / 2,291.50 |
| Nov 19 | -126.50 / 1,526.50 | 167.00 / 282.00 | 113.50 / 284.00 | -304.00 / 1,062.50 | -653.50 / 1,303.00 |
| Other 13 Nov sessions | 2,239.00 / 995.00 | 831.50 / 571.00 | 766.00 / 571.00 | 9.00 / 1,166.50 | -282.50 / 1,102.50 |
| All 14 Nov sessions | 2,112.50 / 1,727.50 | 998.50 / 571.00 | 879.50 / 571.00 | -295.00 / 1,496.00 | -936.00 / 1,717.50 |

| Fixed volume vs original | Net change on original losers | Net change on original winners | Full volume same-episode added re-entries / net | Other added / net | Missed original entries / their net | Additional friction |
|---|---:|---:|---:|---:|---:|---:|
| Earlier 20 | +2,994.00 | -3,279.50 | 158 / -406.00 | 20 / -134.50 | 18 / -689.50 | 960.00 |
| Nov 19 | +462.50 | -169.00 | 11 / -452.00 | 1 / -120.50 | 1 / -564.00 | 66.00 |
| Other 13 | +2,400.00 | -3,807.50 | 73 / -851.50 | 17 / +516.00 | 14 / +775.00 | 456.00 |
| All November | +2,862.50 | -3,976.50 | 84 / -1,303.50 | 18 / +395.50 | 15 / +211.00 | 522.00 |

### Failed recovery

| Panel | Original | Fixed volume | Fixed price | Full volume | Full price |
|---|---:|---:|---:|---:|---:|
| Sep–Oct, 20 sessions | -847.50 / 2,269.00 | -427.00 / 1,746.50 | -503.00 / 1,741.00 | -877.50 / 2,057.00 | -855.00 / 2,071.50 |
| Nov 19 | -126.50 / 1,526.50 | -78.50 / 379.50 | -78.50 / 379.50 | -383.00 / 1,094.00 | -383.00 / 1,094.00 |
| Other 13 Nov sessions | 2,239.00 / 995.00 | 908.00 / 941.50 | 381.00 / 1,002.50 | 1,808.00 / 824.50 | 1,314.00 / 873.00 |
| All 14 Nov sessions | 2,112.50 / 1,727.50 | 829.50 / 941.50 | 302.50 / 1,081.00 | 1,425.00 / 1,157.00 | 931.00 / 1,338.00 |

| Fixed volume vs original | Net change on original losers | Net change on original winners | Full volume same-episode added re-entries / net | Other added / net | Missed original entries / their net | Additional friction |
|---|---:|---:|---:|---:|---:|---:|
| Earlier 20 | +854.00 | -433.50 | 26 / -721.50 | 8 / +83.50 | 8 / -82.50 | 156.00 |
| Nov 19 | +436.50 | -388.50 | 5 / -304.50 | 0 / +0.00 | 0 / +0.00 | 30.00 |
| Other 13 | +1,174.50 | -2,505.50 | 24 / +749.00 | 6 / +335.00 | 6 / +235.00 | 144.00 |
| All November | +1,611.00 | -2,894.00 | 29 / +444.50 | 6 / +335.00 | 6 / +235.00 | 174.00 |

A same-episode added re-entry follows an edited hold exit in the same direction while the entry forecast retains its sign. Missed net is what those original entries earned. Subtract that amount when reconciling the full-strategy delta. Additional friction is already included in net; fees on gross re-entries are provided in results.json. Shared-entry full deltas and gross gains versus damage within each original win/loss group are also in the two result files.

## What the second surgery changed

On November 19 the 10:45 long exited at 10:49 and lost $127.50 instead of $564. This was its largest paired improvement. The original and edited holds were 77 and 4 minutes. Five same-episode re-entries on that date cost $304.50 net and the full day closed at −$383. The most damaged winner was a November 10 short opened at 10:18. The edited exit at 10:33 realized −$6 instead of the original +$662 at 12:27. The chart buttons select these exact entries and mark both exits.

For the first neuron the largest improvement was a November 17 short (+$19 to +$488) and the most damaged winner was the same November 10 short (+$662 to −$12). Both charts keep the original forecast on screen alongside the experimental position-relative hold line.

On identical November entries the second volume exit beat its price-only counterpart by $527. In full replay the advantage was $494, with 122 trades for both. The earlier 20-day full comparison favored price-only by $22.50. The full-volume November net was 67.5% of the original, with marked drawdown dropping from $1,727.50 to $1,157. Relative filters improved this historical November comparison; there is no independent evidence of generalization. The second neuron averaged −33.16 points on its 64 nonpositive November original-cohort readings, where continuing for the truncated horizon averaged +0.68 points. That magnitude and even the average sign fail as a calibrated prediction. [Outcome diagnostics](results/diagnostics.json)

## Review and reproduce

Open either HTML chart locally. Use the mode selector for the original trades, identical-entry experiments, and full-strategy replays. The purple hold line appears while a position is open. The “Largest improvement” and “Most damaged winner” buttons use the fixed-entry volume experiment across all 34 dates. Both charts and this handoff are in hold-exit-charts.zip.

From experiments/reservoir_lab/adverse_impact, run the commands below using the hash-verified source layout from the original workbench. The study checks every original fill, every fixed entry and side, exit timing relative to the original, close-mark accounting, and trade attribution. All weights were committed before their respective first market replays. No coefficient or threshold sweep was run.

```sh
python -m pytest -q test_circuit.py test_simulator.py ../failed_recovery/test_recovery.py
python study.py /path/to/scratch /tmp/impact
python diagnostics.py /path/to/scratch /tmp/impact
python study.py /path/to/scratch /tmp/recovery --model failed_recovery
python diagnostics.py /path/to/scratch /tmp/recovery
```

Available sources were inspected for synchronized bid and ask data. The intraday archive has timestamp, OHLC and volume; the November chart captures and private transfer archives also contain minute bars. No bid/ask tape was available for these dates. Nine-second execution remains unmeasured. Results reflect simulated next-open fills only.
