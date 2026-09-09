# Reused infrastructure

`src/nqprofit/features.py` and its feature tests are copied from
[V1 commit 731607099729bdc1e3151b767a695e5c86aea503](https://github.com/alex0204360/NQ-trading-sept/tree/731607099729bdc1e3151b767a695e5c86aea503).
Only the test import package name changes. The feature implementation has no
runtime dependency on the V1 repository. V2 code was not copied before the V2
plan was published.

The audited canonical dataset and frozen calendar are reused without new outcome
selection or undocumented cleaning. V1's reproducible acquisition remains the
pinned upstream pipeline; V2 verifies and records the prepared inputs. Dataset
files stay outside Git. The matcher package can be installed and exercised with
standard OHLCV input independently of the acquisition checkout.
