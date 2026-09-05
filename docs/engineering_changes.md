# Upstream provenance and local engineering changes

Upstream: [AIoT-MLSys-Lab/SkillEvolBench](https://github.com/AIoT-MLSys-Lab/SkillEvolBench/tree/9e3daa339987c3cfa624121e1be442593a53d43c), commit `9e3daa339987c3cfa624121e1be442593a53d43c`.

The [manifest](../upstream/manifest.json) contains the patch checksum and expected normalized file hashes. The [patch](../upstream/SkillEvolBench.local.patch) records exactly these four files:

| File | Reason for local change |
|---|---|
| `skillevolbench/components/verifier_adapter.py` | Resolve the real Agent ATIF trajectory instead of an artifact manifest; expose token-derived cost and agent-reported cost separately for auditing |
| `skillevolbench/components/skill_author.py` | Handle provider-specific structured output, empty responses and complete single-file upsert recovery; reject truncated output rather than silently accepting an incomplete skill |
| `skillevolbench/metrics/cost.py` | Normalize model identity and calculate DeepSeek cost using the recorded cache-aware peak/off-peak pricing snapshot |
| `skillevolbench/schemas/replay.py` | Persist the extra cost/provenance fields needed to distinguish computed estimates from agent-reported cost |

These changes are engineering support for acquisition, authoring and measurement. They do not change the benchmark task/verifier source. Eight existing regression checks cover trajectory selection, cost calculation and structured-output recovery.

`bootstrap_upstream.py` verifies the upstream HEAD, checks the patch hash, applies the patch only to a clean recognized base, and validates all four resulting file hashes. It refuses to reset an unrelated or unexpectedly edited checkout. Subsequent calls on the matching patched checkout are idempotent.

## Publication-only adjustments

Execution roots now come from `BASELINE_RUNTIME_ROOT` through `runtime_paths.py` / `runtime_paths.sh`. Repetition aggregation accepts `--paired-root`. The setup script uses a pinned package-version snapshot and the fixed Harbor commit. These portability changes preserve the historical scores/artifacts; the publication work does not claim a new real-model reproduction.

Harbor is pinned to `389bd4f8ce796ef4a97de4b62675021e262c8e76` (recorded version 0.22.0). The Agent runtime build script still applies its OpenClaw compatibility adjustment only inside a temporary build context. Historical image/CLI metadata is in `runtime_versions.txt`; rebuilding upstream container installers can resolve newer components, so bitwise container reproducibility is not claimed.

## Attribution and license status

No explicit LICENSE declaration was found in the pinned upstream revision during this review. This private research snapshot retains upstream attribution and does not grant a new license over upstream files or copied verifier material. The repository provides a version reference and the necessary local diff instead of republishing complete upstream checkouts. Clarify upstream redistribution terms before turning this work into a public distribution.
