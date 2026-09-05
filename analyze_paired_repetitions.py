"""Aggregate repeated same-source paired MVP runs without collapsing constructs."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


from runtime_paths import PAIRED_ROOT
LOCAL_ROOT = Path(__file__).resolve().parent
CONDITIONS = ("no_artifact", "episodic", "procedural")
CATEGORIES = ("functional", "contract", "form")


def failed_test_names(items: list[Any]) -> list[str]:
    names: list[str] = []
    for item in items or []:
        if isinstance(item, dict):
            value = item.get("name") or item.get("nodeid") or item.get("test")
            names.append(str(value if value is not None else item))
        else:
            names.append(str(item))
    return names


def classify_failures(
    *, target_task_id: str, failures: list[str], audit_checks: list[dict[str, Any]]
) -> dict[str, Any]:
    task_checks = [item for item in audit_checks if item["task_id"] == target_task_id]
    totals = Counter(item["category"] for item in task_checks)
    failed = Counter()
    unmatched: list[str] = []
    for failure in failures:
        matches = [item for item in task_checks if item["check"] in failure]
        if not matches:
            unmatched.append(failure)
            continue
        for category in {item["category"] for item in matches}:
            failed[category] += 1
    result: dict[str, Any] = {"unmatched_failed_tests": unmatched}
    for category in CATEGORIES:
        total = totals[category]
        n_failed = min(failed[category], total)
        result[category] = {
            "total": total,
            "failed": n_failed,
            "passed": total - n_failed,
            "pass_rate": (total - n_failed) / total if total else None,
        }
    return result


def summarize(values: list[float]) -> dict[str, float | int | None]:
    return {
        "n": len(values),
        "mean": statistics.fmean(values) if values else None,
        "sample_sd": statistics.stdev(values) if len(values) > 1 else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-prefix", default="e1ls3_trainingfree_v1")
    parser.add_argument("--paired-root", type=Path, default=PAIRED_ROOT)
    parser.add_argument(
        "--audit-json", type=Path, default=LOCAL_ROOT / "verifier_construct_audit.json"
    )
    parser.add_argument(
        "--json-output", type=Path, default=LOCAL_ROOT / "paired_repetition_summary.json"
    )
    parser.add_argument(
        "--md-output", type=Path, default=LOCAL_ROOT / "paired_repetition_summary.md"
    )
    args = parser.parse_args()

    audit = json.loads(args.audit_json.read_text(encoding="utf-8"))
    runs: list[dict[str, Any]] = []
    for mvp_dir in sorted(args.paired_root.glob(f"{args.experiment_prefix}__*")):
        summary_path = mvp_dir / "paired_summary.json"
        if not summary_path.is_file():
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        repetition = mvp_dir.name.rsplit("__rep", 1)[-1]
        for branch in summary["results"]:
            failures = failed_test_names(branch.get("failed_tests", []))
            runs.append(
                {
                    "mvp_id": mvp_dir.name,
                    "repetition": repetition,
                    "source_task_id": summary["source_task_id"],
                    "target_task_id": summary["target_task_id"],
                    "condition": branch["condition"],
                    "normalized_score": float(branch["normalized_score"]),
                    "verifier_passed": bool(branch["verifier_passed"]),
                    "outcome_passed": branch.get("outcome_passed"),
                    "process_passed": branch.get("process_passed"),
                    "agent_completed_without_exception": branch.get(
                        "agent_completed_without_exception"
                    ),
                    "agent_input_tokens": branch.get("agent_input_tokens"),
                    "agent_output_tokens": branch.get("agent_output_tokens"),
                    "agent_cache_tokens": branch.get("agent_cache_tokens"),
                    "agent_cost_usd_estimate": branch.get("agent_cost_usd_estimate"),
                    "total_cost_usd_estimate": branch.get("total_cost_usd_estimate"),
                    "failed_tests": failures,
                    "construct_results": classify_failures(
                        target_task_id=summary["target_task_id"],
                        failures=failures,
                        audit_checks=audit["checks"],
                    ),
                    "run_dir": branch["run_dir"],
                }
            )

    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    score_by_rep: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for item in runs:
        grouped[(item["target_task_id"], item["condition"])].append(
            item["normalized_score"]
        )
        score_by_rep[(item["target_task_id"], item["repetition"])][
            item["condition"]
        ] = item["normalized_score"]

    aggregates = []
    for (target, condition), values in sorted(grouped.items()):
        aggregates.append(
            {
                "target_task_id": target,
                "condition": condition,
                **summarize(values),
            }
        )
    matched_deltas = []
    for (target, repetition), scores in sorted(score_by_rep.items()):
        if not all(condition in scores for condition in CONDITIONS):
            continue
        matched_deltas.append(
            {
                "target_task_id": target,
                "repetition": repetition,
                "episodic_minus_no_artifact": scores["episodic"] - scores["no_artifact"],
                "procedural_minus_no_artifact": scores["procedural"] - scores["no_artifact"],
                "procedural_minus_episodic": scores["procedural"] - scores["episodic"],
            }
        )

    construct_grouped: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    construct_by_rep: dict[tuple[str, str, str], dict[str, float]] = defaultdict(dict)
    for item in runs:
        for category in CATEGORIES:
            pass_rate = item["construct_results"][category]["pass_rate"]
            if pass_rate is None:
                continue
            construct_grouped[
                (item["target_task_id"], item["condition"], category)
            ].append(float(pass_rate))
            construct_by_rep[
                (item["target_task_id"], item["repetition"], category)
            ][item["condition"]] = float(pass_rate)

    construct_aggregates = []
    for (target, condition, category), values in sorted(construct_grouped.items()):
        construct_aggregates.append(
            {
                "target_task_id": target,
                "condition": condition,
                "category": category,
                **summarize(values),
            }
        )

    construct_matched_deltas = []
    for (target, repetition, category), scores in sorted(construct_by_rep.items()):
        if not all(condition in scores for condition in CONDITIONS):
            continue
        construct_matched_deltas.append(
            {
                "target_task_id": target,
                "repetition": repetition,
                "category": category,
                "episodic_minus_no_artifact": scores["episodic"]
                - scores["no_artifact"],
                "procedural_minus_no_artifact": scores["procedural"]
                - scores["no_artifact"],
                "procedural_minus_episodic": scores["procedural"]
                - scores["episodic"],
            }
        )

    agent_exception_runs = sum(
        item["agent_completed_without_exception"] is False for item in runs
    )
    unmatched_failures = sum(
        len(item["construct_results"]["unmatched_failed_tests"]) for item in runs
    )
    branch_costs = [
        float(item["total_cost_usd_estimate"])
        for item in runs
        if item["total_cost_usd_estimate"] is not None
    ]

    payload = {
        "schema_version": "paired-repetition-summary-1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "experiment_prefix": args.experiment_prefix,
        "design": {
            "source_task_id": "E1-LS3-T1",
            "targets": ["E1-LS3-T4", "E1-LS3-T5", "E1-LS3-T6"],
            "conditions": list(CONDITIONS),
            "paired_repetitions": ["A", "B", "C"],
            "procedural_artifact": "one frozen abstraction reused across all target runs",
            "randomness_note": "Claude exposes no controllable generation seed; A/B/C are paired repetitions with matched configuration, not identical sampling streams.",
        },
        "n_branch_runs": len(runs),
        "runs": runs,
        "aggregates": aggregates,
        "matched_deltas": matched_deltas,
        "construct_aggregates": construct_aggregates,
        "construct_matched_deltas": construct_matched_deltas,
        "integrity": {
            "agent_exception_runs": agent_exception_runs,
            "unmatched_failed_tests": unmatched_failures,
            "branch_cost_usd_estimate": sum(branch_costs),
            "branch_cost_coverage": len(branch_costs),
            "cost_scope_note": "Target branch execution only; source acquisition and procedural authoring are excluded.",
        },
    }
    args.json_output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        "# Three-Pair Training-Free Repetition Summary",
        "",
        f"- Completed branch runs: {len(runs)} / 27",
        "- Source experience: `E1-LS3-T1`",
        "- Targets: `E1-LS3-T4`, `E1-LS3-T5`, `E1-LS3-T6`",
        "- Conditions: No Artifact, Episodic, Procedural",
        "- One frozen procedural abstraction is reused across all repetitions.",
        "- A/B/C are matched repetitions; the Claude API does not expose a controllable generation seed.",
        f"- Agent exceptions: {agent_exception_runs}; unmatched failed checks: {unmatched_failures}.",
        "",
        "## Aggregate normalized score",
        "",
        "| Target | Condition | n | Mean | SD | Min | Max |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for item in aggregates:
        sd = "-" if item["sample_sd"] is None else f"{item['sample_sd']:.3f}"
        lines.append(
            f"| `{item['target_task_id']}` | {item['condition']} | {item['n']} | "
            f"{item['mean']:.3f} | {sd} | {item['min']:.3f} | {item['max']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Matched deltas",
            "",
            "| Target | Rep | Episodic-No | Procedural-No | Procedural-Episodic |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for item in matched_deltas:
        lines.append(
            f"| `{item['target_task_id']}` | {item['repetition']} | "
            f"{item['episodic_minus_no_artifact']:.3f} | "
            f"{item['procedural_minus_no_artifact']:.3f} | "
            f"{item['procedural_minus_episodic']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Construct-resolved mean pass rate",
            "",
            "| Target | Condition | Functional | Contract | Form |",
            "|---|---|---:|---:|---:|",
        ]
    )
    construct_lookup = {
        (item["target_task_id"], item["condition"], item["category"]): item
        for item in construct_aggregates
    }
    for target in ("E1-LS3-T4", "E1-LS3-T5", "E1-LS3-T6"):
        for condition in CONDITIONS:
            values = []
            for category in CATEGORIES:
                item = construct_lookup.get((target, condition, category))
                values.append("-" if item is None else f"{item['mean']:.3f}")
            lines.append(
                f"| `{target}` | {condition} | {values[0]} | {values[1]} | {values[2]} |"
            )
    lines.extend(
        [
            "",
            "## Functional matched deltas",
            "",
            "| Target | Rep | Episodic-No | Procedural-No | Procedural-Episodic |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for item in construct_matched_deltas:
        if item["category"] != "functional":
            continue
        lines.append(
            f"| `{item['target_task_id']}` | {item['repetition']} | "
            f"{item['episodic_minus_no_artifact']:.3f} | "
            f"{item['procedural_minus_no_artifact']:.3f} | "
            f"{item['procedural_minus_episodic']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation rule",
            "",
            "Functional, contract, and form failures are retained separately in the JSON ledger. A difference in overall score alone is not treated as functional transfer evidence.",
            "",
        ]
    )
    args.md_output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Aggregated {len(runs)} branch runs; JSON={args.json_output}; Markdown={args.md_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
