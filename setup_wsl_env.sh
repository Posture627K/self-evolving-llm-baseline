#!/usr/bin/env bash
set -euo pipefail
baseline_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$baseline_dir/runtime_paths.sh"
runtime_repo="$BASELINE_RUNTIME_ROOT/SkillEvolBench"
harbor_commit="389bd4f8ce796ef4a97de4b62675021e262c8e76"

python3.12 "$baseline_dir/bootstrap_upstream.py" --repo-dir "$runtime_repo"
if [[ ! -x "$BASELINE_PYTHON" ]]; then
  python3.12 -m venv "$BASELINE_RUNTIME_ROOT/.venv"
fi
"$BASELINE_PYTHON" -m pip install -r "$baseline_dir/requirements-runtime-snapshot.txt"
"$BASELINE_PYTHON" -m pip install --no-deps -e "$runtime_repo[dev]"
"$BASELINE_PYTHON" -m pip install --no-deps "git+https://github.com/harbor-framework/harbor.git@$harbor_commit"
"$BASELINE_PYTHON" -m pip check
"$BASELINE_PYTHON" -B -c 'import harbor, skillevolbench; print("Python environment: PASS")'
echo "Environment prepared. Docker image setup and model credentials are separate steps."
