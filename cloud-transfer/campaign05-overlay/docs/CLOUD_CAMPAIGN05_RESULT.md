# Campaign 05: ten search agents, ten oracle testers, 100 variants

**The student still lost money.** Ten search agents fixed ten variants each before any new scoring. Ten different testers audited and scored all 100 against an eight-action hindsight teacher: long or short, held for 3, 5, 10, or 20 bars, with each action valued at the worse of immediate and one-bar-delayed next-open fills after a $6 stressed round trip. All losing alternatives remained in the training data. The oracle's future prices were labels and tester evidence only; the students received completed-bar features. The dashboard at `/workspace/outputs/mnq_oracle_teaching_dashboard.html` and full aggregate ledger show every variant and its three chronological fold scores.

Twenty-four variants passed the internal rank screen. The fixed global winner was search agent 06, variant 00, a nine-feature Ridge model with mean action-value rank correlation **0.0790** over the three purged selection folds (+0.1280, +0.0417, +0.0673). It was then fitted on 15,024 mature pre-October 1 rows and replayed exactly once on October 1–6, an already opened internal development holdout. Holdout rank correlation fell to **0.0463**. The student signaled on 7.2% of mature ready opportunities and selected the hindsight oracle's exact action on only 6.6%. The hindsight oracle found some positive action on 96.0% of opportunities because it knew the subsequent path; that figure is not a tradable success rate.

| One-contract holdout replay | Immediate fill | One-bar delayed fill |
| --- | ---: | ---: |
| Filled trades | 45 | 45 |
| Base net | -$294.50 | -$345.00 |
| Stressed net | **-$384.50** | **-$435.00** |
| Extreme net | -$564.50 | -$615.00 |
| Stressed bar-close max drawdown | $790.50 | $826.50 |
| Stressed session-bootstrap lower expectancy | -$17.00/trade | -$15.76/trade |
| Gap exits / their stressed net | 2 / -$1.00 | 3 / -$17.00 |

The result fails the original 50-trade and ten-active-session minimums (45 trades, five active sessions), as well as profitability and bootstrap gates. Gap-exit gains did not create this loss; the model lost under all three cost settings. The unchanged no-trade control earned $0. This holdout is not independent confirmation, and the exact MNQ contract/roll/timestamp identity is still unverified. The selected nine-feature set also includes causal OHLCV values beyond the current 18-feature paper API, so a matching live adapter does not yet exist. No candidate was promoted to paper execution or live trading.

The local private dashboard at `/workspace/outputs/mnq_oracle_teaching_dashboard_PRIVATE.html` includes an exact, first-signal Ridge breakdown. For that signal, the model predicted **+$6.91** stressed net for a 20-bar long. After the exit matured, the same oracle action's realized stressed net was **-$85.00**. The dashboard lists all eight predicted and realized action values plus every feature's additive contribution to the chosen forecast. This is a reproducible explanation of model arithmetic, not hidden thoughts or a causal explanation of the market.

Future observations cannot be known on a live chart. A student can instead estimate a distribution of future paths from information available at decision time; it must show that the resulting action values are calibrated, stable across time, and profitable after execution costs. This experiment shows that the present 2026 Yahoo minute bars and feature sets have not met that standard. A next attempt needs contract-identified source data, matching historical/live feature construction, an append-only post-freeze paper cohort, and a finite risk budget before any order path. Raw 2025 remained sealed; no broker was connected and no orders were submitted.
