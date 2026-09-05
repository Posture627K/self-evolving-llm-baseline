"""Local Harbor compatibility for the bounded SkillEvolBench smoke test."""

from __future__ import annotations

import functools
import logging


_LOG = logging.getLogger(__name__)
_PATCHED = False


def _refresh_instruction(trial: object) -> str | None:
    """Reload instruction.md after SkillEvolBench's START hook updates it."""
    from harbor.models.task.task import strip_canary

    task = getattr(trial, "_task", None)
    paths = getattr(task, "paths", None)
    instruction_path = getattr(paths, "instruction_path", None)
    if instruction_path is None or not instruction_path.exists():
        return None

    fresh = strip_canary(instruction_path.read_text(encoding="utf-8"))
    task.instruction = fresh
    return fresh


def apply_harbor_patches() -> None:
    """Refresh injected instructions on both old and current Harbor APIs."""
    global _PATCHED
    if _PATCHED:
        return

    from harbor.environments.docker.docker import DockerEnvironment
    from harbor.trial.trial import Trial

    # SkillEvolBench targets Harbor 0.6's ``mounts_json`` keyword. Harbor
    # 0.22 renamed it to ``mounts`` and otherwise silently ignores the old
    # keyword, leaving /skills and the native CLI skill folders unmounted.
    original_docker_init = DockerEnvironment.__init__

    @functools.wraps(original_docker_init)
    def docker_init_with_legacy_mounts(
        self: object, *args: object, **kwargs: object
    ) -> None:
        legacy_mounts = list(kwargs.pop("mounts_json", None) or [])
        if legacy_mounts:
            current_mounts = list(kwargs.get("mounts") or [])
            kwargs["mounts"] = current_mounts + legacy_mounts
        original_docker_init(self, *args, **kwargs)

    DockerEnvironment.__init__ = docker_init_with_legacy_mounts

    if hasattr(Trial, "_execute_agent"):
        original = Trial._execute_agent

        @functools.wraps(original)
        async def execute_with_fresh_instruction(self: object) -> None:
            try:
                _refresh_instruction(self)
            except Exception:
                _LOG.warning("Failed to refresh task instruction", exc_info=True)
            await original(self)

        Trial._execute_agent = execute_with_fresh_instruction
        patched_method = "Trial._execute_agent"
    elif hasattr(Trial, "_run_agent_phase"):
        original = Trial._run_agent_phase

        @functools.wraps(original)
        async def run_phase_with_fresh_instruction(
            self: object, *args: object, **kwargs: object
        ) -> None:
            try:
                fresh = _refresh_instruction(self)
                if fresh is not None:
                    kwargs["instruction"] = fresh
            except Exception:
                _LOG.warning("Failed to refresh task instruction", exc_info=True)
            await original(self, *args, **kwargs)

        Trial._run_agent_phase = run_phase_with_fresh_instruction
        patched_method = "Trial._run_agent_phase"
    else:
        raise RuntimeError("Unsupported Harbor Trial API: no agent execution method")

    _PATCHED = True
    _LOG.info(
        "Installed SkillEvolBench compatibility patches on %s and "
        "DockerEnvironment.mounts",
        patched_method,
    )


def install() -> None:
    """Replace SkillEvolBench's version-specific patch at runtime."""
    import skillevolbench.harbor_ext._patches as upstream_patches

    upstream_patches.apply_harbor_patches = apply_harbor_patches


__all__ = ["install"]
