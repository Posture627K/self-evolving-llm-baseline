#!/usr/bin/env bash
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/runtime_paths.sh"

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
paired_root="$BASELINE_RUNTIME_ROOT/SkillEvolBench/workspace/paired_mvp"
source_task="E1-LS3-T1"
model_preset="${MODEL_PRESET:-claude-sonnet-5-anu}"
experiment_prefix="${EXPERIMENT_PREFIX:-e1ls3_trainingfree_v1}"
source_run_dir="${1:-}"
if [[ "${CONFIRM_PAIRED_RUN:-}" != "yes" || -z "$source_run_dir" ]]; then
  echo "Usage: CONFIRM_PAIRED_RUN=yes bash $0 /absolute/path/to/verified/source_run" >&2
  echo "This runs 27 paid target branches and may author a procedural skill." >&2
  exit 2
fi
targets=("E1-LS3-T4" "E1-LS3-T5" "E1-LS3-T6")
repetitions=("A" "B" "C")
artifact_mvp_id="${experiment_prefix}__E1-LS3-T4__repA"

for target in "${targets[@]}"; do
  for repetition in "${repetitions[@]}"; do
    mvp_id="${experiment_prefix}__${target}__rep${repetition}"
    args=(
      --source-task-id "$source_task"
      --target-task-id "$target"
      --model-preset "$model_preset"
      --order-seed "$repetition"
      --mvp-id "$mvp_id"
      --conditions all
      --skip-ledger
      --author-max-tokens 8192
      --confirm-run
    )
    if [[ -n "$source_run_dir" ]]; then
      args+=(--source-run-dir "$source_run_dir")
    fi
    if [[ "$mvp_id" != "$artifact_mvp_id" ]]; then
      args+=(--reuse-procedural-from "$paired_root/$artifact_mvp_id")
    fi
    if [[ -d "$paired_root/$mvp_id" ]]; then
      args+=(--resume)
    fi
    echo "Running target=$target repetition=$repetition mvp_id=$mvp_id"
    bash "$script_dir/run_paired_mvp_wsl.sh" "${args[@]}"
  done
done

"$BASELINE_PYTHON" \
  "$script_dir/analyze_paired_repetitions.py" \
  --experiment-prefix "$experiment_prefix"
