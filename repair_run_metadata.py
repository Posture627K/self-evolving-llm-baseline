"""Repair trajectory and provider-cost metadata in completed local runs."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


from runtime_paths import REPO_ROOT as RUNTIME_REPO
sys.path.insert(0, str(RUNTIME_REPO))

from skillevolbench.components.compactor import TrajectoryCompactor
from skillevolbench.metrics.cost import (
    DEEPSEEK_PRICING_SNAPSHOT,
    compute_cost_usd,
    pricing_tier_for_model,
)
from skillevolbench.stores import ReplayStore


def utc_from_run_id(run_id: str) -> datetime | None:
    match = re.search(r"__(\d{8}_\d{6})$", run_id)
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y%m%d_%H%M%S").replace(
        tzinfo=timezone.utc
    )


def resolve_trajectory(trial_dir: Path) -> Path | None:
    for candidate in (
        trial_dir / "agent" / "trajectory.json",
        trial_dir / "artifacts" / "logs" / "agent" / "trajectory.json",
        trial_dir / "artifacts" / "trajectory.json",
        trial_dir / "agent" / "gemini-cli.trajectory.json",
        trial_dir / "agent" / "gemini-cli.trajectory.jsonl",
    ):
        if candidate.is_file():
            return candidate
    return None


def backup_once(path: Path) -> None:
    if not path.is_file():
        return
    backup = path.with_suffix(path.suffix + ".pre_metadata_repair")
    if not backup.exists():
        shutil.copy2(path, backup)


def repair_report(run_dir: Path, records: list) -> None:
    report_path = run_dir / "reports" / "full_report.json"
    if not report_path.is_file():
        return
    backup_once(report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    section = report.setdefault("cost", {})
    n_tasks = len(records)
    n_passed = sum(1 for record in records if record.outcome.verifier_passed)
    agent_total = round(sum(record.outcome.cost_usd for record in records), 6)
    reported_total = round(
        sum(record.outcome.reported_cost_usd for record in records), 6
    )
    source_breakdown: dict[str, int] = {}
    for record in records:
        source = record.outcome.cost_source or "unknown"
        source_breakdown[source] = source_breakdown.get(source, 0) + 1
    section.update(
        {
            "agent_total_cost_usd": agent_total,
            "agent_reported_total_cost_usd": reported_total,
            "agent_input_tokens": sum(r.outcome.n_input_tokens for r in records),
            "agent_output_tokens": sum(r.outcome.n_output_tokens for r in records),
            "agent_cache_tokens": sum(r.outcome.n_cache_tokens for r in records),
            "agent_cost_per_task_usd": round(agent_total / n_tasks, 6)
            if n_tasks
            else 0.0,
            "agent_cost_source_breakdown": source_breakdown,
        }
    )
    host_total = float(section.get("host_total_cost_usd", 0.0) or 0.0)
    total = round(agent_total + host_total, 6)
    section["total_cost_usd"] = total
    section["total_cost_per_task_usd"] = (
        round(total / n_tasks, 6) if n_tasks else 0.0
    )
    section["total_cost_per_successful_task_usd"] = (
        round(total / n_passed, 6) if n_passed else 0.0
    )
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def repair_run(run_dir: Path, model_preset: str) -> dict:
    store = ReplayStore(run_dir / "stores" / "replay")
    records = store.all_records()
    at_time = utc_from_run_id(run_dir.name)
    summaries = []
    for record in records:
        json_path = store.records_dir / f"{record.task_id}.json"
        backup_once(json_path)
        outcome = record.outcome
        reported = outcome.reported_cost_usd
        if not reported and outcome.cost_source == "agent_reported":
            reported = outcome.cost_usd
        cost = compute_cost_usd(
            model_preset,
            outcome.n_input_tokens,
            outcome.n_output_tokens,
            outcome.n_cache_tokens,
            at_time=at_time,
        )
        if cost is not None:
            outcome.cost_usd = cost
            outcome.cost_source = "computed_from_tokens"
            outcome.reported_cost_usd = reported
            outcome.cost_model_name = model_preset
            outcome.cost_pricing_tier = pricing_tier_for_model(
                model_preset, at_time
            )
            outcome.cost_pricing_snapshot = (
                DEEPSEEK_PRICING_SNAPSHOT
                if model_preset.startswith("deepseek-")
                else ""
            )

        trajectory = None
        if outcome.trial_dir is not None:
            trajectory = resolve_trajectory(Path(outcome.trial_dir))
        if trajectory is not None:
            outcome.trajectory_path = trajectory
            record.trajectory_compact = TrajectoryCompactor().compact(
                trajectory, outcome
            ).to_dict()
            record.trajectory_compact_rough = TrajectoryCompactor.make_rough().compact(
                trajectory, outcome
            ).to_dict()
        store.persist(record)
        summaries.append(
            {
                "task_id": record.task_id,
                "trajectory_path": str(outcome.trajectory_path or ""),
                "cost_usd": outcome.cost_usd,
                "reported_cost_usd": outcome.reported_cost_usd,
                "cost_pricing_tier": outcome.cost_pricing_tier,
                "rich_events": record.trajectory_compact.get("n_events", 0),
                "rough_events": record.trajectory_compact_rough.get("n_events", 0),
            }
        )
    store.close()
    repair_report(run_dir, records)
    return {"run_dir": str(run_dir), "records": summaries}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", action="append", required=True)
    parser.add_argument("--model-preset", required=True)
    args = parser.parse_args()
    results = []
    for raw_path in args.run_dir:
        run_dir = Path(raw_path).expanduser().resolve()
        if not run_dir.is_dir():
            raise SystemExit(f"Run directory not found: {run_dir}")
        results.append(repair_run(run_dir, args.model_preset))
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
