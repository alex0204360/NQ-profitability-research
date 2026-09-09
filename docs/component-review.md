# Component review before market evaluation

Reviewer: `v2_integration_review`. No market data read; source review only.

Findings and resolutions:

1. Missing benchmark executions could distort paired advantage. Both candidate
   and benchmark must now have zero censored attempts for qualification.
2. Serving computed model hashes without comparing them to expected values.
   Library entries now bind model/encoder hashes and identities; edited or swapped
   files fail load. Regression tests first reproduced the missing rejection.
3. One terminal candidate failure could abort remaining survivors. Each failed
   frozen candidate now remains in the Holm family at p=1 while others continue.
   Shared failures produce a failed terminal artifact with no qualifications.
4. Freeze initially bound an input manifest without rechecking the input bytes.
   Training and schedule files are now included in the frozen artifact hashes;
   holdout file identity is recorded by mechanical digest without price decoding.

The reviewer found no additional critical error in the 45-minute execution timing,
chronological fitting, paired ratio bootstrap, maximum-p aggregation, or Holm
correction. Root implemented the fixes and validates the regression suite. This
review establishes implementation checks, not profitability.

Component authors: `v2_execution` (execution engine), `v2_policies` (encoders and
payoff tables), `v2_inference` (statistics), `v2_matcher` (serving), and `root`
(inherited causal features, replay, orchestration and integration). Usage limits
interrupted some agent handoffs; root recovered their saved files and verified them.
