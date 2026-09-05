"""Print a compact, auditable summary of a completed paired MVP."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mvp_dir", type=Path)
    args = parser.parse_args()
    root = args.mvp_dir.expanduser().resolve()
    summary = load_json(root / "paired_summary.json")
    print("SUMMARY")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    print("BRANCH_AUDIT")
    for condition in ("no_artifact", "episodic", "procedural"):
        branch = root / "branches" / condition
        result = load_json(branch / "paired_branch_result.json")
        report = load_json(branch / "reports" / "full_report.json")
        record_paths = sorted((branch / "stores" / "replay" / "records").glob("*.json"))
        record = load_json(record_paths[0]) if record_paths else {}
        outcome = record.get("outcome") or {}
        trajectory = {}
        trajectory_path = Path(str(outcome.get("trajectory_path", "")))
        if trajectory_path.is_file():
            trajectory = load_json(trajectory_path)
        steps = trajectory.get("steps") or []
        tool_counts: Counter[str] = Counter()
        last_message = ""
        for step in steps:
            message = step.get("message")
            if isinstance(message, str) and message.strip():
                last_message = message.strip()
            for call in step.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                function = call.get("function") or {}
                name = call.get("name") or (
                    function.get("name") if isinstance(function, dict) else None
                )
                if name:
                    tool_counts[str(name)] += 1
        exceptions = []
        for path in (branch / "harbor-job").glob("**/result.json"):
            payload = load_json(path)
            if payload.get("exception_info"):
                exceptions.append(str(path))
        row = {
            "condition": condition,
            "normalized_score": result.get("normalized_score"),
            "verifier_passed": result.get("verifier_passed"),
            "outcome_passed": outcome.get("outcome_passed"),
            "process_passed": outcome.get("process_passed"),
            "failed_tests": [
                item.get("name") for item in outcome.get("failed_tests", [])
            ],
            "cost_usd": outcome.get("cost_usd"),
            "reported_cost_usd": outcome.get("reported_cost_usd"),
            "cost_source": outcome.get("cost_source"),
            "trajectory_path": outcome.get("trajectory_path"),
            "representation_audit": result.get("representation_audit"),
            "report_total_cost_usd": (report.get("cost") or {}).get("total_cost_usd"),
            "agent_exception_count": len(exceptions),
            "trajectory_steps": len(steps),
            "tool_counts": dict(tool_counts),
            "last_message": last_message[:1000],
        }
        print(json.dumps(row, ensure_ascii=False))

    procedural_dir = root / "evidence" / "procedural"
    skill_path = procedural_dir / "SKILL.md"
    manifest = load_json(procedural_dir / "authoring_manifest.json")
    print("PROCEDURAL_AUDIT")
    print(
        json.dumps(
            {
                "files": {
                    path.name: path.stat().st_size
                    for path in sorted(procedural_dir.glob("*"))
                },
                "authoring_manifest": manifest,
                "skill_chars": len(skill_path.read_text(encoding="utf-8")),
                "author_dump_files": {
                    path.name: path.stat().st_size
                    for path in sorted((root / "evidence" / "llm_calls").glob("*"))
                },
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
