# Matured-label hold-value memory

All dates were exposed. Each source and fill schedule has a separate memory.
A label enters memory strictly after its original exit. The decision uses only the first
discretionary close. All original entries count toward fixed-ledger net.

| Source | Fill | Head | MSE (pts²) | MAE (pts) | Mean (pts) | Bias (pts) | Spearman | Changed fills | Δ USD | Net $3 | Net $6 | Net $9 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| discovery40 | Next open | zero | 4,782.78 | 41.08 | 0.00 | -0.29 | — | 0 | +0.00 | 1,634.50 | 452.50 | -729.50 |
| discovery40 | Next open | raw_volume | 5,760.27 | 49.70 | 30.23 | 29.94 | 0.073 | 0 | +0.00 | 1,634.50 | 452.50 | -729.50 |
| discovery40 | Next open | constant | 4,887.74 | 41.09 | -4.73 | -5.02 | -0.083 | 217 | -188.50 | 1,446.00 | 264.00 | -918.00 |
| discovery40 | Next open | price | 4,894.45 | 41.11 | -4.82 | -5.10 | -0.082 | 217 | -188.50 | 1,446.00 | 264.00 | -918.00 |
| discovery40 | Next open | interaction | 4,902.37 | 41.13 | -4.93 | -5.22 | -0.086 | 217 | -188.50 | 1,446.00 | 264.00 | -918.00 |
| discovery40 | Extra minute | zero | 5,628.97 | 45.19 | 0.00 | 1.54 | — | 0 | +0.00 | 759.50 | -323.50 | -1,406.50 |
| discovery40 | Extra minute | raw_volume | 7,959.66 | 57.76 | 34.38 | 35.92 | -0.021 | 0 | +0.00 | 759.50 | -323.50 | -1,406.50 |
| discovery40 | Extra minute | constant | 5,704.26 | 45.41 | -0.19 | 1.36 | -0.082 | 89 | -537.50 | 222.00 | -861.00 | -1,944.00 |
| discovery40 | Extra minute | price | 5,709.93 | 45.49 | -0.27 | 1.28 | -0.097 | 89 | -1,087.00 | -327.50 | -1,410.50 | -2,493.50 |
| discovery40 | Extra minute | interaction | 5,713.90 | 45.52 | -0.42 | 1.12 | -0.099 | 95 | -1,312.50 | -553.00 | -1,636.00 | -2,719.00 |
| external60 | Next open | zero | 2,686.21 | 35.66 | 0.00 | 0.25 | — | 0 | +0.00 | -2,198.00 | -3,821.00 | -5,444.00 |
| external60 | Next open | raw_volume | 4,106.39 | 46.15 | 27.68 | 27.93 | -0.084 | 0 | +0.00 | -2,198.00 | -3,821.00 | -5,444.00 |
| external60 | Next open | constant | 2,693.46 | 35.42 | -2.79 | -2.55 | 0.069 | 226 | -88.50 | -2,286.50 | -3,909.50 | -5,532.50 |
| external60 | Next open | price | 2,701.77 | 35.49 | -2.67 | -2.43 | 0.062 | 226 | +66.00 | -2,132.00 | -3,755.00 | -5,378.00 |
| external60 | Next open | interaction | 2,703.46 | 35.52 | -2.56 | -2.31 | 0.055 | 222 | +28.00 | -2,170.00 | -3,793.00 | -5,416.00 |
| external60 | Extra minute | zero | 2,418.59 | 33.62 | 0.00 | -0.13 | — | 0 | +0.00 | -1,207.50 | -2,734.50 | -4,261.50 |
| external60 | Extra minute | raw_volume | 3,450.61 | 42.94 | 27.04 | 26.91 | 0.028 | 0 | +0.00 | -1,207.50 | -2,734.50 | -4,261.50 |
| external60 | Extra minute | constant | 2,432.07 | 33.71 | -0.66 | -0.79 | -0.004 | 156 | -78.50 | -1,286.00 | -2,813.00 | -4,340.00 |
| external60 | Extra minute | price | 2,432.33 | 33.68 | -0.26 | -0.40 | -0.012 | 139 | -155.00 | -1,362.50 | -2,889.50 | -4,416.50 |
| external60 | Extra minute | interaction | 2,426.80 | 33.60 | 0.17 | 0.03 | 0.007 | 124 | +16.00 | -1,191.50 | -2,718.50 | -4,245.50 |

Differences below are interaction MSE minus control MSE. The paired five-session
circular block bootstrap uses 10,000 draws and seed 2711. It resamples whole sessions,
including those with no labels, and divides resampled squared-error totals by resampled trade counts.

| Source | Fill | Control | Δ MSE (pts²) | Paired 95% interval |
|---|---|---|---:|---:|
| discovery40 | Next open | zero | +119.59 | [-30.28, +305.12] |
| discovery40 | Next open | constant | +14.63 | [+4.22, +29.95] |
| discovery40 | Next open | price | +7.92 | [+0.60, +19.51] |
| discovery40 | Extra minute | zero | +84.93 | [-10.91, +213.30] |
| discovery40 | Extra minute | constant | +9.64 | [-4.61, +24.92] |
| discovery40 | Extra minute | price | +3.97 | [-2.43, +11.38] |
| external60 | Next open | zero | +17.24 | [-36.56, +72.54] |
| external60 | Next open | constant | +10.00 | [-2.85, +23.81] |
| external60 | Next open | price | +1.69 | [-5.93, +9.50] |
| external60 | Extra minute | zero | +8.21 | [-28.41, +42.55] |
| external60 | Extra minute | constant | -5.27 | [-36.35, +22.58] |
| external60 | Extra minute | price | -5.53 | [-20.85, +7.06] |
