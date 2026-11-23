# MNQ reservoir · local research kit

Open **MNQ-trade-chart.html** in a browser. It contains candles and all 299 frozen reservoir trades across the 34 previously scored sessions. Choose a date, inspect an entry, and switch to Guarded to compare that day's proposed $500 lockout. The chart and embedded data work offline. All displayed prices and returns are simulated fills. All clock times are New York time.

## The neuron

The failed predecessor compared volume before a move to volume after a move. It earned $0.24 gross per trade against even the $3 base friction. Its volume memory was nonpositive on 583 of 695 entries. A quiet period and a price fall could accidentally look like accumulated buying opportunity.

The replacement gives activity a finite memory. For each completed minute, let e be log-volume surprise against its prior exponential average, clipped to one doubling or halving. Let q be close-to-close displacement divided by the prior average bar range, clipped to ±2. The background averages use 1/32 updates. Start each contiguous session segment with empty stock B and directional forecast F. Each bar computes the following using the old B and F.

```text
charge   = max(e − |q|, 0)
u        = clip(q, −1, 1)
release  = B × u
B_next   = (7/8) × B × (1 − |u|) + charge
F_next   = (7/8) × (F + release)
score    = prior_range_in_points × F_next
```

A bar with e=1 and q=0 puts one unit into an empty reservoir. If the next bar moves half a range up with zero new charge, it releases +0.5. The new stock and forecast are both 0.4375. At an eight-point prior range, that gives a +3.5-point score. This illustrative input would clear the +1.5-point entry hurdle after warmup. The sign of the evidence determines direction. Loss of that sign triggers an exit. There are no fitted coefficients or predetermined holding periods. The state variables describe price and volume. Interpreting them as buying or selling by a particular participant would go beyond the observations.

**Files for a new chat.** The ZIP root contains brain.py, the two exact weight files area.json and reservoir.json, and execution.py. The reservoir relies on the normalization settings in area.json. Those files reproduce the original circuit, and workbench/session.py verifies their hashes. Include this handoff, both weight files and brain.py when passing the model to another researcher. Create a separate candidate file and run it on a discovery copy when changing the math. The registered reference remains available for comparison. [Original weights and evidence](https://github.com/alex0204360/NQ-profitability-research/tree/03ec0a10541fc59fb88f3f137a354c81e911f75f/experiments/path_order)

## Guard experiment and risk

The baseline already closes at the 15:55 open. No position is opened at or after that time. A missing price at the cutoff can delay the modeled liquidation to the next observed open. The cutoff applies to this U.S. daytime strategy. MNQ also trades outside these hours.

The candidate guard measures one-contract marked P&L relative to the beginning of each day. At the first completed minute at or below −$500 it requests a next-open liquidation and suppresses further entries. That amount was set before the comparison as one third of the prior $1,500 drawdown budget. It can overshoot. It is a paper overlay for comparison.

| Exposed panel | Base net | Guarded net | Base marked drawdown | Guarded marked drawdown |
|---|---:|---:|---:|---:|
| Sep 14–Oct 9 · 20 sessions | −$847.50 | −$918.00 | $2,269.00 | $2,339.50 |
| Nov 3–20 · 14 sessions | +$2,112.50 | +$1,687.00 | $1,727.50 | $1,510.00 |

The guard retained 79.9% of November net after $6 modeled friction per trade. It fired on two November dates, and the worst closing day worsened from −$493.50 to −$530.50. The baseline's largest November drawdown ran from the November 17 morning peak to the November 19 midday trough. The guarded peak also occurred on November 17 and its trough on November 20. A daily reset misses cumulative multiday giveback. In discovery the guard worsened both P&L and drawdown. Neither variant cleared the historical $1,500 budget on either panel. Review November 19 in the chart to see the guard flatten a losing position and miss the baseline's later recovery.

## Run one completed day

In the extracted kit root, use Python 3.12 and install the pinned dependencies with `python -m pip install -r requirements.txt`. The repository copy places this same root at experiments/path_order. For a verified upload, the input CSV columns are timestamp_utc,open,high,low,close,volume,contract. Use individual unadjusted MNQZ26 one-minute bars, timezone-qualified timestamps, and specify whether timestamps mark the start or end of the minute. Five-minute candles cannot reproduce the original decisions. If the contract column is absent, the caller's contract designation is recorded. Use full regular daytime sessions for this runner.

```sh
python workbench/paper_day.py --date 2026-11-23 --contract MNQZ26 --bars bars.csv --stamp start --out nov23-upload
```

To request the same vendor's dated-contract chart after the close, use the following command. Exact contract mapping and minute labels remain vendor assumptions on this route. It archives the raw response and checksum. If data are incomplete at publication, rerun after the final bar is available.

```sh
python workbench/paper_day.py --date 2026-11-23 --contract MNQZ26 --fetch --out nov23-yahoo
```

The output includes trades.html, a scorecard, the two trade ledgers, and minute-by-minute activations and equity. A signal on the bar labeled 10:14 becomes available at 10:15. The simulation uses the 10:15 open as the historical price proxy. To examine sub-ten-second execution, supply a timestamped best bid/offer CSV for the same contract and day using timestamp_utc,bid,ask,contract and append `--quotes quotes.csv --latency-seconds 9` to a new run. Quotes must be chronological, uniquely timestamped, on the tick grid, and at most one second old at the modeled arrival. Signal orders use the observed bid for sales and ask for buys; scheduled flatten assumes arrival at 15:55 exactly. Repricing charges $2 fees round trip and reports one extra adverse tick per side as a sensitivity. Coverage is explicit. A quote without confirmed size and a fill report cannot establish the price a real order obtained. Both sets of paper instructions receive a separate quote audit. The guard still locks using its registered minute-mark reference equity. A guard triggered by actual brokerage P&L would be a different experiment.

**Today's question.** Did both frozen variants behave as expected, how much did the base signal move between decision and arrival, and did either variant violate the risk budget? Review the day once; record it as exposed for any new version. Keep the day's outcome separate from the cumulative prospective study. As of this pre-market handoff, November 23 is unscored.
