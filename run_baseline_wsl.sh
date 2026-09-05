#!/usr/bin/env bash
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/runtime_paths.sh"

mode="${1:-check}"
model_preset="${2:-gpt-5.4}"
order_seed="${3:-A}"

case "${mode}" in
  check|dry-run|run) ;;
  *) echo "Usage: $0 [check|dry-run|run] [model-preset] [A|B|C]" >&2; exit 2 ;;
esac

case "${order_seed}" in
  A|B|C) ;;
  *) echo "Order seed must be A, B, or C." >&2; exit 2 ;;
esac

baseline_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
runtime_root="$BASELINE_RUNTIME_ROOT"
repo_dir="${runtime_root}/SkillEvolBench"
venv_dir="${runtime_root}/.venv"
python_bin="$BASELINE_PYTHON"
credentials_file="${baseline_dir}/.harbor-agents.env"
local_model_config="${baseline_dir}/model_presets/${model_preset}.yaml"
if [[ -f "${local_model_config}" ]]; then
  model_config="${local_model_config}"
else
  model_config="${repo_dir}/configs/models/${model_preset}.yaml"
fi

# shellcheck source=provider_credentials_wsl.sh
source "${baseline_dir}/provider_credentials_wsl.sh"

if [[ ! -x "${python_bin}" ]]; then
  echo "WSL environment missing. Run ./setup_wsl_env.sh first." >&2
  exit 1
fi

bash "${baseline_dir}/sync_runtime_fixes_wsl.sh"

if [[ ! -f "${model_config}" ]]; then
  echo "Unknown model preset: ${model_preset}" >&2
  exit 1
fi

if [[ "${mode}" == "run" ]]; then
  load_provider_credentials "${credentials_file}"
  require_model_credentials "${model_preset}"
elif [[ -f "${credentials_file}" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${credentials_file}"
  set +a
fi

cd "${repo_dir}"
"${python_bin}" -m scripts.validate_configs
"${python_bin}" -m scripts.validate_assets
"${python_bin}" -m scripts.preflight

if [[ "${mode}" == "check" ]]; then
  exit 0
fi

if [[ "${mode}" == "run" ]]; then
  "${python_bin}" -m scripts.preflight --strict
  if [[ "${CONFIRM_FULL_RUN:-}" != "yes" ]]; then
    echo "Set CONFIRM_FULL_RUN=yes to acknowledge the 180-270 task cost per condition." >&2
    exit 2
  fi
fi

timestamp="$(date +%Y%m%d_%H%M%S)"
conditions=(
  no_skill
  raw_trajectory_rag
  selfgen_experience_always
)

for condition in "${conditions[@]}"; do
  run_id="baseline__${condition}__${model_preset}__seed${order_seed}__${timestamp}"
  arguments=(
    -m scripts.run
    --baseline-name "${condition}"
    --model-yaml "${model_config}"
    --order-seed "${order_seed}"
    --run-id "${run_id}"
  )
  if [[ "${mode}" == "dry-run" ]]; then
    arguments+=(--dry-run)
  fi
  "${python_bin}" "${arguments[@]}"
done
