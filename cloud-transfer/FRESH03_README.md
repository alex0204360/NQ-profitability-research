# November MNQ upload diagnostic

The uploaded `MNQ_Yahoo_1m_2026-10-28_to_2026-11-02_161500_327580.csv` was evaluated in a separately registered, upload-only diagnostic. Its SHA-256 is `9639ef1fb72918ae6432fcbcf5e46ae6bbdc3506dd6279e8dd295417889aa654`. The raw CSV, normalized bars, forecasts, trade journals, event journals and model bundles remain private in `/workspace`; none is committed here.

After the original cloud transfer and campaign 01 overlay are restored, copy `cloud-transfer/fresh03-overlay/` into `/workspace/mnq-oracle-code/`, preserving the `docs/` and `tools/` paths. Transfer the exact uploaded CSV separately to a private workspace path. From `/workspace/mnq-oracle-code`, use a **new empty** output directory:

```sh
python -c 'from tools.cloud_fresh03 import run; run(source="/workspace/PRIVATE_UPLOAD.csv", out="/workspace/mnq-private-results/NEW_EMPTY_RUN")'
```

The script verifies the registered input SHA-256 and both frozen model manifests before producing 18 fixed evaluations. It refuses to overwrite a previous run. The completed local runs are `cloud_fresh03` and `cloud_fresh03_lineage`; the latter used the baseline model's recorded numerical package versions. All 18 replay metric dictionaries matched exactly between the two environments. `cloud-transfer/fresh03-summary/` contains the verified aggregate HTML and knowledge JSON. The narrative, source caveats and verdict are in `fresh03-overlay/docs/CLOUD_FRESH03_RESULT.md`.

There are only two observed sessions, two source-overlap conflicts, and no independently verified contract or roll metadata. This is a retrospective diagnostic, not fresh confirmation or real-time paper trading. No policy was selected; 2025 remains sealed.
