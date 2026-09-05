#!/usr/bin/env bash
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/runtime_paths.sh"

runtime_root="$BASELINE_RUNTIME_ROOT"
repo="$runtime_root/SkillEvolBench"
source_context="$repo/docker/agent-build"

if [ ! -f "$source_context/install-agent-runtime.sh" ]; then
  echo "SkillEvolBench agent build context not found: $source_context" >&2
  exit 1
fi

# Keep the pinned upstream checkout clean. The current OpenClaw CLI routes a
# bare `setup --workspace` call to interactive onboarding, so patch only a
# disposable build context to request baseline-only initialization.
build_context="$(mktemp -d "$runtime_root/.agent-runtime-build.XXXXXX")"
case "$build_context" in
  "$runtime_root"/.agent-runtime-build.*) ;;
  *) echo "Unexpected temporary path: $build_context" >&2; exit 1 ;;
esac
trap 'rm -rf -- "$build_context"' EXIT

cp -a "$source_context/." "$build_context/"

old_command='openclaw --no-color setup --workspace "$workspace_dir"'
new_command='openclaw --no-color setup --baseline --workspace "$workspace_dir"'
install_script="$build_context/install-agent-runtime.sh"

if ! grep -Fq "$old_command" "$install_script"; then
  echo "Expected OpenClaw setup command was not found; upstream may have changed." >&2
  exit 1
fi

sed -i "s|$old_command|$new_command|" "$install_script"
bash "$build_context/build.sh"
docker image inspect agent-runtime:latest >/dev/null

echo "agent-runtime:latest build: PASS"
