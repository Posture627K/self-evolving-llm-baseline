# Publication validation — 2026-09-05

These checks were run during preparation of this repository. They validate the exported evidence and engineering changes; they are not new model experiments.

| Check | Result |
|---|---|
| Published LS3 snapshot | PASS: 27 unique branches, 9 matched groups, shared source/skill hashes, scores, sample SD and target cost total |
| Evidence checksums | PASS: 226 files, including exported branch/verifier records and shared artifacts |
| Independent aggregation from exported paired summaries | PASS: branch count, aggregate statistics, paired deltas, construct statistics and integrity fields equal the frozen published summary |
| Four-file upstream patch | PASS: reconstructed in a clean local clone at the pinned commit; all four normalized file hashes matched |
| Existing engineering regression suite on that reconstruction | PASS: 8 tests |
| Python runtime root override | PASS, including a path containing spaces |
| Shell syntax | PASS: 13 scripts |
| Paired-run cost guard | PASS: missing explicit confirmation/source path exits before running targets |
| Parameterized WSL smoke dry-run | PASS: explicitly selected E1-LS3-T1; no API or Docker task executed |
| Main README and current documentation links | PASS |
| Publication credential scan | PASS: 281 staged files, zero findings; final staged bytes are scanned again immediately before commit/push |

The earlier source workspace review also passed static configuration validation (15 baseline configs, 2 strategies), task-asset validation (30 families / 180 tasks), and `pip check` in the actual WSL runtime. Windows asset validation did not verify Docker/Harbor availability; the Ubuntu runtime is the real execution environment.

## Limits

- No paid model inference was performed during publication preparation.
- Full fresh package installation and a new Docker image build were not rerun. The installer uses the recorded package versions and pinned source commits; later availability and installer behavior may differ.
- No full official three-condition benchmark completion is claimed.
- `security_check.py` checks staged bytes for the supplied local credential values, common token/private-key formats, forbidden paths, and populated credential fields. It prints only filenames and finding types. It does not certify future unreviewed uploads.
- Original run data was not overwritten. Publication JSON metadata replaces the old machine root with `${RUNTIME_ROOT}`; shared source input and skill bytes retain their original hashes.
