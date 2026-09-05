"""Run a matched-delivery episodic-versus-procedural SkillEvolBench MVP.

One verified acquisition trajectory is frozen as the shared source evidence.
Three clean branches then evaluate one held-out task:

* no_artifact: no source evidence is available;
* episodic: a transport-normalized, untruncated event stream is injected;
* procedural: the same stream is distilled into one SKILL.md and injected
  through the same prompt location.

This is a bounded measurement run, not a full SkillEvolBench experiment.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MethodType
from typing import Any

import yaml


from runtime_paths import RUNTIME_ROOT
REPO_ROOT = RUNTIME_ROOT / "SkillEvolBench"
RUNS_ROOT = REPO_ROOT / "workspace" / "runs"
PAIRED_ROOT = REPO_ROOT / "workspace" / "paired_mvp"
LOCAL_MODEL_PRESETS = Path(__file__).resolve().parent / "model_presets"

sys.path.insert(0, str(REPO_ROOT))

from harbor_compat import install as install_harbor_compat  # noqa: E402
from scripts.run import _apply_model_preset  # noqa: E402
from skillevolbench.baselines import BaselineRuntime, load_baseline  # noqa: E402
from skillevolbench.discovery import (  # noqa: E402
    TaskRecord,
    TaskRegistry,
    default_skills_root,
    default_tasks_root,
)
from skillevolbench.metrics.reporter import ReportGenerator  # noqa: E402
from skillevolbench.orchestration import LifelongRunner  # noqa: E402
from skillevolbench.schemas import (  # noqa: E402
    CompactedTrajectory,
    ReplayRecord,
    RunConfig,
    StrategyConfig,
)


CONDITION_BASELINES = {
    "no_artifact": "no_skill",
    "episodic": "no_skill",
    "procedural": "no_skill",
}
AUTHORING_BASELINE = "selfgen_experience_always"
TRANSPORT_ONLY_FIELDS = {
    "step_id",
    "timestamp",
    "model_name",
    "metrics",
    "llm_call_count",
}
SEMANTIC_FIELD_ORDER = (
    "message",
    "reasoning_content",
    "tool_calls",
    "observation",
)


def resolve_model_preset(model_preset: str) -> Path:
    local_path = LOCAL_MODEL_PRESETS / f"{model_preset}.yaml"
    if local_path.is_file():
        return local_path
    return REPO_ROOT / "configs" / "models" / f"{model_preset}.yaml"


def normalize_model_identity(model_name: str) -> str:
    normalized = model_name.strip().casefold()
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    return normalized


def source_agent_model(source_run: Path, task_id: str) -> str:
    candidates: list[tuple[int, Path, dict[str, Any]]] = []
    for path in (source_run / "harbor-job").glob("**/result.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("task_name") == task_id:
            candidates.append((path.stat().st_mtime_ns, path, payload))
    if not candidates:
        raise RuntimeError(f"source run has no Harbor result for {task_id}")
    _, result_path, payload = max(candidates, key=lambda item: item[0])
    exception = payload.get("exception_info")
    if isinstance(exception, dict):
        raise RuntimeError(
            "source experience came from an Agent-failed trial: "
            f"{exception.get('exception_type')} ({result_path})"
        )
    model_info = (payload.get("agent_info") or {}).get("model_info") or {}
    model_name = model_info.get("name")
    if not isinstance(model_name, str) or not model_name.strip():
        raise RuntimeError(f"source run does not record its Agent model: {result_path}")
    return model_name


@dataclass(frozen=True)
class NormalizedEvidence:
    """Loss-minimized source packet shared by both representation branches."""

    raw_path: Path
    payload: dict[str, Any]
    text: str
    n_events: int
    n_units: int
    sha256: str


class BranchInfrastructureError(RuntimeError):
    """Raised when Harbor completed bookkeeping but the Agent itself failed."""


def _jsonable_list(values: Any) -> list[Any]:
    result: list[Any] = []
    for value in values or []:
        if hasattr(value, "model_dump"):
            result.append(value.model_dump(mode="json"))
        elif isinstance(value, dict):
            result.append(value)
        else:
            result.append(str(value))
    return result


class MatchedArtifactPromptBuilder:
    """Inject either representation through one neutral prompt wrapper."""

    def __init__(
        self,
        *,
        artifact_text: str | None,
        source_task_id: str,
    ) -> None:
        self.artifact_text = artifact_text
        self.source_task_id = source_task_id

    def build(
        self,
        *,
        original_instruction: str,
        baseline: Any,
        task: Any,
        retrieved_skills: list[Any],
        retrieved_trajectories: list[Any],
        history_context: str | None,
        library_frozen: bool,
    ) -> str:
        del baseline, task, retrieved_skills, retrieved_trajectories
        del history_context, library_frozen
        if self.artifact_text is None:
            return original_instruction
        return (
            f"# Task\n\n{original_instruction.strip()}\n\n"
            "# Prior Experience Artifact\n\n"
            "The following artifact was derived from one verified previous "
            "task in the same family. Use it only when applicable, and verify "
            "it against the current task rather than copying it blindly.\n\n"
            f"Source task: `{self.source_task_id}`\n\n"
            "<prior-experience-artifact>\n"
            f"{self.artifact_text.rstrip()}\n"
            "</prior-experience-artifact>\n"
        )


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_instruction(task: TaskRecord) -> str:
    return (task.folder / task.spec.harbor.instruction).read_text(encoding="utf-8")


def _load_record(path: Path) -> ReplayRecord:
    return ReplayRecord.model_validate_json(path.read_text(encoding="utf-8"))


def _source_record_path(run_dir: Path, task_id: str) -> Path:
    return run_dir / "stores" / "replay" / "records" / f"{task_id}.json"


def discover_source_run(task_id: str) -> Path:
    """Find the newest successful no-skill smoke run containing task_id."""
    candidates = sorted(
        RUNS_ROOT.glob("smoke__no_skill__*"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for run_dir in candidates:
        record_path = _source_record_path(run_dir, task_id)
        if not record_path.is_file():
            continue
        try:
            record = _load_record(record_path)
        except Exception:
            continue
        if record.outcome.verifier_passed:
            return run_dir
    raise FileNotFoundError(
        f"No successful no_skill smoke run contains {task_id!r} under {RUNS_ROOT}"
    )


def load_source_evidence(run_dir: Path, task_id: str) -> ReplayRecord:
    record_path = _source_record_path(run_dir, task_id)
    if not record_path.is_file():
        raise FileNotFoundError(record_path)
    record = _load_record(record_path)
    if record.task_id != task_id:
        raise ValueError(f"Source record task mismatch: {record.task_id} != {task_id}")
    if not record.outcome.verifier_passed:
        raise ValueError(f"Source evidence {task_id} did not pass its verifier")
    return record


def resolve_raw_trajectory(source: ReplayRecord) -> Path:
    """Resolve the real agent trace, rejecting artifact manifests.

    Some Harbor versions report ``artifacts/manifest.json`` as
    ``outcome.trajectory_path`` even when the canonical ATIF trace exists in
    ``<trial>/agent/trajectory.json``. The manifest records copied files; it
    is not an agent experience and must never become the episodic artifact.
    """
    candidates: list[Path] = []
    trial_dir_value = getattr(source.outcome, "trial_dir", None)
    if trial_dir_value:
        trial_dir = Path(trial_dir_value)
        candidates.extend(
            [
                trial_dir / "agent" / "trajectory.json",
                trial_dir / "artifacts" / "logs" / "agent" / "trajectory.json",
            ]
        )
        agent_dir = trial_dir / "agent"
        if agent_dir.is_dir():
            candidates.extend(sorted(agent_dir.glob("*.trajectory.json")))
            candidates.extend(sorted(agent_dir.glob("*.trajectory.jsonl")))

    reported = getattr(source.outcome, "trajectory_path", None)
    if reported:
        reported_path = Path(reported)
        if reported_path.name != "manifest.json":
            candidates.append(reported_path)

    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    raise FileNotFoundError(
        "No real agent trajectory found. Checked: "
        + ", ".join(str(path) for path in candidates)
    )


def _load_event_sequence(path: Path) -> tuple[list[dict[str, Any]], str]:
    """Parse ATIF, JSON arrays, JSONL, or plain text without event selection."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, dict) and isinstance(parsed.get("steps"), list):
        events = [item for item in parsed["steps"] if isinstance(item, dict)]
        return events, str(parsed.get("schema_version") or "ATIF")
    if isinstance(parsed, list):
        return [
            item if isinstance(item, dict) else {"message": item}
            for item in parsed
        ], "json-array"
    if isinstance(parsed, dict):
        return [parsed], "json-object"

    jsonl: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            jsonl = []
            break
        jsonl.append(item if isinstance(item, dict) else {"message": item})
    if jsonl:
        return jsonl, "jsonl"
    return [{"source": "unknown", "message": raw}], "plain-text"


def build_normalized_evidence(
    *,
    source: ReplayRecord,
    source_task: TaskRecord,
) -> NormalizedEvidence:
    """Create an ordered evidence-unit stream with no semantic truncation.

    Only step-level transport/accounting fields are removed. Every non-empty
    semantic field is retained as its own auditable evidence unit, including
    messages, reasoning, tool calls, observations, and unknown extra fields.
    """
    raw_path = resolve_raw_trajectory(source)
    events, source_format = _load_event_sequence(raw_path)
    units: list[dict[str, Any]] = []
    unit_index = 1
    for event_index, event in enumerate(events):
        source_name = str(event.get("source") or event.get("role") or "unknown")
        ordered_keys = [key for key in SEMANTIC_FIELD_ORDER if key in event]
        ordered_keys.extend(
            sorted(
                key
                for key in event
                if key not in SEMANTIC_FIELD_ORDER
                and key not in TRANSPORT_ONLY_FIELDS
                and key not in {"source", "role"}
            )
        )
        for key in ordered_keys:
            value = event.get(key)
            if value in (None, "", [], {}):
                continue
            canonical_value = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            units.append(
                {
                    "evidence_unit_id": f"E{unit_index:04d}",
                    "event_index": event_index,
                    "source": source_name,
                    "kind": key,
                    "content": value,
                    "content_sha256": _sha256_text(canonical_value),
                }
            )
            unit_index += 1

    if not units:
        raise ValueError(f"Trajectory contains no semantic evidence units: {raw_path}")

    outcome = source.outcome
    outcome_data = outcome.model_dump(mode="json")
    payload = {
        "schema_version": "same-source-evidence-2.0",
        "source_task": {
            "task_id": source_task.spec.task_id,
            "family_id": source_task.spec.family_id,
            "role": source_task.spec.role.value,
            "instruction": _read_instruction(source_task),
        },
        "source_outcome": {
            "verifier_passed": outcome_data.get("verifier_passed"),
            "normalized_score": outcome_data.get("normalized_score"),
            "reward": outcome_data.get("reward"),
            "failure_summary": outcome_data.get("failure_summary"),
            "failed_tests": outcome_data.get("failed_tests"),
            "rubric_dimensions": outcome_data.get("rubric_dimensions"),
        },
        "normalization": {
            "source_format": source_format,
            "raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
            "dropped_transport_fields": sorted(TRANSPORT_ONLY_FIELDS),
            "semantic_event_selection": False,
            "semantic_truncation": False,
            "event_order_preserved": True,
        },
        "evidence_units": units,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return NormalizedEvidence(
        raw_path=raw_path,
        payload=payload,
        text=text,
        n_events=len(events),
        n_units=len(units),
        sha256=_sha256_text(text),
    )


def build_target_demand_card(eval_task: TaskRecord) -> dict[str, Any]:
    """Freeze explicit target demands before procedural authoring.

    Demands are extracted deterministically from the target instruction, not
    inferred after seeing a generated skill or a branch outcome.
    """
    instruction = _read_instruction(eval_task)
    requirement_headings = (
        "expected behavior",
        "expected behaviour",
        "requirements",
        "acceptance criteria",
    )
    resource_headings = (
        "useful paths",
        "useful files",
        "resources",
        "reference paths",
    )
    current_heading = ""
    demand_texts: list[tuple[str, str]] = []
    resource_texts: list[tuple[str, str]] = []
    for raw_line in instruction.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("#"):
            current_heading = stripped.lstrip("#").strip()
            continue
        colon_heading = stripped.rstrip(":").strip()
        colon_heading_key = colon_heading.casefold()
        if stripped.endswith(":") and (
            any(key in colon_heading_key for key in requirement_headings)
            or any(key in colon_heading_key for key in resource_headings)
        ):
            current_heading = colon_heading
            continue
        if not stripped.startswith("- "):
            continue
        text = stripped[2:].strip()
        heading_key = current_heading.casefold()
        if any(key in heading_key for key in resource_headings):
            resource_texts.append((text, current_heading))
        else:
            # Bullets under an explicit requirement heading, and bullets not
            # identified as resource hints, remain observable task demands.
            demand_texts.append((text, current_heading))

    demands = [
        {
            "target_demand_id": f"D{index:03d}",
            "text": text,
            "source": "target_instruction_bullet",
            "source_section": heading,
            "explicit_requirement_section": any(
                key in heading.casefold() for key in requirement_headings
            ),
        }
        for index, (text, heading) in enumerate(demand_texts, start=1)
    ]
    resource_hints = [
        {
            "resource_hint_id": f"H{index:03d}",
            "text": text,
            "source_section": heading,
        }
        for index, (text, heading) in enumerate(resource_texts, start=1)
    ]
    return {
        "schema_version": "target-demand-card-1.1",
        "task_id": eval_task.spec.task_id,
        "family_id": eval_task.spec.family_id,
        "role": eval_task.spec.role.value,
        "instruction_sha256": _sha256_text(instruction),
        "fixed_before_procedural_authoring": True,
        "demands": demands,
        "resource_hints": resource_hints,
        "scope_note": (
            "Explicit behavioral bullets are separated from resource/path hints. "
            "Hidden verifier requirements require independent human review."
        ),
    }


def validate_pair(
    registry: TaskRegistry,
    source: ReplayRecord,
    source_task: TaskRecord,
    eval_task: TaskRecord,
) -> None:
    if source.family_id != source_task.spec.family_id:
        raise ValueError("Source ReplayRecord and source TaskSpec family differ")
    if source_task.spec.family_id != eval_task.spec.family_id:
        raise ValueError("Source and evaluation tasks must belong to the same family")
    if source_task.spec.phase.value != "learning":
        raise ValueError("Source task must be an acquisition/learning task")
    if eval_task.spec.phase.value != "evaluation":
        raise ValueError("Target task must be held-out/evaluation")
    if eval_task.spec.task_id == source_task.spec.task_id:
        raise ValueError("Source and target tasks must differ")
    if registry.task(source_task.spec.task_id).spec.task_id != source.task_id:
        raise ValueError("Source task is not present in the active benchmark registry")


def build_config(
    *,
    condition: str,
    run_id: str,
    model_preset: str,
    mvp_dir: Path,
    order_seed: str,
) -> RunConfig:
    baseline = load_baseline(CONDITION_BASELINES[condition])
    model_path = resolve_model_preset(model_preset)
    if not model_path.is_file():
        raise FileNotFoundError(f"Unknown model preset: {model_path}")
    baseline, _ = _apply_model_preset(baseline, model_path)

    strategy_name = baseline.default_strategy
    if strategy_name == "none":
        strategy_name = "chain"
    strategy = StrategyConfig.from_yaml(
        REPO_ROOT / "configs" / "strategies" / f"{strategy_name}.yaml"
    )
    return RunConfig(
        run_id=run_id,
        baseline=baseline,
        strategy=strategy,
        order_seed=order_seed,
        workspace_root=mvp_dir / "branches",
        max_tasks=1,
    )


def build_authoring_config(
    *,
    run_id: str,
    model_preset: str,
    mvp_dir: Path,
    order_seed: str,
    author_max_tokens: int,
) -> RunConfig:
    baseline = load_baseline(AUTHORING_BASELINE)
    model_path = resolve_model_preset(model_preset)
    if not model_path.is_file():
        raise FileNotFoundError(f"Unknown model preset: {model_path}")
    baseline, _ = _apply_model_preset(baseline, model_path)
    strategy = StrategyConfig.from_yaml(
        REPO_ROOT / "configs" / "strategies" / f"{baseline.default_strategy}.yaml"
    )
    strategy = strategy.model_copy(
        update={"author_max_tokens": author_max_tokens}
    )
    return RunConfig(
        run_id=run_id,
        baseline=baseline,
        strategy=strategy,
        order_seed=order_seed,
        workspace_root=mvp_dir / "authoring",
        max_tasks=1,
    )


def parse_conditions(value: str) -> tuple[str, ...]:
    """Parse a stable, de-duplicated branch selection."""
    if value.strip().casefold() == "all":
        return tuple(CONDITION_BASELINES)
    requested = {item.strip() for item in value.split(",") if item.strip()}
    unknown = requested - set(CONDITION_BASELINES)
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown conditions: {', '.join(sorted(unknown))}"
        )
    if not requested:
        raise argparse.ArgumentTypeError("at least one condition is required")
    return tuple(name for name in CONDITION_BASELINES if name in requested)


def next_run_id(workspace_root: Path, base: str) -> str:
    """Choose a non-destructive retry ID when an earlier run is incomplete."""
    candidate = workspace_root / base
    if not candidate.exists() or not any(candidate.iterdir()):
        return base
    index = 1
    while True:
        retry = f"{base}__retry{index}"
        candidate = workspace_root / retry
        if not candidate.exists() or not any(candidate.iterdir()):
            return retry
        index += 1


def load_harbor_trial_status(
    *, run_dir: Path, target_task_id: str
) -> dict[str, Any] | None:
    """Read Harbor's authoritative Agent exception state for one branch."""
    candidates: list[tuple[int, Path, dict[str, Any]]] = []
    harbor_root = run_dir / "harbor-job"
    if not harbor_root.is_dir():
        return None
    for path in harbor_root.glob("**/result.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("task_name") != target_task_id:
            continue
        candidates.append((path.stat().st_mtime_ns, path, payload))
    if not candidates:
        return None
    _, result_path, payload = max(candidates, key=lambda item: item[0])
    exception = payload.get("exception_info")
    agent_result = payload.get("agent_result") or {}
    return {
        "result_path": str(result_path),
        "agent_completed": exception is None,
        "exception_type": (
            exception.get("exception_type") if isinstance(exception, dict) else None
        ),
        "exception_message": (
            exception.get("exception_message") if isinstance(exception, dict) else None
        ),
        "agent_input_tokens": agent_result.get("n_input_tokens", 0),
        "agent_output_tokens": agent_result.get("n_output_tokens", 0),
        "agent_cache_tokens": agent_result.get("n_cache_tokens", 0),
        "agent_cost_usd_estimate": agent_result.get("cost_usd", 0.0),
    }


def load_completed_branch_results(
    *,
    mvp_dir: Path,
    source_task_id: str,
    target_task_id: str,
) -> dict[str, dict[str, Any]]:
    """Load valid checkpoints without treating partial run directories as complete."""
    results: dict[str, tuple[int, dict[str, Any]]] = {}
    branches_root = mvp_dir / "branches"
    if not branches_root.is_dir():
        return {}
    for path in branches_root.glob("*/paired_branch_result.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        condition = payload.get("condition")
        if condition not in CONDITION_BASELINES:
            continue
        if payload.get("source_task_id") != source_task_id:
            continue
        if payload.get("target_task_id") != target_task_id:
            continue
        run_dir_value = payload.get("run_dir")
        if not isinstance(run_dir_value, str):
            continue
        trial_status = load_harbor_trial_status(
            run_dir=Path(run_dir_value),
            target_task_id=target_task_id,
        )
        if trial_status is None or not trial_status["agent_completed"]:
            continue
        modified = path.stat().st_mtime_ns
        current = results.get(condition)
        if current is None or modified > current[0]:
            results[condition] = (modified, payload)
    return {condition: item[1] for condition, item in results.items()}


def ensure_evidence_packet(
    *,
    mvp_dir: Path,
    source_run: Path,
    source: ReplayRecord,
    source_task: TaskRecord,
    eval_task: TaskRecord,
    normalized: NormalizedEvidence,
    target_demand_card: dict[str, Any],
) -> Path:
    evidence_dir = mvp_dir / "evidence"
    packet_path = evidence_dir / "evidence_packet.json"
    if packet_path.is_file():
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        expected = {
            "source_task_id": source_task.spec.task_id,
            "target_task_id": eval_task.spec.task_id,
            "canonical_payload_sha256": normalized.sha256,
        }
        mismatches = {
            key: (packet.get(key), value)
            for key, value in expected.items()
            if packet.get(key) != value
        }
        if mismatches:
            raise RuntimeError(f"resume evidence mismatch: {mismatches}")
        return evidence_dir
    if evidence_dir.exists() and any(evidence_dir.iterdir()):
        raise RuntimeError(
            f"incomplete evidence checkpoint requires review: {evidence_dir}"
        )
    return persist_evidence_packet(
        mvp_dir=mvp_dir,
        source_run=source_run,
        source=source,
        source_task=source_task,
        eval_task=eval_task,
        normalized=normalized,
        target_demand_card=target_demand_card,
    )


def load_cached_procedural_representation(
    *, evidence_dir: Path, normalized: NormalizedEvidence
) -> tuple[dict[str, Any], str] | None:
    procedural_dir = evidence_dir / "procedural"
    skill_path = procedural_dir / "SKILL.md"
    manifest_path = procedural_dir / "authoring_manifest.json"
    metadata_path = procedural_dir / "procedural_metadata.json"
    if not (skill_path.is_file() and manifest_path.is_file() and metadata_path.is_file()):
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("source_payload_sha256") != normalized.sha256:
        raise RuntimeError("cached procedural artifact has a different source payload")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return metadata, skill_path.read_text(encoding="utf-8")


def load_reusable_procedural_representation(
    *, source_path: Path, normalized: NormalizedEvidence
) -> tuple[dict[str, Any], str, Path]:
    """Load one frozen procedural artifact for repeated target executions."""
    resolved = source_path.resolve()
    if (resolved / "evidence" / "procedural").is_dir():
        procedural_dir = resolved / "evidence" / "procedural"
    elif resolved.name == "procedural" and resolved.is_dir():
        procedural_dir = resolved
    else:
        raise FileNotFoundError(
            "--reuse-procedural-from must be an MVP directory or its "
            f"evidence/procedural directory: {resolved}"
        )
    loaded = load_cached_procedural_representation(
        evidence_dir=procedural_dir.parent,
        normalized=normalized,
    )
    if loaded is None:
        raise RuntimeError(f"Reusable procedural checkpoint is incomplete: {procedural_dir}")
    metadata, text = loaded
    return metadata, text, procedural_dir


def persist_evidence_packet(
    *,
    mvp_dir: Path,
    source_run: Path,
    source: ReplayRecord,
    source_task: TaskRecord,
    eval_task: TaskRecord,
    normalized: NormalizedEvidence,
    target_demand_card: dict[str, Any],
) -> Path:
    evidence_dir = mvp_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=False)
    (evidence_dir / "source_replay_record.json").write_text(
        source.model_dump_json(indent=2), encoding="utf-8"
    )

    raw_target = evidence_dir / "source_trajectory.atif.json"
    shutil.copy2(normalized.raw_path, raw_target)
    normalized_path = evidence_dir / "normalized_source_evidence.json"
    normalized_path.write_text(normalized.text, encoding="utf-8")
    demand_path = evidence_dir / "target_demand_card.json"
    demand_path.write_text(
        json.dumps(target_demand_card, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    packet = {
        "schema_version": "paired-mvp-2.0",
        "source_run": str(source_run),
        "source_task_id": source_task.spec.task_id,
        "source_family_id": source_task.spec.family_id,
        "source_verifier_passed": source.outcome.verifier_passed,
        "source_normalized_score": source.outcome.normalized_score,
        "source_raw_trajectory_copy": str(raw_target),
        "canonical_payload": str(normalized_path),
        "canonical_payload_sha256": normalized.sha256,
        "canonical_payload_chars": len(normalized.text),
        "canonical_event_count": normalized.n_events,
        "canonical_evidence_unit_count": normalized.n_units,
        "semantic_event_selection": False,
        "semantic_truncation": False,
        "target_task_id": eval_task.spec.task_id,
        "target_role": eval_task.spec.role.value,
        "target_demand_card": str(demand_path),
        "delivery_mode": "matched_prompt",
        "conditions": list(CONDITION_BASELINES),
    }
    (evidence_dir / "evidence_packet.json").write_text(
        json.dumps(packet, indent=2), encoding="utf-8"
    )
    return evidence_dir


def _install_untruncated_induction_prompt(evolver: Any) -> None:
    """Remove SkillAuthor's 8K-character T1 input cap for parity.

    The episodic branch receives the full normalized source packet. Keeping
    the upstream induction cap would silently give the procedural operator a
    strict prefix of that packet, confounding representation with source
    information. The rest of SkillAuthor, including its output schema and
    parser, remains unchanged.
    """
    from skillevolbench.components.skill_author import (
        _INDUCE_SYSTEM,
        _INDUCE_USER_TEMPLATE,
    )
    from skillevolbench.stores.library_store import skill_id_to_slug

    def render_untruncated(
        self: Any,
        *,
        family_id: str,
        latent_skill_id: str,
        compacted: Any,
        outcome: Any,
    ) -> tuple[str, str]:
        user = _INDUCE_USER_TEMPLATE.format(
            family_id=family_id,
            latent_skill_id=latent_skill_id,
            slug=skill_id_to_slug(latent_skill_id),
            verifier_passed=getattr(outcome, "verifier_passed", False),
            failure_summary=self._format_feedback(outcome, self._feedback_level),
            trajectory_summary=(getattr(compacted, "text", "") or ""),
        )
        return _INDUCE_SYSTEM, user

    evolver._render_induction_prompt = MethodType(render_untruncated, evolver)


def extract_procedural_spans(skill_md: str) -> list[dict[str, Any]]:
    """Split SKILL.md into stable blocks for sidecar provenance mapping."""
    spans: list[dict[str, Any]] = []
    block: list[str] = []
    start_line = 1

    def flush(end_line: int) -> None:
        nonlocal block, start_line
        text = "\n".join(block).strip()
        if text:
            spans.append(
                {
                    "procedural_span_id": f"P{len(spans) + 1:03d}",
                    "start_line": start_line,
                    "end_line": end_line,
                    "text": text,
                    "content_sha256": _sha256_text(text),
                }
            )
        block = []

    lines = skill_md.splitlines()
    for line_no, line in enumerate(lines, start=1):
        if not line.strip():
            flush(line_no - 1)
            start_line = line_no + 1
            continue
        if line.startswith("#") and block:
            flush(line_no - 1)
            start_line = line_no
        block.append(line)
    flush(len(lines))
    return spans


def _parse_json_response(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Audit response must be a JSON object")
    return parsed


def generate_abstraction_delta_ledger(
    *,
    evidence_dir: Path,
    normalized: NormalizedEvidence,
    skill_md: str,
    target_demand_card: dict[str, Any],
    audit_client: Any,
) -> tuple[Path, Path]:
    """Create a sidecar audit; it is never exposed to the task-solving agent."""
    spans = extract_procedural_spans(skill_md)
    evidence_ids = {
        unit["evidence_unit_id"]
        for unit in normalized.payload["evidence_units"]
    }
    span_ids = {span["procedural_span_id"] for span in spans}
    demand_ids = {
        demand["target_demand_id"]
        for demand in target_demand_card["demands"]
    }
    allowed_changes = {"preserved", "omitted", "reorganized", "generalized"}
    allowed_relations = {"supports", "conflicts", "unrelated", "unclear"}
    allowed_confidences = {"low", "medium", "high"}
    system = (
        "You audit an experience-to-procedure transformation. Produce JSON "
        "only. Ground every claim in the supplied IDs. Do not infer branch "
        "outcomes, and do not call a generalization 'over-generalization' "
        "unless a fixed target demand makes its boundary invalid."
    )
    prompt = "\n".join(
        [
            "Audit how source evidence changed during procedural abstraction.",
            "Allowed change labels: preserved, omitted, reorganized, generalized.",
            "Allowed demand relations: supports, conflicts, unrelated, unclear.",
            "Treat unsupported procedural content separately as unsupported_additions.",
            "Return this JSON schema:",
            json.dumps(
                {
                    "alignments": [
                        {
                            "evidence_unit_ids": ["E0001"],
                            "procedural_span_ids": ["P001"],
                            "change": "preserved",
                            "target_demand_ids": ["D001"],
                            "demand_relation": "supports",
                            "rationale": "short source-grounded explanation",
                            "confidence": "low|medium|high",
                        }
                    ],
                    "unsupported_additions": [
                        {
                            "procedural_span_ids": ["P001"],
                            "target_demand_ids": [],
                            "rationale": "why no source evidence supports it",
                        }
                    ],
                    "summary": "short provisional summary",
                },
                ensure_ascii=False,
                indent=2,
            ),
            "SOURCE EVIDENCE UNITS:",
            normalized.text,
            "PROCEDURAL SPANS:",
            json.dumps(spans, ensure_ascii=False, indent=2),
            "FIXED TARGET DEMAND CARD:",
            json.dumps(target_demand_card, ensure_ascii=False, indent=2),
        ]
    )

    status = "provisional_model_assisted"
    validation_issues: list[str] = []
    annotated_evidence_ids: set[str] = set()
    try:
        annotations = _parse_json_response(
            audit_client(prompt, system_prompt=system)
        )
        alignments = annotations.get("alignments", [])
        unsupported_additions = annotations.get("unsupported_additions", [])
        if not isinstance(alignments, list):
            raise ValueError("annotations.alignments must be a list")
        if not isinstance(unsupported_additions, list):
            raise ValueError("annotations.unsupported_additions must be a list")
        for index, item in enumerate(alignments):
            if not isinstance(item, dict):
                validation_issues.append(f"alignment[{index}] must be an object")
                continue
            bad_evidence = set(item.get("evidence_unit_ids", [])) - evidence_ids
            bad_spans = set(item.get("procedural_span_ids", [])) - span_ids
            bad_demands = set(item.get("target_demand_ids", [])) - demand_ids
            if bad_evidence or bad_spans or bad_demands:
                validation_issues.append(
                    f"alignment[{index}] unknown IDs: "
                    f"evidence={sorted(bad_evidence)}, "
                    f"spans={sorted(bad_spans)}, demands={sorted(bad_demands)}"
                )
            annotated_evidence_ids.update(
                set(item.get("evidence_unit_ids", [])) & evidence_ids
            )
            if item.get("change") not in allowed_changes:
                validation_issues.append(
                    f"alignment[{index}] invalid change label: {item.get('change')!r}"
                )
            if item.get("demand_relation") not in allowed_relations:
                validation_issues.append(
                    "alignment["
                    f"{index}] invalid demand relation: {item.get('demand_relation')!r}"
                )
            if item.get("confidence") not in allowed_confidences:
                validation_issues.append(
                    f"alignment[{index}] invalid confidence: {item.get('confidence')!r}"
                )
        for index, item in enumerate(unsupported_additions):
            if not isinstance(item, dict):
                validation_issues.append(
                    f"unsupported_additions[{index}] must be an object"
                )
                continue
            bad_spans = set(item.get("procedural_span_ids", [])) - span_ids
            bad_demands = set(item.get("target_demand_ids", [])) - demand_ids
            if bad_spans or bad_demands:
                validation_issues.append(
                    f"unsupported_additions[{index}] unknown IDs: "
                    f"spans={sorted(bad_spans)}, demands={sorted(bad_demands)}"
                )
    except Exception as exc:
        status = "generation_failed_requires_review"
        annotations = {
            "alignments": [],
            "unsupported_additions": [],
            "summary": "Semantic audit generation failed; use the saved scaffold.",
        }
        validation_issues.append(type(exc).__name__)

    unannotated_evidence_ids = sorted(evidence_ids - annotated_evidence_ids)
    coverage = {
        "source_unit_count": len(evidence_ids),
        "annotated_source_unit_count": len(annotated_evidence_ids),
        "source_unit_coverage_ratio": (
            len(annotated_evidence_ids) / len(evidence_ids) if evidence_ids else 1.0
        ),
        "unannotated_evidence_unit_ids": unannotated_evidence_ids,
        "interpretation": (
            "Coverage is descriptive. Unannotated units require review and are not "
            "automatically treated as omitted information."
        ),
    }

    ledger = {
        "schema_version": "abstraction-delta-ledger-1.0",
        "annotation_status": status,
        "independent_human_review_required": True,
        "visible_to_task_agent": False,
        "source_payload_sha256": normalized.sha256,
        "allowed_change_labels": sorted(allowed_changes),
        "allowed_demand_relations": sorted(allowed_relations),
        "source_evidence_units": normalized.payload["evidence_units"],
        "procedural_spans": spans,
        "target_demand_card": target_demand_card,
        "annotations": annotations,
        "coverage": coverage,
        "validation_issues": validation_issues,
    }
    json_path = evidence_dir / "abstraction_delta_ledger.json"
    json_path.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md_path = evidence_dir / "abstraction_delta_ledger.md"
    md_path.write_text(
        "\n".join(
            [
                "# Abstraction Delta Ledger",
                "",
                f"- Status: `{status}`",
                f"- Source evidence units: `{len(evidence_ids)}`",
                f"- Procedural spans: `{len(spans)}`",
                f"- Fixed target demands: `{len(demand_ids)}`",
                (
                    "- Annotated source-unit coverage: "
                    f"`{coverage['annotated_source_unit_count']}/{coverage['source_unit_count']}`"
                ),
                "- Visibility: analysis-only; never shown to the task agent",
                "- Interpretation: provisional until independent human review",
                "",
                str(annotations.get("summary", "")),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return json_path, md_path


def seed_procedural_representation(
    *,
    runtime: BaselineRuntime,
    source: ReplayRecord,
    source_task: TaskRecord,
    evidence_dir: Path,
    normalized: NormalizedEvidence,
) -> tuple[dict[str, Any], str]:
    runtime.switch_env(source_task.spec.environment_id)
    if runtime.evolver is None:
        raise RuntimeError("Procedural branch did not construct a SkillAuthor")

    _install_untruncated_induction_prompt(runtime.evolver)
    compacted = CompactedTrajectory(
        task_id=source.task_id,
        n_events=normalized.n_events,
        text=normalized.text,
        n_tokens=len(normalized.text) // 4,
        skills_referenced=[],
        raw_path=normalized.raw_path,
    )
    patch = None
    reused_author_response_index: int | None = None
    author_log = evidence_dir / "llm_calls" / "skill_author.jsonl"
    if author_log.is_file():
        for index, line in enumerate(
            author_log.read_text(encoding="utf-8").splitlines()
        ):
            if not line.strip():
                continue
            try:
                archived = json.loads(line)
                raw_response = str(archived.get("response", ""))
                patch = runtime.evolver._parse_create_patch(
                    raw=raw_response,
                    latent_skill_id=source_task.spec.latent_skill_id,
                    triggered_by_task=source.task_id,
                    proposing_mode="induce_from_archived_response",
                )
            except Exception:
                patch = None
                continue
            reused_author_response_index = index
            print(
                "Reusing complete archived procedural-author response: "
                f"index={index}"
            )
            break
    if patch is None:
        patch = runtime.evolver.induce_skill(
            family_id=source_task.spec.family_id,
            latent_skill_id=source_task.spec.latent_skill_id,
            compacted=compacted,
            outcome=source.outcome,
        )
    apply_result = runtime.freeze_ctrl.submit_patch(
        patch=patch,
        strategy_name=runtime.strategy.name,
        current_task=source_task.spec.task_id,
    )
    if apply_result is None:
        raise RuntimeError("Procedural skill patch was discarded")
    if not runtime.library.has_skill(source_task.spec.latent_skill_id):
        raise RuntimeError("Procedural skill was not present after induction")

    procedural_dir = evidence_dir / "procedural"
    procedural_dir.mkdir(parents=True, exist_ok=True)
    (procedural_dir / "skill_patch.json").write_text(
        patch.model_dump_json(indent=2), encoding="utf-8"
    )
    skill = runtime.library.get_skill(source_task.spec.latent_skill_id)
    skill_md = skill.files.get("SKILL.md", "")
    if not skill_md.strip():
        raise RuntimeError("Induced procedural representation has no SKILL.md")
    (procedural_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
    authoring_manifest = {
        "schema_version": "procedural-authoring-2.0",
        "source_payload_sha256": normalized.sha256,
        "source_payload_chars": len(normalized.text),
        "source_payload_truncated": False,
        "operator": "SkillEvolBench.SkillAuthor.induce_skill",
        "induction_prompt_cap_removed_for_information_parity": True,
        "structured_output": "json_object",
        "deepseek_v4_thinking_for_json_author": "disabled",
        "empty_response_retry_limit": 1,
        "reused_archived_author_response_index": reused_author_response_index,
    }
    (procedural_dir / "authoring_manifest.json").write_text(
        json.dumps(authoring_manifest, indent=2), encoding="utf-8"
    )
    metadata = {
        "skill_id": source_task.spec.latent_skill_id,
        "commit_hash": apply_result.commit_hash,
        "skill_md": str(procedural_dir / "SKILL.md"),
        "patch": str(procedural_dir / "skill_patch.json"),
        "authoring_manifest": str(procedural_dir / "authoring_manifest.json"),
        "representation": "procedural abstraction derived from canonical payload",
        "canonical_payload_sha256": normalized.sha256,
    }
    (procedural_dir / "procedural_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return metadata, skill_md


def audit_branch_representation(
    *,
    condition: str,
    run_dir: Path,
    source_task_id: str,
    eval_task_id: str,
    artifact_text: str | None,
) -> dict[str, Any]:
    instruction_path = run_dir / "runtime" / eval_task_id / "instruction.md"
    instruction = instruction_path.read_text(encoding="utf-8")
    injection_context = json.loads(
        (run_dir / "runtime" / eval_task_id / "injection-context.json").read_text(
            encoding="utf-8"
        )
    )
    has_wrapper = "# Prior Experience Artifact" in instruction
    expected_wrapper = artifact_text is not None
    if has_wrapper != expected_wrapper:
        raise AssertionError(
            f"{condition}: matched artifact wrapper={has_wrapper}, "
            f"expected={expected_wrapper}"
        )
    if artifact_text is not None and artifact_text.rstrip() not in instruction:
        raise AssertionError(f"{condition}: expected artifact text was not injected")
    if artifact_text is not None and source_task_id not in instruction:
        raise AssertionError(f"{condition}: source task id missing from wrapper")
    retrieved_skill_ids = injection_context.get("retrieved_skill_ids", [])
    if retrieved_skill_ids:
        raise AssertionError(
            f"{condition}: native skill retrieval must be disabled: "
            f"{retrieved_skill_ids}"
        )
    return {
        "instruction_path": str(instruction_path),
        "delivery_mode": "matched_prompt",
        "artifact_injected": has_wrapper,
        "artifact_sha256": (
            _sha256_text(artifact_text) if artifact_text is not None else None
        ),
        "native_skill_retrieval_disabled": True,
        "native_skill_ids": retrieved_skill_ids,
    }


def validate_matched_delivery_offline(
    *,
    configs: dict[str, RunConfig],
    normalized: NormalizedEvidence,
    source_task_id: str,
) -> None:
    """Fail fast if execution settings or wrappers reintroduce access bias."""
    for condition, config in configs.items():
        baseline = config.baseline
        if baseline.name != "no_skill":
            raise AssertionError(f"{condition}: execution baseline is not no_skill")
        if baseline.use_skill_library or baseline.use_trajectory_rag:
            raise AssertionError(f"{condition}: native artifact retrieval is enabled")
        if baseline.use_history_context:
            raise AssertionError(f"{condition}: history context is enabled")

    if not configs:
        raise AssertionError("at least one execution config is required")
    reference_config = next(iter(configs.values()))
    kwargs = {
        "original_instruction": "TARGET",
        "baseline": reference_config.baseline,
        "task": None,
        "retrieved_skills": [],
        "retrieved_trajectories": [],
        "history_context": None,
        "library_frozen": False,
    }
    no_artifact = MatchedArtifactPromptBuilder(
        artifact_text=None,
        source_task_id=source_task_id,
    ).build(**kwargs)
    episodic = MatchedArtifactPromptBuilder(
        artifact_text=normalized.text,
        source_task_id=source_task_id,
    ).build(**kwargs)
    procedural_probe = "PROCEDURAL-PROBE"
    procedural = MatchedArtifactPromptBuilder(
        artifact_text=procedural_probe,
        source_task_id=source_task_id,
    ).build(**kwargs)
    if no_artifact != "TARGET":
        raise AssertionError("No Artifact must preserve the original instruction")
    if episodic.replace(normalized.text, "<ARTIFACT>") != procedural.replace(
        procedural_probe, "<ARTIFACT>"
    ):
        raise AssertionError("Episodic and Procedural prompt wrappers differ")


def validate_ledger_offline(
    *,
    normalized: NormalizedEvidence,
    target_demand_card: dict[str, Any],
) -> None:
    """Exercise ledger generation with a deterministic, non-network stub."""
    first_evidence = normalized.payload["evidence_units"][0]["evidence_unit_id"]
    demand_ids = [
        item["target_demand_id"] for item in target_demand_card["demands"][:1]
    ]

    def audit_stub(prompt: str, *, system_prompt: str | None = None) -> str:
        if "SOURCE EVIDENCE UNITS" not in prompt or not system_prompt:
            raise AssertionError("Audit prompt is missing required sections")
        return json.dumps(
            {
                "alignments": [
                    {
                        "evidence_unit_ids": [first_evidence],
                        "procedural_span_ids": ["P001"],
                        "change": "preserved",
                        "target_demand_ids": demand_ids,
                        "demand_relation": "supports",
                        "rationale": "offline schema check",
                        "confidence": "high",
                    }
                ],
                "unsupported_additions": [],
                "summary": "offline schema check",
            }
        )

    with tempfile.TemporaryDirectory(prefix="paired-mvp-ledger-") as tmp:
        json_path, _ = generate_abstraction_delta_ledger(
            evidence_dir=Path(tmp),
            normalized=normalized,
            skill_md="# Procedure\n\n1. Verify the relevant condition.",
            target_demand_card=target_demand_card,
            audit_client=audit_stub,
        )
        ledger = json.loads(json_path.read_text(encoding="utf-8"))
        if ledger["annotation_status"] != "provisional_model_assisted":
            raise AssertionError("Offline ledger stub did not pass validation")
        if ledger["visible_to_task_agent"]:
            raise AssertionError("Ledger must remain analysis-only")
        if ledger["validation_issues"]:
            raise AssertionError(ledger["validation_issues"])


def validate_checkpoint_helpers_offline() -> None:
    """Exercise branch selection and non-destructive resume checkpoints."""
    if parse_conditions("procedural,no_artifact,procedural") != (
        "no_artifact",
        "procedural",
    ):
        raise AssertionError("condition parsing is not stable or de-duplicated")
    with tempfile.TemporaryDirectory(prefix="paired-mvp-resume-") as tmp:
        root = Path(tmp)
        branches = root / "branches"
        if next_run_id(branches, "episodic") != "episodic":
            raise AssertionError("fresh branch did not use its canonical run ID")
        incomplete = branches / "episodic"
        incomplete.mkdir(parents=True)
        (incomplete / "partial.log").write_text("partial", encoding="utf-8")
        if next_run_id(branches, "episodic") != "episodic__retry1":
            raise AssertionError("incomplete branch would not use a retry directory")
        completed = branches / "no_artifact"
        completed.mkdir(parents=True)
        harbor_result = completed / "harbor-job" / "no_artifact" / "trial" / "result.json"
        harbor_result.parent.mkdir(parents=True)
        harbor_result.write_text(
            json.dumps(
                {
                    "task_name": "TARGET",
                    "exception_info": None,
                    "agent_result": {"n_input_tokens": 1},
                }
            ),
            encoding="utf-8",
        )
        (completed / "paired_branch_result.json").write_text(
            json.dumps(
                {
                    "condition": "no_artifact",
                    "source_task_id": "SOURCE",
                    "target_task_id": "TARGET",
                    "normalized_score": 1.0,
                    "run_dir": str(completed),
                }
            ),
            encoding="utf-8",
        )
        loaded = load_completed_branch_results(
            mvp_dir=root,
            source_task_id="SOURCE",
            target_task_id="TARGET",
        )
        if set(loaded) != {"no_artifact"}:
            raise AssertionError("resume loader accepted an incomplete branch")


async def run_branch(
    *,
    condition: str,
    config: RunConfig,
    registry: TaskRegistry,
    source: ReplayRecord,
    eval_task: TaskRecord,
    artifact_text: str | None,
    artifact_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    runner = LifelongRunner(config=config)
    runner._preflight()
    runtime = BaselineRuntime.build(config)
    matched_prompt_builder = MatchedArtifactPromptBuilder(
        artifact_text=artifact_text,
        source_task_id=source.task_id,
    )
    runtime.runtime_builder.prompt_builder = matched_prompt_builder
    runner._persist_run_config(runtime.run_root)
    benchmark_hash = runner._snapshot_benchmark_hash(runtime.run_root)

    from harbor.job import Job
    from skillevolbench.harbor_ext import SkillEvolBenchHooks
    from skillevolbench.harbor_ext._patches import apply_harbor_patches
    from skillevolbench.harbor_ext.job_builder import build_job_config

    apply_harbor_patches()
    job = await Job.create(build_job_config(config, [eval_task]))
    hooks = SkillEvolBenchHooks(
        runtime=runtime,
        task_registry=registry,
        runtime_builder=runtime.runtime_builder,
        prompt_builder=matched_prompt_builder,
    )
    job.on_trial_started(hooks.on_trial_started)
    job.on_trial_ended(hooks.on_trial_ended)
    runtime.event_store.record(
        "paired_branch_started",
        {
            "condition": condition,
            "source_task_id": source.task_id,
            "target_task_id": eval_task.spec.task_id,
        },
    )

    try:
        await job.run()
    finally:
        if hooks._current_env is not None:
            await hooks._handle_env_transition(hooks._current_env, "END")
            hooks._current_env = None
        runner._finalise(runtime, hooks, benchmark_hash)

    trial_status = load_harbor_trial_status(
        run_dir=runtime.run_root,
        target_task_id=eval_task.spec.task_id,
    )
    if trial_status is None:
        raise BranchInfrastructureError(
            f"{condition}: Harbor did not produce an authoritative result.json"
        )
    if not trial_status["agent_completed"]:
        message = str(trial_status.get("exception_message") or "")
        failure = {
            "schema_version": "paired-branch-failure-1.0",
            "condition": condition,
            "source_task_id": source.task_id,
            "target_task_id": eval_task.spec.task_id,
            "status": "infrastructure_failure",
            "exception_type": trial_status.get("exception_type"),
            "exception_message_excerpt": message[:4000],
            "trial_result": trial_status.get("result_path"),
            "agent_input_tokens": trial_status.get("agent_input_tokens", 0),
            "agent_output_tokens": trial_status.get("agent_output_tokens", 0),
            "agent_cache_tokens": trial_status.get("agent_cache_tokens", 0),
            "agent_cost_usd_estimate": trial_status.get(
                "agent_cost_usd_estimate", 0.0
            ),
            "research_result_valid": False,
        }
        failure_path = runtime.run_root / "paired_branch_failure.json"
        failure_path.write_text(json.dumps(failure, indent=2), encoding="utf-8")
        raise BranchInfrastructureError(
            f"{condition}: Agent failed with {failure['exception_type']}; "
            f"checkpoint={failure_path}"
        )

    report_gen = ReportGenerator(
        runtime.run_root,
        config,
        task_registry=registry,
        host_llm_clients=runtime.host_llm_clients,
    )
    report = report_gen.generate()
    report_path = report_gen.write(report)
    target = runtime.replay_store.get(eval_task.spec.task_id)
    audit = audit_branch_representation(
        condition=condition,
        run_dir=runtime.run_root,
        source_task_id=source.task_id,
        eval_task_id=eval_task.spec.task_id,
        artifact_text=artifact_text,
    )
    result = {
        "condition": condition,
        "baseline": config.baseline.name,
        "source_task_id": source.task_id,
        "target_task_id": eval_task.spec.task_id,
        "verifier_passed": target.outcome.verifier_passed,
        "normalized_score": target.outcome.normalized_score,
        "reward": target.outcome.reward,
        "outcome_passed": target.outcome.outcome_passed,
        "process_passed": target.outcome.process_passed,
        "failed_tests": _jsonable_list(target.outcome.failed_tests),
        "rubric_dimensions": _jsonable_list(target.outcome.rubric_dimensions),
        "agent_input_tokens": target.outcome.n_input_tokens,
        "agent_output_tokens": target.outcome.n_output_tokens,
        "agent_cache_tokens": target.outcome.n_cache_tokens,
        "agent_cost_usd_estimate": target.outcome.cost_usd,
        "total_cost_usd_estimate": report.cost.get("total_cost_usd", 0.0),
        "artifact": artifact_metadata,
        "activation_audit": audit,
        "agent_completed_without_exception": True,
        "trial_result": trial_status["result_path"],
        "run_dir": str(runtime.run_root),
        "report": str(report_path),
    }
    (runtime.run_root / "paired_branch_result.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    return result


def write_summary(
    *,
    mvp_dir: Path,
    source_run: Path,
    source_task: TaskRecord,
    eval_task: TaskRecord,
    results: list[dict[str, Any]],
) -> tuple[Path, Path]:
    by_condition = {item["condition"]: item for item in results}
    no_score = by_condition["no_artifact"]["normalized_score"]
    episodic_score = by_condition["episodic"]["normalized_score"]
    procedural_score = by_condition["procedural"]["normalized_score"]
    deltas = {
        "episodic_minus_no_artifact": episodic_score - no_score,
        "procedural_minus_no_artifact": procedural_score - no_score,
        "procedural_minus_episodic": procedural_score - episodic_score,
    }
    summary = {
        "schema_version": "paired-mvp-2.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_run": str(source_run),
        "source_task_id": source_task.spec.task_id,
        "target_task_id": eval_task.spec.task_id,
        "family_id": source_task.spec.family_id,
        "n_source_experiences": 1,
        "n_target_tasks": 1,
        "delivery_mode": "matched_prompt",
        "native_retrieval_disabled": True,
        "results": results,
        "score_deltas": deltas,
        "interpretation_limit": (
            "Single-source, single-target diagnostic MVP; not statistical evidence."
        ),
    }
    json_path = mvp_dir / "paired_summary.json"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    rows = []
    for condition in CONDITION_BASELINES:
        item = by_condition[condition]
        rows.append(
            f"| {condition} | {item['baseline']} | "
            f"{item['normalized_score']:.3f} | "
            f"{'PASS' if item['verifier_passed'] else 'FAIL'} |"
        )
    markdown = "\n".join(
        [
            "# Same-Source Paired MVP Result",
            "",
            f"- Source: `{source_task.spec.task_id}`",
            f"- Target: `{eval_task.spec.task_id}`",
            f"- Family: `{source_task.spec.family_id}`",
            "- Scope: one source experience and one held-out target task",
            "- Delivery: matched prompt wrapper; native retrieval disabled",
            "",
            "| Condition | Baseline | Score | Outcome |",
            "|---|---|---:|---|",
            *rows,
            "",
            "## Score deltas",
            "",
            f"- Episodic - No Artifact: `{deltas['episodic_minus_no_artifact']:.3f}`",
            f"- Procedural - No Artifact: `{deltas['procedural_minus_no_artifact']:.3f}`",
            f"- Procedural - Episodic: `{deltas['procedural_minus_episodic']:.3f}`",
            "",
            "> This is a diagnostic MVP, not statistical evidence.",
            "",
        ]
    )
    md_path = mvp_dir / "paired_summary.md"
    md_path.write_text(markdown, encoding="utf-8")
    return json_path, md_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-task-id", default="E1-LS1-T1")
    parser.add_argument("--target-task-id", default="E1-LS1-T4")
    parser.add_argument("--source-run-dir", type=Path)
    parser.add_argument("--model-preset", default="gemini-3-flash")
    parser.add_argument("--order-seed", choices=("A", "B", "C"), default="A")
    parser.add_argument("--mvp-id")
    parser.add_argument(
        "--conditions",
        type=parse_conditions,
        default=parse_conditions("all"),
        metavar="LIST",
        help="comma-separated no_artifact,episodic,procedural, or all",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="reuse completed branch and procedural checkpoints for --mvp-id",
    )
    parser.add_argument(
        "--skip-ledger",
        action="store_true",
        help="skip the optional model-assisted abstraction audit",
    )
    parser.add_argument(
        "--author-max-tokens",
        type=int,
        default=4096,
        help="maximum procedural-author output tokens",
    )
    parser.add_argument(
        "--allow-cross-model-source",
        action="store_true",
        help="explicitly permit source and target Agent models to differ",
    )
    parser.add_argument(
        "--reuse-procedural-from",
        type=Path,
        help=(
            "reuse a frozen procedural representation from another MVP directory; "
            "the canonical source-evidence hash must match"
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--confirm-run",
        action="store_true",
        help="required for real API execution",
    )
    return parser


async def async_main(args: argparse.Namespace) -> int:
    if args.author_max_tokens < 1:
        raise SystemExit("--author-max-tokens must be positive")
    if args.resume and not args.mvp_id:
        raise SystemExit("--resume requires an explicit --mvp-id")

    source_run = args.source_run_dir or discover_source_run(args.source_task_id)
    source_run = source_run.resolve()
    source = load_source_evidence(source_run, args.source_task_id)
    registry = TaskRegistry.from_disk(default_skills_root(), default_tasks_root())
    source_task = registry.task(args.source_task_id)
    eval_task = registry.task(args.target_task_id)
    validate_pair(registry, source, source_task, eval_task)
    model_path = resolve_model_preset(args.model_preset)
    if not model_path.is_file():
        raise SystemExit(f"Unknown model preset: {model_path}")
    model_preset = yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}
    target_agent_model = str(model_preset.get("agent_model_name", ""))
    source_model = source_agent_model(source_run, args.source_task_id)
    if (
        normalize_model_identity(source_model)
        != normalize_model_identity(target_agent_model)
        and not args.allow_cross_model_source
    ):
        raise SystemExit(
            "Source/target model mismatch: "
            f"source={source_model!r}, target={target_agent_model!r}. "
            "Generate a same-model source run or pass --allow-cross-model-source."
        )
    normalized = build_normalized_evidence(
        source=source,
        source_task=source_task,
    )
    target_demand_card = build_target_demand_card(eval_task)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    mvp_id = args.mvp_id or (
        f"paired__{args.source_task_id}__to__{args.target_task_id}__{timestamp}"
    )
    if (
        not mvp_id
        or mvp_id.startswith(".")
        or "/" in mvp_id
        or "\\" in mvp_id
        or any(char.isspace() for char in mvp_id)
    ):
        raise SystemExit(f"unsafe --mvp-id: {mvp_id!r}")
    mvp_dir = PAIRED_ROOT / mvp_id
    if args.resume:
        if not mvp_dir.is_dir():
            raise SystemExit(f"resume target does not exist: {mvp_dir}")
    elif mvp_dir.exists():
        raise SystemExit(f"MVP output already exists; use --resume: {mvp_dir}")

    selected_conditions = tuple(args.conditions)
    completed_results = (
        load_completed_branch_results(
            mvp_dir=mvp_dir,
            source_task_id=source.task_id,
            target_task_id=eval_task.spec.task_id,
        )
        if args.resume
        else {}
    )
    pending_conditions = tuple(
        condition
        for condition in selected_conditions
        if condition not in completed_results
    )
    branches_root = mvp_dir / "branches"
    configs = {
        condition: build_config(
            condition=condition,
            run_id=next_run_id(branches_root, condition),
            model_preset=args.model_preset,
            mvp_dir=mvp_dir,
            order_seed=args.order_seed,
        )
        for condition in pending_conditions
    }

    cached_procedural = None
    reusable_procedural_dir: Path | None = None
    if mvp_dir.is_dir():
        cached_procedural = load_cached_procedural_representation(
            evidence_dir=mvp_dir / "evidence",
            normalized=normalized,
        )
    if cached_procedural is None and args.reuse_procedural_from is not None:
        metadata, text, reusable_procedural_dir = load_reusable_procedural_representation(
            source_path=args.reuse_procedural_from,
            normalized=normalized,
        )
        cached_procedural = (metadata, text)
    needs_authoring = "procedural" in pending_conditions and cached_procedural is None
    authoring_config = None
    if needs_authoring:
        authoring_config = build_authoring_config(
            run_id=next_run_id(mvp_dir / "authoring", "procedural_author"),
            model_preset=args.model_preset,
            mvp_dir=mvp_dir,
            order_seed=args.order_seed,
            author_max_tokens=args.author_max_tokens,
        )

    # Validate only work that has not already produced a complete checkpoint.
    for config in configs.values():
        LifelongRunner(config=config)._preflight()
    if authoring_config is not None:
        LifelongRunner(config=authoring_config)._preflight()
    if configs:
        validate_matched_delivery_offline(
            configs=configs,
            normalized=normalized,
            source_task_id=source.task_id,
        )
    validate_ledger_offline(
        normalized=normalized,
        target_demand_card=target_demand_card,
    )
    validate_checkpoint_helpers_offline()

    print(f"Source run: {source_run}")
    print(f"Source evidence: {args.source_task_id} (verified PASS)")
    print(f"Source Agent model: {source_model}")
    print(f"Target Agent model: {target_agent_model}")
    print(f"Raw trajectory: {normalized.raw_path}")
    print(
        "Normalized evidence: "
        f"events={normalized.n_events} units={normalized.n_units} "
        f"chars={len(normalized.text)} sha256={normalized.sha256}"
    )
    print(f"Held-out target: {args.target_task_id}")
    print(f"Fixed explicit target demands: {len(target_demand_card['demands'])}")
    print(f"Separated resource hints: {len(target_demand_card['resource_hints'])}")
    print(f"Selected conditions: {', '.join(selected_conditions)}")
    print(f"Completed checkpoints: {', '.join(completed_results) or 'none'}")
    print(f"Pending conditions: {', '.join(pending_conditions) or 'none'}")
    print(f"Ledger: {'skipped' if args.skip_ledger else 'post-run audit'}")
    print(f"Procedural author max tokens: {args.author_max_tokens}")
    print("Delivery: matched prompt wrapper (native retrieval disabled)")
    print(f"Output: {mvp_dir}")
    if args.dry_run:
        print("Paired MVP dry-run: PASS (no API or Docker task executed)")
        return 0
    if not args.confirm_run:
        raise SystemExit("Real execution requires --confirm-run")

    if not args.resume:
        mvp_dir.mkdir(parents=True, exist_ok=False)
    evidence_dir = ensure_evidence_packet(
        mvp_dir=mvp_dir,
        source_run=source_run,
        source=source,
        source_task=source_task,
        eval_task=eval_task,
        normalized=normalized,
        target_demand_card=target_demand_card,
    )
    if reusable_procedural_dir is not None:
        local_procedural_dir = evidence_dir / "procedural"
        if local_procedural_dir.exists():
            local_loaded = load_cached_procedural_representation(
                evidence_dir=evidence_dir,
                normalized=normalized,
            )
            if local_loaded is None:
                raise RuntimeError(
                    f"Local procedural checkpoint is incomplete: {local_procedural_dir}"
                )
        else:
            shutil.copytree(reusable_procedural_dir, local_procedural_dir)
        (local_procedural_dir / "reuse_manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "procedural-reuse-1.0",
                    "source_directory": str(reusable_procedural_dir),
                    "source_payload_sha256": normalized.sha256,
                    "reason": "freeze one abstraction across paired target repetitions",
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    artifacts: dict[str, tuple[str | None, dict[str, Any] | None]] = {
        "no_artifact": (None, None),
        "episodic": (
            normalized.text,
            {
                "representation": "normalized episodic event stream",
                "canonical_payload": str(
                    evidence_dir / "normalized_source_evidence.json"
                ),
                "canonical_payload_sha256": normalized.sha256,
                "semantic_event_selection": False,
                "semantic_truncation": False,
            },
        ),
    }
    install_harbor_compat()

    results_by_condition = dict(completed_results)
    procedural_metadata: dict[str, Any] | None = None
    procedural_text: str | None = None
    authoring_runtime: BaselineRuntime | None = None
    if cached_procedural is not None:
        procedural_metadata, procedural_text = cached_procedural

    # Stable order gives two cheap infrastructure checks before skill authoring.
    for condition in pending_conditions:
        if condition == "procedural" and procedural_text is None:
            if authoring_config is None:
                raise RuntimeError("missing procedural authoring configuration")
            print("Authoring procedural representation from canonical evidence")
            # Capture the host-side author prompt/response for audit. The
            # directory is local experiment state and is never shown to T4.
            previous_dump_dir = os.environ.get("SEVB_DUMP_PROMPTS")
            os.environ["SEVB_DUMP_PROMPTS"] = str(evidence_dir / "llm_calls")
            try:
                authoring_runtime = BaselineRuntime.build(authoring_config)
            finally:
                if previous_dump_dir is None:
                    os.environ.pop("SEVB_DUMP_PROMPTS", None)
                else:
                    os.environ["SEVB_DUMP_PROMPTS"] = previous_dump_dir
            procedural_metadata, procedural_text = seed_procedural_representation(
                runtime=authoring_runtime,
                source=source,
                source_task=source_task,
                evidence_dir=evidence_dir,
                normalized=normalized,
            )
        if condition == "procedural":
            if procedural_metadata is None or procedural_text is None:
                raise RuntimeError("procedural artifact checkpoint is incomplete")
            artifacts["procedural"] = (procedural_text, procedural_metadata)

        print(f"Running paired branch: {condition}")
        artifact_text, artifact_metadata = artifacts[condition]
        result = await run_branch(
            condition=condition,
            config=configs[condition],
            registry=registry,
            source=source,
            eval_task=eval_task,
            artifact_text=artifact_text,
            artifact_metadata=artifact_metadata,
        )
        results_by_condition[condition] = result
        print(
            f"  {condition}: score={result['normalized_score']:.3f} "
            f"passed={result['verifier_passed']}"
        )

    ledger_json: Path | None = None
    ledger_path = evidence_dir / "abstraction_delta_ledger.json"
    if not args.skip_ledger and procedural_text is not None:
        if ledger_path.is_file():
            ledger_json = ledger_path
            print(f"Reusing abstraction ledger: {ledger_json}")
        else:
            if authoring_runtime is None:
                audit_config = build_authoring_config(
                    run_id=next_run_id(mvp_dir / "authoring", "procedural_audit"),
                    model_preset=args.model_preset,
                    mvp_dir=mvp_dir,
                    order_seed=args.order_seed,
                    author_max_tokens=args.author_max_tokens,
                )
                LifelongRunner(config=audit_config)._preflight()
                authoring_runtime = BaselineRuntime.build(audit_config)
            if not authoring_runtime.host_llm_clients:
                raise RuntimeError("No audit-capable Gemini client is available")
            ledger_json, ledger_md = generate_abstraction_delta_ledger(
                evidence_dir=evidence_dir,
                normalized=normalized,
                skill_md=procedural_text,
                target_demand_card=target_demand_card,
                audit_client=authoring_runtime.host_llm_clients[-1],
            )
            print(f"Generated abstraction ledger: {ledger_json}")
            print(f"Generated ledger summary: {ledger_md}")

    ordered_results = [
        results_by_condition[name]
        for name in CONDITION_BASELINES
        if name in results_by_condition
    ]
    progress = {
        "schema_version": "paired-mvp-progress-1.0",
        "source_task_id": source.task_id,
        "target_task_id": eval_task.spec.task_id,
        "completed_conditions": [item["condition"] for item in ordered_results],
        "missing_conditions": [
            name for name in CONDITION_BASELINES if name not in results_by_condition
        ],
        "results": ordered_results,
    }
    progress_path = mvp_dir / "paired_progress.json"
    progress_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")

    if len(results_by_condition) == len(CONDITION_BASELINES):
        json_path, md_path = write_summary(
            mvp_dir=mvp_dir,
            source_run=source_run,
            source_task=source_task,
            eval_task=eval_task,
            results=ordered_results,
        )
        print("Paired MVP run: COMPLETE")
        print(f"  summary_json={json_path}")
        print(f"  summary_md={md_path}")
    else:
        print("Paired MVP run: PARTIAL CHECKPOINT")
        print(f"  progress_json={progress_path}")
    if ledger_json is not None:
        print(f"  abstraction_ledger={ledger_json}")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
