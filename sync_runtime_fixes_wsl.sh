#!/usr/bin/env bash
set -euo pipefail
baseline_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$baseline_dir/runtime_paths.sh"
exec python3 "$baseline_dir/bootstrap_upstream.py" --repo-dir "$BASELINE_RUNTIME_ROOT/SkillEvolBench" --existing-only
