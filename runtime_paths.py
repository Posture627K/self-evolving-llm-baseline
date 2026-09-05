"""Shared paths for new runs; importing this module performs no I/O writes."""
from pathlib import Path
import os

RUNTIME_ROOT = Path(os.environ.get(
    'BASELINE_RUNTIME_ROOT', str(Path.home() / 'workspaces' / 'self-evolving-llm-baseline')
)).expanduser().resolve()
REPO_ROOT = RUNTIME_ROOT / 'SkillEvolBench'
PAIRED_ROOT = REPO_ROOT / 'workspace' / 'paired_mvp'
