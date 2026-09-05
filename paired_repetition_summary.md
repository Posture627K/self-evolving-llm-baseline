# Three-Pair Training-Free Repetition Summary

- Completed branch runs: 27 / 27
- Source experience: `E1-LS3-T1`
- Targets: `E1-LS3-T4`, `E1-LS3-T5`, `E1-LS3-T6`
- Conditions: No Artifact, Episodic, Procedural
- One frozen procedural abstraction is reused across all repetitions.
- A/B/C are matched repetitions; the Claude API does not expose a controllable generation seed.
- Agent exceptions: 0; unmatched failed checks: 0.

## Aggregate normalized score

| Target | Condition | n | Mean | SD | Min | Max |
|---|---|---:|---:|---:|---:|---:|
| `E1-LS3-T4` | episodic | 3 | 0.938 | 0.108 | 0.812 | 1.000 |
| `E1-LS3-T4` | no_artifact | 3 | 0.417 | 0.036 | 0.375 | 0.438 |
| `E1-LS3-T4` | procedural | 3 | 0.562 | 0.217 | 0.438 | 0.812 |
| `E1-LS3-T5` | episodic | 3 | 1.000 | 0.000 | 1.000 | 1.000 |
| `E1-LS3-T5` | no_artifact | 3 | 1.000 | 0.000 | 1.000 | 1.000 |
| `E1-LS3-T5` | procedural | 3 | 1.000 | 0.000 | 1.000 | 1.000 |
| `E1-LS3-T6` | episodic | 3 | 0.979 | 0.036 | 0.938 | 1.000 |
| `E1-LS3-T6` | no_artifact | 3 | 0.938 | 0.000 | 0.938 | 0.938 |
| `E1-LS3-T6` | procedural | 3 | 0.979 | 0.036 | 0.938 | 1.000 |

## Matched deltas

| Target | Rep | Episodic-No | Procedural-No | Procedural-Episodic |
|---|---|---:|---:|---:|
| `E1-LS3-T4` | A | 0.375 | 0.375 | 0.000 |
| `E1-LS3-T4` | B | 0.625 | 0.062 | -0.562 |
| `E1-LS3-T4` | C | 0.562 | 0.000 | -0.562 |
| `E1-LS3-T5` | A | 0.000 | 0.000 | 0.000 |
| `E1-LS3-T5` | B | 0.000 | 0.000 | 0.000 |
| `E1-LS3-T5` | C | 0.000 | 0.000 | 0.000 |
| `E1-LS3-T6` | A | 0.062 | 0.062 | 0.000 |
| `E1-LS3-T6` | B | 0.000 | 0.000 | 0.000 |
| `E1-LS3-T6` | C | 0.062 | 0.062 | 0.000 |

## Construct-resolved mean pass rate

| Target | Condition | Functional | Contract | Form |
|---|---|---:|---:|---:|
| `E1-LS3-T4` | no_artifact | 0.810 | 0.000 | - |
| `E1-LS3-T4` | episodic | 0.952 | 0.889 | - |
| `E1-LS3-T4` | procedural | 0.857 | 0.222 | - |
| `E1-LS3-T5` | no_artifact | 1.000 | 1.000 | - |
| `E1-LS3-T5` | episodic | 1.000 | 1.000 | - |
| `E1-LS3-T5` | procedural | 1.000 | 1.000 | - |
| `E1-LS3-T6` | no_artifact | 1.000 | 0.800 | - |
| `E1-LS3-T6` | episodic | 1.000 | 0.933 | - |
| `E1-LS3-T6` | procedural | 1.000 | 0.933 | - |

## Functional matched deltas

| Target | Rep | Episodic-No | Procedural-No | Procedural-Episodic |
|---|---|---:|---:|---:|
| `E1-LS3-T4` | A | 0.000 | 0.000 | 0.000 |
| `E1-LS3-T4` | B | 0.286 | 0.143 | -0.143 |
| `E1-LS3-T4` | C | 0.143 | 0.000 | -0.143 |
| `E1-LS3-T5` | A | 0.000 | 0.000 | 0.000 |
| `E1-LS3-T5` | B | 0.000 | 0.000 | 0.000 |
| `E1-LS3-T5` | C | 0.000 | 0.000 | 0.000 |
| `E1-LS3-T6` | A | 0.000 | 0.000 | 0.000 |
| `E1-LS3-T6` | B | 0.000 | 0.000 | 0.000 |
| `E1-LS3-T6` | C | 0.000 | 0.000 | 0.000 |

## Interpretation rule

Functional, contract, and form failures are retained separately in the JSON ledger. A difference in overall score alone is not treated as functional transfer evidence.
