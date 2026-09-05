# Experiment design

## Upstream baseline

SkillEvolBench is pinned to `9e3daa339987c3cfa624121e1be442593a53d43c`. Its official conditions perform their own acquisition. The wrapper supports `no_skill`, `raw_trajectory_rag`, and `selfgen_experience_always`. Running those conditions independently does not isolate representation changes applied to the same experience. The published snapshot does not contain evidence of a completed full official three-condition experiment.

## Added same-source comparison

The current `e1ls3_trainingfree_v1` experiment uses one verified `E1-LS3-T1` acquisition trajectory. Its normalized event stream retains semantic order/content and removes transport/accounting metadata. A single procedural `SKILL.md` is authored from this common packet and frozen. Both artifact forms use the same `Prior Experience Artifact` prompt wrapper. All three branches execute with `no_skill`, with native retrieval disabled.

| Condition | Input to target Agent |
|---|---|
| No Artifact | No prior experience artifact |
| Episodic | Full normalized common source event stream |
| Procedural | One frozen abstraction of that common stream |

The matrix is 3 targets × 3 conditions × 3 repetitions = 27 branches. Targets are E1-LS3-T4/T5/T6. Recorded source and target model labels are `claude-sonnet-5`, using the ANU gateway and Claude Code. The model label records the configured gateway identity; it is not an independently verified model-weights identifier.

Nine normalized inputs have the same SHA-256. Nine procedural copies have the same SHA-256. The publication deduplicates them and preserves the actual shared input and skill bytes. JSON metadata replaces the machine's runtime prefix with `${RUNTIME_ROOT}`. The per-group evidence packets and membership manifest retain the original artifact hashes.

## Measurement and limits

- A/B/C are matched repetitions without a controllable generation seed, not nine independent sources or seeded-identical samples.
- Functional checks, task-declared contracts and implementation-form checks are reported separately. Construct classification is an analysis layer with judgment calls, not a new ground-truth task label.
- T4 is a candidate case requiring explanation. Its stronger aggregate difference is largely contractual.
- T5 is at the ceiling; T6 has functional ceiling and non-functional score differences.
- One source and one frozen abstraction do not establish general representation superiority, sampling stability, or the causal mechanism of information loss.
- Costs are token-derived estimates for target branches only. Historical provider pricing is a recorded snapshot, not a quote for a future run.

The [findings](../paired_repetition_findings.md) state what the evidence can and cannot support. The [historical LS1 pilots](pilots/) are separate diagnostics and are not pooled into the LS3 means.
