# Reproduction: two separate entry points

## A. Offline verification of the published LS3 results

Requirements: Python 3.10+ with its standard library. No upstream checkout, model key, Docker, package installation, or network request is required.

From the repository root:

```powershell
# Windows PowerShell
.\verify_offline.ps1
```

```bash
# Linux / Ubuntu WSL
bash ./verify_offline.sh
```

Both run `verify_snapshot.py`. It checks the complete 27-branch matrix, unique target/repetition/condition membership, shared source and skill hashes, raw branch scores against the published rows, the absence of Agent exceptions, recorded model labels, means/sample SD, target cost total and evidence-file checksums.

To independently regenerate the analysis from the nine published paired summaries, keep new output separate from the frozen report:

```bash
mkdir -p /tmp/baseline-analysis
python3 -B analyze_paired_repetitions.py \
  --paired-root results/paired \
  --experiment-prefix e1ls3_trainingfree_v1 \
  --json-output /tmp/baseline-analysis/summary.json \
  --md-output /tmp/baseline-analysis/summary.md
```

This aggregation is also offline. The snapshot hashes establish file consistency; they are not a signature from an external auditor. `trial_status.json` is a selected-field export from Harbor, with complete runtime environment/configuration fields excluded. Original normalized source input and frozen `SKILL.md` are preserved byte-for-byte.

## B. Install and run new model experiments

Requirements: Ubuntu 24.04 / Ubuntu WSL2, Git, Python 3.12 with the `venv` module, Docker Engine and access to the selected model provider. Installation downloads packages and upstream source. Real model experiments incur API usage.

### 1. Choose a runtime location and install pinned Python dependencies

Run in Ubuntu / WSL from this repository root:

```bash
export BASELINE_RUNTIME_ROOT="$HOME/workspaces/self-evolving-llm-baseline"
bash ./setup_wsl_env.sh
```

`BASELINE_RUNTIME_ROOT` must be an absolute Linux path; it is shared by all Python and Shell launchers. `BASELINE_PYTHON` optionally selects an already prepared Python executable. Keep the runtime and Docker I/O on the Linux filesystem when using WSL. Changing the root creates/selects a different runtime without changing the published results.

The installer clones the exact SkillEvolBench commit, checks/applies the four-file patch, creates a virtual environment, installs `requirements-runtime-snapshot.txt`, installs the local benchmark package and the pinned Harbor Git revision, then runs `pip check`. The package snapshot records versions from the working environment; full clean-room dependency installation was not rerun during publication.

If Docker is not installed, inspect and execute `bash ./install_docker_wsl.sh` as appropriate for Ubuntu. It uses the official Docker apt source and requests sudo. With Docker available:

```bash
bash ./build_agent_runtime_wsl.sh
bash ./run_baseline_wsl.sh check
bash ./run_baseline_wsl.sh dry-run claude-sonnet-5-anu A
```

These checks/dry-runs do not run model inference. The dry-run creates fresh runtime planning files. The historical image digest and CLI versions are recorded in `runtime_versions.txt`; the build script uses upstream installers, so an identical image digest is not guaranteed on a later rebuild.

### 2. Configure credentials locally

```bash
cp .harbor-agents.env.example .harbor-agents.env
chmod 600 .harbor-agents.env
```

Edit only the local `.harbor-agents.env` file and configure the chosen provider. Do not paste keys into tracked YAML, command arguments, reports, issues or commit messages. The template contains empty credential fields. `.gitignore` excludes the populated file and its backup variants.

The published LS3 experiment used `claude-sonnet-5-anu`: access to the ANU network/VPN and that gateway is needed to use this preset. A different provider/model creates a separate experiment and must be labelled accordingly. Source and target model labels must match. The launcher supports direct Anthropic, Gemini, DeepSeek and the upstream provider routes, but their outputs are not interchangeable with the reported LS3 results.

### 3. Acquire an explicitly selected LS3 source (uses API)

```bash
bash ./run_smoke_wsl.sh \
  --baseline-name no_skill \
  --model-preset claude-sonnet-5-anu \
  --order-seed A \
  --task-id E1-LS3-T1 \
  --max-tasks 1 \
  --run-id source__E1-LS3-T1__new01 \
  --require-verifier-pass
```

Continue only when source acquisition completes without Agent exceptions and the verifier passes. Retain failed acquisition attempts and document the selection policy. The separate `run_acquisition_policy_wsl.sh` is the historical LS1 policy; it is not the LS3 source command.

### 4. Run the same-source 27-branch matrix (uses API)

```bash
export MODEL_PRESET=claude-sonnet-5-anu
export EXPERIMENT_PREFIX=e1ls3_trainingfree_new01
CONFIRM_PAIRED_RUN=yes bash ./run_three_pair_repetitions_wsl.sh \
  "$BASELINE_RUNTIME_ROOT/SkillEvolBench/workspace/runs/source__E1-LS3-T1__new01"
```

The script evaluates T4/T5/T6 under A/B/C matched repetitions and reuses one frozen procedural abstraction with an 8,192-token author output limit. An explicit source path is required. Completed branches can be resumed with the same command. API/authentication/Agent exceptions are not accepted as completed experimental checkpoints. New source acquisition and sampling are not expected to reproduce the historical outputs exactly.

For a single target or a controlled partial run, use `run_paired_mvp_wsl.sh` with explicit `--source-task-id`, `--target-task-id`, `--source-run-dir`, `--model-preset`, `--mvp-id`, `--conditions`, and `--confirm-run`. Its `--dry-run` validates the prepared source and delivery helpers without target inference.

### 5. Optional official full baseline (separate experiment, uses API)

```bash
CONFIRM_FULL_RUN=yes bash ./run_baseline_wsl.sh run claude-sonnet-5-anu A
```

This runs the three official conditions with their independent acquisition; it is not the same-source pilot. Planned task counts are 180 / 270 / 270. The published repository does not claim this full run has completed.

## Engineering regression checks

To reconstruct the local checkout used by the existing tests, without creating Docker tasks:

```bash
python3 -B bootstrap_upstream.py
python3 -m venv .venv-tests
.venv-tests/bin/python -m pip install -r requirements-test.txt
.venv-tests/bin/python -B -m unittest discover -s tests -p test_engineering_fixes.py -v
```

On Windows use `python` and `.venv-tests\Scripts\python.exe`. Do not run unrestricted root `pytest`: benchmark task verifiers are designed for their task containers. After installing the full runtime, task/configuration validation uses upstream `scripts.validate_configs` and `scripts.validate_assets`.

## Before another push

```bash
python3 -B security_check.py --staged --secret-file /absolute/path/to/local/.harbor-agents.env
git diff --cached --check
```

The scanner reads secrets only for local exact-match checks and reports only file paths and finding types. It also blocks credential-shaped content and populated credential JSON fields. Passing a scan is a scoped check of the staged bytes, not a guarantee about files staged afterward.
