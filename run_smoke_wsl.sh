#!/usr/bin/env bash
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/runtime_paths.sh"

baseline_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
runtime_root="$BASELINE_RUNTIME_ROOT"
python_bin="$BASELINE_PYTHON"
credentials_file="$baseline_dir/.harbor-agents.env"

# shellcheck source=provider_credentials_wsl.sh
source "$baseline_dir/provider_credentials_wsl.sh"
model_preset="$(model_preset_from_args "gemini-3-flash" "$@")"
is_dry_run=false
for argument in "$@"; do
  if [[ "$argument" == "--dry-run" ]]; then
    is_dry_run=true
    break
  fi
done

if [[ ! -x "$python_bin" ]]; then
  echo "WSL Python environment is missing. Run setup_wsl_env.sh first." >&2
  exit 1
fi
bash "$baseline_dir/sync_runtime_fixes_wsl.sh"
if [[ "$is_dry_run" == false ]]; then
  load_provider_credentials "$credentials_file"
  require_model_credentials "$model_preset"
fi

exec "$python_bin" "$baseline_dir/run_smoke.py" "$@"
