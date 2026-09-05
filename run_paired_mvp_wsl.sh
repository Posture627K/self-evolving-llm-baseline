#!/usr/bin/env bash
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/runtime_paths.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRET_FILE="$SCRIPT_DIR/.harbor-agents.env"
PYTHON_BIN="$BASELINE_PYTHON"

# shellcheck source=provider_credentials_wsl.sh
source "$SCRIPT_DIR/provider_credentials_wsl.sh"
MODEL_PRESET="$(model_preset_from_args "gemini-3-flash" "$@")"

is_dry_run=false
for arg in "$@"; do
  if [[ "$arg" == "--dry-run" ]]; then
    is_dry_run=true
    break
  fi
done

bash "$SCRIPT_DIR/sync_runtime_fixes_wsl.sh"

if [[ "$is_dry_run" == false ]]; then
  load_provider_credentials "$SECRET_FILE"
  require_model_credentials "$MODEL_PRESET"
fi

exec "$PYTHON_BIN" "$SCRIPT_DIR/run_paired_mvp.py" "$@"
