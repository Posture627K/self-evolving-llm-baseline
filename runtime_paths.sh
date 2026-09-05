#!/usr/bin/env bash
# Source from a launcher. Keep credentials out of this configuration.
export BASELINE_RUNTIME_ROOT="${BASELINE_RUNTIME_ROOT:-$HOME/workspaces/self-evolving-llm-baseline}"
case "$BASELINE_RUNTIME_ROOT" in
  /*) ;;
  *) echo "BASELINE_RUNTIME_ROOT must be an absolute Linux path." >&2; return 2 ;;
esac
export BASELINE_PYTHON="${BASELINE_PYTHON:-$BASELINE_RUNTIME_ROOT/.venv/bin/python}"
