# MNQ campaign 03: frozen entries, causal bracket exit

The registered one-rule comparison keeps the $8 entry model and signal unchanged. It compares the existing `time10` exit with the existing causal-v2 one-ATR stop, 1.5-ATR target and 30-bar cap on two upload-only development windows. The complete local results are in `/workspace/mnq-private-results/cloud_campaign03`, with frozen protocol, decision/trade/event journals and a SHA-256 manifest. Private market data and journals are not committed to Git.

After restoring the original transfer and prior overlays, copy `cloud-transfer/campaign03-overlay/` into `/workspace/mnq-oracle-code/`, preserving paths. Reproduce in a new empty result directory with the baseline model's recorded numerical environment:

```sh
python -c 'from tools.cloud_campaign03 import run; run("/workspace/mnq-private-results/NEW_EMPTY_RUN")'
```

The script verifies frozen input/model artifacts and reproduces the original $8 fixed-ten-bar control before interpreting the alternative exit. Its registered plan and verdict are in `campaign03-overlay/docs/`. Aggregate HTML and JSON are in `campaign03-summary/`. The bracket exit lost more than the control under stressed immediate and delayed fills on the 14-session window and was rejected. No production policy was selected. Raw 2025 remains sealed; no orders were submitted.
