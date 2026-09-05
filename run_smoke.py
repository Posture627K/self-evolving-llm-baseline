"""Run a bounded real-model SkillEvolBench smoke test.

This launcher uses the upstream RunConfig.max_tasks fixture knob without
modifying the pinned SkillEvolBench checkout. Its output is diagnostic only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path


from runtime_paths import RUNTIME_ROOT
REPO_ROOT = RUNTIME_ROOT / "SkillEvolBench"
WORKSPACE_ROOT = REPO_ROOT / "workspace" / "runs"
LOCAL_MODEL_PRESETS = Path(__file__).resolve().parent / "model_presets"

sys.path.insert(0, str(REPO_ROOT))

from scripts.run import _apply_model_preset  # noqa: E402
from harbor_compat import install as install_harbor_compat  # noqa: E402
from skillevolbench.baselines import BaselineRuntime, load_baseline  # noqa: E402
from skillevolbench.discovery import (  # noqa: E402
    TaskRegistry,
    default_skills_root,
    default_tasks_root,
)
from skillevolbench.metrics.reporter import ReportGenerator  # noqa: E402
from skillevolbench.orchestration import LifelongRunner  # noqa: E402
from skillevolbench.schemas import RunConfig, StrategyConfig  # noqa: E402


def collect_agent_failures(run_dir: Path) -> list[dict[str, str]]:
    """Reject Harbor bookkeeping results produced after an Agent exception."""
    failures: list[dict[str, str]] = []
    for path in (run_dir / "harbor-job").glob("**/result.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        exception = payload.get("exception_info")
        if not isinstance(exception, dict):
            continue
        failures.append(
            {
                "task_name": str(payload.get("task_name", "unknown")),
                "exception_type": str(exception.get("exception_type", "unknown")),
                "result_path": str(path),
            }
        )
    return failures


def load_replay_records(run_dir: Path) -> list[tuple[Path, dict]]:
    """Load persisted per-task replay JSON without opening replay.db."""
    records_dir = run_dir / "stores" / "replay" / "records"
    records: list[tuple[Path, dict]] = []
    for path in sorted(records_dir.glob("*.json")):
        try:
            records.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError):
            continue
    return records


def replay_validation_summary(record: dict) -> dict:
    """Extract the fields that decide whether a source experience is valid."""
    outcome = record.get("outcome") or {}
    return {
        "task_id": record.get("task_id", outcome.get("task_id", "unknown")),
        "normalized_score": float(outcome.get("normalized_score", 0.0) or 0.0),
        "outcome_passed": outcome.get("outcome_passed"),
        "process_passed": outcome.get("process_passed"),
        "verifier_passed": bool(outcome.get("verifier_passed", False)),
        "cost_usd": float(outcome.get("cost_usd", 0.0) or 0.0),
        "reported_cost_usd": float(outcome.get("reported_cost_usd", 0.0) or 0.0),
        "cost_source": str(outcome.get("cost_source", "")),
        "cost_pricing_tier": str(outcome.get("cost_pricing_tier", "")),
        "trajectory_path": str(outcome.get("trajectory_path", "")),
        "failed_tests": [
            str(item.get("name", "unknown"))
            for item in (outcome.get("failed_tests") or [])
            if isinstance(item, dict)
        ],
    }


def source_is_fully_valid(summary: dict) -> bool:
    """Require both verifier groups, not only a positive partial reward."""
    return (
        summary.get("verifier_passed") is True
        and summary.get("outcome_passed") is True
        and summary.get("process_passed") is True
    )


def print_replay_validation(summary: dict) -> None:
    print(f"  task_id={summary['task_id']}")
    print(f"  normalized_score={summary['normalized_score']:.3f}")
    print(f"  outcome_passed={summary['outcome_passed']}")
    print(f"  process_passed={summary['process_passed']}")
    print(f"  verifier_passed={summary['verifier_passed']}")
    print(f"  source_valid={source_is_fully_valid(summary)}")
    print(
        f"  estimated_cost_usd={summary['cost_usd']:.6f} "
        f"source={summary['cost_source']} tier={summary['cost_pricing_tier']}"
    )
    if summary["reported_cost_usd"]:
        print(f"  agent_reported_cost_usd={summary['reported_cost_usd']:.6f}")
    print(f"  trajectory={summary['trajectory_path']}")
    if summary["failed_tests"]:
        print(f"  failed_tests={','.join(summary['failed_tests'])}")


def build_config(args: argparse.Namespace) -> RunConfig:
    baseline = load_baseline(args.baseline_name)
    local_model_path = LOCAL_MODEL_PRESETS / f"{args.model_preset}.yaml"
    model_path = (
        local_model_path
        if local_model_path.is_file()
        else REPO_ROOT / "configs" / "models" / f"{args.model_preset}.yaml"
    )
    if not model_path.is_file():
        raise SystemExit(f"Unknown model preset: {args.model_preset}")

    baseline, model_short_id = _apply_model_preset(baseline, model_path)
    strategy_name = baseline.default_strategy
    if strategy_name == "none":
        strategy_name = "chain"
    strategy = StrategyConfig.from_yaml(
        REPO_ROOT / "configs" / "strategies" / f"{strategy_name}.yaml"
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    selected = f"__{args.task_id}" if getattr(args, "task_id", None) else ""
    run_id = getattr(args, "run_id", None) or (
        f"smoke__{baseline.name}__{model_short_id}{selected}__"
        f"seed{args.order_seed}__n{args.max_tasks}__{timestamp}"
    )
    return RunConfig(
        run_id=run_id,
        baseline=baseline,
        strategy=strategy,
        order_seed=args.order_seed,
        workspace_root=WORKSPACE_ROOT,
        max_tasks=args.max_tasks,
    )


async def run_selected_task(config: RunConfig, task_id: str):
    """Run exactly one named task while preserving normal Harbor artifacts."""
    runner = LifelongRunner(config=config)
    runner._preflight()
    registry = TaskRegistry.from_disk(default_skills_root(), default_tasks_root())
    task = registry.task(task_id)
    if task.spec.phase.value != "learning":
        raise ValueError(f"Selected smoke source must be a learning task: {task_id}")

    runtime = BaselineRuntime.build(config)
    runner._persist_run_config(runtime.run_root)
    benchmark_hash = runner._snapshot_benchmark_hash(runtime.run_root)

    from harbor.job import Job
    from skillevolbench.harbor_ext import SkillEvolBenchHooks
    from skillevolbench.harbor_ext._patches import apply_harbor_patches
    from skillevolbench.harbor_ext.job_builder import build_job_config

    apply_harbor_patches()
    job = await Job.create(build_job_config(config, [task]))
    prompt_builder = runtime.runtime_builder.prompt_builder
    hooks = SkillEvolBenchHooks(
        runtime=runtime,
        task_registry=registry,
        runtime_builder=runtime.runtime_builder,
        prompt_builder=prompt_builder,
    )
    job.on_trial_started(hooks.on_trial_started)
    job.on_trial_ended(hooks.on_trial_ended)
    try:
        await job.run()
    finally:
        if hooks._current_env is not None:
            await hooks._handle_env_transition(hooks._current_env, "END")
            hooks._current_env = None
        runner._finalise(runtime, hooks, benchmark_hash)

    report_gen = ReportGenerator(
        runtime.run_root,
        config,
        task_registry=registry,
        host_llm_clients=runtime.host_llm_clients,
    )
    report = report_gen.generate()
    report_gen.write(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-name", default="no_skill")
    parser.add_argument("--model-preset", default="gemini-3-flash")
    parser.add_argument("--order-seed", choices=("A", "B", "C"), default="A")
    parser.add_argument("--max-tasks", type=int, default=1)
    parser.add_argument(
        "--task-id",
        help="run exactly one named learning task instead of the seeded prefix",
    )
    parser.add_argument("--run-id")
    parser.add_argument(
        "--require-verifier-pass",
        action="store_true",
        help="Return non-zero unless every smoke replay is fully source-valid.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.max_tasks < 1:
        raise SystemExit("--max-tasks must be at least 1")
    if args.task_id and args.max_tasks != 1:
        raise SystemExit("--task-id requires --max-tasks 1")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = build_config(args)
    print(f"Smoke run: {config.run_id}")
    print(
        f"  baseline={config.baseline.name} model={args.model_preset} "
        f"max_tasks={config.max_tasks}"
    )

    if args.dry_run:
        LifelongRunner(config=config)._preflight()
        print("Smoke dry-run: PASS (no API or Docker task executed)")
        return 0

    install_harbor_compat()
    report = (
        asyncio.run(run_selected_task(config, args.task_id))
        if args.task_id
        else asyncio.run(LifelongRunner(config=config).run())
    )
    report_path = config.run_dir / "reports" / "full_report.json"
    failures = collect_agent_failures(config.run_dir)
    if failures:
        failure_path = config.run_dir / "smoke_agent_failures.json"
        failure_path.write_text(json.dumps(failures, indent=2), encoding="utf-8")
        raise SystemExit(
            f"Smoke run failed in the Agent phase; details={failure_path}"
        )
    print("Smoke run: COMPLETE")
    print(f"  attempted={report.n_tasks_attempted}")
    print(f"  overall_sr={report.task_success.get('overall_sr', 0):.3f}")
    print(f"  report={report_path}")
    replay_records = load_replay_records(config.run_dir)
    if not replay_records:
        raise SystemExit("Smoke run produced no replay records")
    summaries = [replay_validation_summary(record) for _, record in replay_records]
    for summary in summaries:
        print_replay_validation(summary)
    if args.require_verifier_pass and not all(
        source_is_fully_valid(summary) for summary in summaries
    ):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
