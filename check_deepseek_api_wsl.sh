#!/usr/bin/env bash
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/runtime_paths.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$BASELINE_PYTHON"

# shellcheck source=provider_credentials_wsl.sh
source "$SCRIPT_DIR/provider_credentials_wsl.sh"
load_provider_credentials "$SCRIPT_DIR/.harbor-agents.env"
require_model_credentials "deepseek-v4-flash"

exec "$PYTHON_BIN" "$SCRIPT_DIR/check_deepseek_api.py"
