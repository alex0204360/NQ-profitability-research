# Four-minute NQ opportunity selection

This study asks whether explicit evidence of price acceptance or rejection at a recent range boundary can pay the cost of one NQ round trip. All parameters were programmed by hand. Git history records each design before its first performance evaluation. The original impulse experiment is preserved in the sibling directory.

## What motivated the experiment

Among 707 v06 trades, the 226 that passed the v08 gate returned $58.69 on average. The 481 it rejected lost $12.81 on average. The retained group had a higher median normalized impulse (3.16 versus 2.46), so the difference cannot isolate overhead inventory. Within v08, winner and loser impulse medians were 3.13 and 3.16. Median pre-entry range was 6.05 points for the five best trades and 13.41 for the five worst. Five observations per tail give little basis for a volatility cutoff. First-minute returns after entry contain outcome information and were excluded from all predictors. The pinned paired interval for v08 minus the dispersion control v09 included zero.

## Reproduction and interpretation

From this directory run `OPENBLAS_NUM_THREADS=1 python evaluate.py /path/to/Dataset_NQ_1min_2022_2025.csv` with NumPy and pandas. The inherited replay verifies the archive member's SHA-256 and filters price calculations to pre-2025 weekday daytime sessions. The evaluation copies the inherited replay into a temporary directory before executing it. Each strategy trades one contract at the next bar open, can hold one position, and uses the same timed four-minute exit and missing-bar logic. The base round trip costs $14.50. Stress adds one tick at each fill. Dollar drawdown uses closed trades. Daily comparisons include zero-trade dates and use paired five-session circular block resampling. Intervals are descriptive and do not adjust for sequential design decisions.

No independent price series was scored. Historical exposure elsewhere in the repository precludes assuming that 2025 is pristine. Future testing would require documented prior non-exposure, contract rolls, session calendar, verified timestamp semantics and an execution specification frozen before scoring.

[Prior experiment](../impulse_context/README.md) · [Direct weight programming inspiration](https://rikiyat.github.io/blog/weight-space-programming/) · [Network equations](brain.py) · [Design decisions](protocol.md)

## Exploratory results

| Model | Trades | Net USD | Mean net per trade | Stressed net USD | Closed drawdown USD |
|---|---:|---:|---:|---:|---:|
| v06 | 707 | 7,103.50 | 10.05 | 33.50 | 8,172.00 |
| v08 | 245 | 14,522.50 | 59.28 | 12,072.50 | 4,087.00 |
| v09 | 189 | 7,704.50 | 40.76 | 5,814.50 | 5,942.50 |
| cash | 0 | 0.00 | — | 0.00 | 0.00 |
| periodic | 47,482 | -634,464.00 | -13.36 | -1,109,284.00 | 639,246.00 |
| two_up | 23,781 | -330,474.50 | -13.90 | -568,284.50 | 339,392.00 |
| auction | 3,553 | -19,363.50 | -5.45 | -54,893.50 | 30,328.00 |
| auction_compression | 1,554 | -9,828.00 | -6.32 | -25,368.00 | 19,258.50 |
| rejection | 672 | -18,234.00 | -27.13 | -24,954.00 | 18,891.50 |
| cost_aware_momentum | 41,890 | -584,710.00 | -13.96 | -1,003,610.00 | 591,966.00 |

The first design captured $9.05 gross per trade against $14.50 costs. Compression reduced turnover, but gross fell to $8.18. The replacement detector lost $12.63 per trade before costs and lost on both sides. Its average daily difference versus cash was −$35.07 (paired block interval −$63.25 to −$7.47). Retire all three for execution and retain cash. Reversing a losing forecast after observing the result would be a new exploratory hypothesis. The full output includes side and annual attribution. All five active inherited benchmarks reproduced their pinned net exactly. Prefix-invariance and sign-reflection checks on synthetic bars passed for all three designs.
