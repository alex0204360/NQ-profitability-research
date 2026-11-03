# Fresh03: November 2 upload-only diagnostic

**No selection and not ready.** The exact uploaded CSV has SHA-256 `9639ef1fb72918ae6432fcbcf5e46ae6bbdc3506dd6279e8dd295417889aa654`. The plan in `CLOUD_FRESH03_PLAN.json` was saved before any model predictions or profit evaluation. The transfer had 5,041 ordered, timezone-offset, minute-aligned 2026 bars with finite tick-aligned OHLCV. Of 3,226 bars overlapping the previous upload, two conflict, at October 28 04:09 UTC and October 30 12:29 UTC. The new diagnostic used the uploaded file alone and did not splice sources. The user knows only that the file came from Yahoo; exact contract, roll, interval-start convention and any correction notice remain unknown.

Evaluation covered October 30 through November 2, 2026, ending before the final ten-bar horizon could be truncated. Only **two observed sessions** were available. The frozen $8 reference and two previously rejected dual-delay students were evaluated with the same causal-v2 next-open replay, ten-bar exit, three cost assumptions and zero/one-bar signal delays. No fitting, parameter changes or policy selection occurred.

| Policy | Immediate stress net | Delayed stress net | Immediate extreme net | Immediate stress trades | Immediate bar-close drawdown |
| --- | ---: | ---: | ---: | ---: | ---: |
| Unchanged $8 gate | +$429.00 | +$259.50 | +$317.00 | 28 | $271.00 |
| Ridge dual-delay | -$930.00 | -$1,059.00 | -$1,042.00 | 28 | $969.00 |
| Extra trees dual-delay | +$1,091.00 | -$1,342.00 | +$839.00 | 63 | $1,082.00 |

The $8 gate's two-session positive result does not erase its earlier $1,250 delayed-stress loss, negative extreme result, or negative development bootstrap bound. The tree student's immediate profit fails under a one-bar delay and its two-session bootstrap lower stress expectancy is -$24.77 per trade. Ridge lost under every registered stress scenario. The sample misses the registered ten-active-session support screen. These models remain rejected or baseline-only. The user specified no maximum drawdown, so the goal's risk-limit qualification is still open.

The first `cloud_fresh03` run used scikit-learn 1.8.0 for all models; the unchanged baseline was serialized under 1.6.1. Its warning was investigated by rerunning in an isolated environment with the baseline's recorded NumPy 2.5.4, pandas 3.0.1, SciPy 1.18.1, scikit-learn 1.6.1, joblib 1.6.0 and threadpoolctl 3.7.0. That environment warned when loading the students built under 1.8.0. **Every replay metric across all 18 cells matched exactly between the two runs.** The canonical aggregate is `cloud_fresh03_lineage`; both immutable runs and their hashes are retained. This agreement tests observed output stability, but it does not certify cross-version portability in general.

No 2025 data was opened. No broker orders or prospective paper decisions were made. A source-audited feed with explicit contract and roll metadata is still needed. New models must be registered before evaluating a later untouched period; this small upload cannot rescue a rejected model by retrospective selection.
