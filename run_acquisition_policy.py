"""Acquire one fully verified T1 source trajectory under a bounded policy.

Every attempt keeps the same model preset, harness, task order, baseline, and
task limit. Failed attempts remain in the ledger; the first source-valid run is
selected. The script never changes the task prompt or verifier.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from run_smoke import (
    WORKSPACE_ROOT,
    build_config,
    collect_agent_failures,
    load_replay_records,
    print_replay_validation,
    replay_validation_summary,
    source_is_fully_valid,
)

from harbor_compat import install as install_harbor_compat
from skillevolbench.metrics.cost import (
    DEEPSEEK_PRICING_SNAPSHOT,
    compute_cost_usd,
    deepseek_pricing_tier,
)
from skillevolbench.orchestration import LifelongRunner


EXPECTED_TASK_ID = "E1-LS1-T1"
LOCAL_LATEST_SOURCE = Path(__file__).resolve().parent / "latest_selected_source.json"


def _utc_from_run_id(run_id: str) -> datetime | None:
    match = re.search(r"__(\d{8}_\d{6})$", run_id)
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y%m%d_%H%M%S").replace(
        tzinfo=timezone.utc
    )


def _repair_summary_for_audit(
    summary: dict, record: dict, run_dir: Path, model_preset: str,
) -> dict:
    """Correct legacy path/cost fields in the policy ledger, not source data."""
    outcome = record.get("outcome") or {}
    trial_dir_text = str(outcome.get("trial_dir", ""))
    if summary.get("trajectory_path", "").endswith("manifest.json") and trial_dir_text:
        trial_dir = Path(trial_dir_text)
        for candidate in (
            trial_dir / "agent" / "trajectory.json",
            trial_dir / "artifacts" / "logs" / "agent" / "trajectory.json",
            trial_dir / "artifacts" / "trajectory.json",
        ):
            if candidate.is_file():
                summary["trajectory_path"] = str(candidate)
                summary["legacy_trajectory_path_repaired_in_ledger"] = True
                break

    if model_preset.startswith("deepseek-") and (
        outcome.get("cost_source") != "computed_from_tokens"
        or not outcome.get("cost_model_name", "").startswith("deepseek-")
    ):
        n_input = int(outcome.get("n_input_tokens", 0) or 0)
        n_output = int(outcome.get("n_output_tokens", 0) or 0)
        n_cache = int(outcome.get("n_cache_tokens", 0) or 0)
        at_time = _utc_from_run_id(run_dir.name)
        estimated = compute_cost_usd(
            model_preset, n_input, n_output, n_cache, at_time=at_time
        )
        if estimated is not None:
            summary["reported_cost_usd"] = float(outcome.get("cost_usd", 0.0) or 0.0)
            summary["cost_usd"] = estimated
            summary["cost_source"] = "computed_from_tokens"
            summary["cost_pricing_tier"] = deepseek_pricing_tier(at_time)
            summary["cost_pricing_snapshot"] = DEEPSEEK_PRICING_SNAPSHOT
            summary["legacy_cost_repaired_in_ledger"] = True
    return summary


def inspect_run(run_dir: Path, model_preset: str) -> dict:
    records = load_replay_records(run_dir)
    failures = collect_agent_failures(run_dir)
    attempt: dict = {
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "agent_failures": failures,
        "record_count": len(records),
        "source_valid": False,
    }
    if failures:
        attempt["status"] = "agent_failure"
        return attempt
    if len(records) != 1:
        attempt["status"] = "invalid_record_count"
        return attempt

    record_path, record = records[0]
    summary = _repair_summary_for_audit(
        replay_validation_summary(record), record, run_dir, model_preset
    )
    attempt.update(summary)
    attempt["record_path"] = str(record_path)
    attempt["source_valid"] = source_is_fully_valid(summary)
    attempt["status"] = "selected" if attempt["source_valid"] else "verifier_rejected"
    if summary.get("task_id") != EXPECTED_TASK_ID:
        attempt["status"] = "unexpected_task"
        attempt["source_valid"] = False
    return attempt


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-preset", default="deepseek-v4-flash")
    parser.add_argument("--order-seed", choices=("A", "B", "C"), default="A")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument(
        "--audit-ledger",
        help="Re-audit an existing acquisition ledger without running a model.",
    )
    parser.add_argument(
        "--existing-run-dir",
        action="append",
        default=[],
        help="Count an earlier same-configuration run as an attempt.",
    )
    args = parser.parse_args()
    if args.max_attempts < 1:
        raise SystemExit("--max-attempts must be at least 1")

    if args.audit_ledger:
        ledger_path = Path(args.audit_ledger).expanduser().resolve()
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        model_preset = ledger["fixed_configuration"]["model_preset"]
        refreshed = []
        for old_attempt in ledger.get("attempts", []):
            attempt = inspect_run(Path(old_attempt["run_dir"]), model_preset)
            attempt["attempt_number"] = old_attempt["attempt_number"]
            attempt["origin"] = old_attempt.get("origin", "unknown")
            refreshed.append(attempt)
        ledger["attempts"] = refreshed
        ledger["selected_source"] = next(
            (attempt for attempt in refreshed if attempt.get("source_valid")), None
        )
        ledger["last_audited_at"] = datetime.now(timezone.utc).isoformat()
        write_json(ledger_path, ledger)
        selected_path = ledger_path.parent / "selected_source.json"
        if ledger["selected_source"] is not None:
            write_json(selected_path, ledger["selected_source"])
            write_json(LOCAL_LATEST_SOURCE, ledger["selected_source"])
        elif selected_path.exists():
            selected_path.unlink()
        print(f"Re-audited ledger: {ledger_path}")
        return 0

    started_at = datetime.now(timezone.utc)
    policy_id = (
        f"acquisition__no_skill__{args.model_preset}__seed{args.order_seed}__"
        f"max{args.max_attempts}__{started_at.strftime('%Y%m%d_%H%M%S')}"
    )
    policy_dir = WORKSPACE_ROOT / "acquisition_policies" / policy_id
    ledger_path = policy_dir / "acquisition_ledger.json"
    ledger = {
        "policy_id": policy_id,
        "started_at": started_at.isoformat(),
        "fixed_configuration": {
            "baseline": "no_skill",
            "model_preset": args.model_preset,
            "agent_harness": "claude-code",
            "order_seed": args.order_seed,
            "max_tasks_per_attempt": 1,
            "expected_task_id": EXPECTED_TASK_ID,
            "prompt_or_verifier_changes_between_attempts": False,
        },
        "selection_rule": (
            "first attempt with verifier_passed=true, outcome_passed=true, "
            "and process_passed=true"
        ),
        "max_attempts": args.max_attempts,
        "attempts": [],
        "selected_source": None,
    }

    for existing in args.existing_run_dir:
        if len(ledger["attempts"]) >= args.max_attempts:
            break
        run_dir = Path(existing).expanduser().resolve()
        if not run_dir.is_dir():
            raise SystemExit(f"Existing run directory not found: {run_dir}")
        attempt = inspect_run(run_dir, args.model_preset)
        attempt["attempt_number"] = len(ledger["attempts"]) + 1
        attempt["origin"] = "existing"
        ledger["attempts"].append(attempt)
        write_json(ledger_path, ledger)
        print(f"Attempt {attempt['attempt_number']} (existing): {attempt['status']}")
        if "normalized_score" in attempt:
            print_replay_validation(attempt)
        if attempt["source_valid"]:
            ledger["selected_source"] = attempt
            break

    install_harbor_compat()
    while ledger["selected_source"] is None and len(ledger["attempts"]) < args.max_attempts:
        attempt_number = len(ledger["attempts"]) + 1
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        run_id = (
            f"acquire{attempt_number}__no_skill__{args.model_preset}__"
            f"seed{args.order_seed}__n1__{timestamp}"
        )
        smoke_args = SimpleNamespace(
            baseline_name="no_skill",
            model_preset=args.model_preset,
            order_seed=args.order_seed,
            max_tasks=1,
            run_id=run_id,
        )
        config = build_config(smoke_args)
        print(f"Attempt {attempt_number}: starting {run_id}")
        try:
            asyncio.run(LifelongRunner(config=config).run())
            attempt = inspect_run(config.run_dir, args.model_preset)
        except Exception as exc:
            attempt = {
                "run_id": run_id,
                "run_dir": str(config.run_dir),
                "status": "runtime_error",
                "source_valid": False,
                "error_type": type(exc).__name__,
                "error": str(exc)[:2000],
            }
        attempt["attempt_number"] = attempt_number
        attempt["origin"] = "new"
        ledger["attempts"].append(attempt)
        if attempt.get("source_valid"):
            ledger["selected_source"] = attempt
        write_json(ledger_path, ledger)
        print(f"Attempt {attempt_number}: {attempt['status']}")
        if "normalized_score" in attempt:
            print_replay_validation(attempt)

    ledger["completed_at"] = datetime.now(timezone.utc).isoformat()
    ledger["attempts_used"] = len(ledger["attempts"])
    write_json(ledger_path, ledger)
    print(f"Acquisition ledger: {ledger_path}")
    if ledger["selected_source"] is None:
        print("Acquisition policy exhausted without a fully valid source.", file=sys.stderr)
        return 4

    selected_path = policy_dir / "selected_source.json"
    write_json(selected_path, ledger["selected_source"])
    write_json(LOCAL_LATEST_SOURCE, ledger["selected_source"])
    print(f"Selected source: {ledger['selected_source']['run_dir']}")
    print(f"Selection record: {selected_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
