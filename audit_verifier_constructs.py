"""Audit SkillEvolBench T4--T6 verifier checks by measured construct.

The output is a static first-pass audit.  It distinguishes checks of observable
task behaviour (functional), explicit non-functional obligations (contract),
and checks tied to a particular code shape or symbol (form).  Candidate pairs
are then manually reviewed against their task instructions.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_TASKS_ROOT = (
    Path(__file__).resolve().parent / "SkillEvolBench" / "benchmark" / "tasks"
)
TASK_ID_RE = re.compile(r"^task_id:\s*([^\s#]+)\s*$", re.MULTILINE)
TASK_SLUG_RE = re.compile(r"^task_slug:\s*([^\s#]+)\s*$", re.MULTILINE)
FAMILY_RE = re.compile(r"^family_id:\s*([^\s#]+)\s*$", re.MULTILINE)
ROLE_RE = re.compile(r"^role:\s*([^\s#]+)\s*$", re.MULTILINE)


# These three targets were selected only after reading their instructions and
# verifier bodies.  "Low" is not "zero": residual form checks are reported and
# must not be silently folded into the functional result.
CANDIDATE_PAIRS = (
    {
        "source_task_id": "E1-LS3-T1",
        "target_task_id": "E1-LS3-T4",
        "review": "Architectural transfer target: functional plugin tests plus broad modularity obligations stated in the task; no required helper-call location.",
    },
    {
        "source_task_id": "E1-LS3-T1",
        "target_task_id": "E1-LS3-T5",
        "review": "Boundary-preservation target: executable None/empty-value cases plus the explicitly requested Pipeline and stage-preservation contract.",
    },
    {
        "source_task_id": "E1-LS3-T1",
        "target_task_id": "E1-LS3-T6",
        "review": "Refactor-and-test target: functional edge cases plus task-declared helper-count, test-count, and coverage obligations.",
    },
)


def _field(pattern: re.Pattern[str], text: str, path: Path) -> str:
    match = pattern.search(text)
    if not match:
        raise ValueError(f"Missing required task field in {path}")
    return match.group(1)


def _test_segment(source: str, node: ast.AST) -> str:
    return ast.get_source_segment(source, node) or ""


def extract_checks(path: Path) -> list[dict[str, Any]]:
    source = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [
            {
                "name": "<parse-error>",
                "line": exc.lineno or 0,
                "source": "",
                "extraction": "parse_error",
            }
        ]

    checks: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            key = (node.name, node.lineno)
            if key not in seen:
                seen.add(key)
                checks.append(
                    {
                        "name": node.name,
                        "line": node.lineno,
                        "source": _test_segment(source, node),
                        "extraction": "pytest_or_unittest",
                    }
                )

        if not isinstance(node, ast.Call):
            continue
        call_name = ""
        if isinstance(node.func, ast.Name):
            call_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            call_name = node.func.attr
        if call_name != "run_checks" or len(node.args) < 2:
            continue
        collection = node.args[1]
        if not isinstance(collection, (ast.List, ast.Tuple)):
            continue
        section = "unknown"
        if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            section = node.args[0].value
        for item in collection.elts:
            if not isinstance(item, ast.Tuple) or not item.elts:
                continue
            label = item.elts[0]
            if not isinstance(label, ast.Constant) or not isinstance(label.value, str):
                continue
            name = str(label.value)
            key = (name, item.lineno)
            if key in seen:
                continue
            seen.add(key)
            checks.append(
                {
                    "name": name,
                    "line": item.lineno,
                    "source": _test_segment(source, item),
                    "extraction": f"run_checks:{section}",
                }
            )
    return sorted(checks, key=lambda item: (item["line"], item["name"]))


def classify_check(*, verifier_group: str, name: str, source: str) -> tuple[str, str, str]:
    """Return category, rationale, and confidence for one static check."""
    text = f"{name}\n{source}".casefold()
    static_source = any(
        token in text
        for token in (
            ".read_text(",
            "read_text(",
            "ast.parse",
            "source =",
            "script =",
            "code =",
        )
    ) and any(token in text for token in (".py", "policy", "pipeline", "script", "code", "source"))
    executes_behaviour = any(
        token in text
        for token in (
            "subprocess.run",
            "runpy.run_path",
            "output()",
            "data()",
            "_result()",
            "load_output()",
            "process_requests(",
            "is_relevant(",
            "json.loads(output",
        )
    )
    contract_signal = any(
        token in text
        for token in (
            "hardcod",
            "static output",
            "static_output",
            "stub",
            "unsafe",
            "provenance",
            "all_source",
            "all source",
            "schema",
            "audit",
            "validat",
            "security",
            "not_remote",
            "no_top",
        )
    )
    broad_contract_signal = any(
        token in text
        for token in (
            "hardcod",
            "static output",
            "static_output",
            "stub",
            "unsafe",
            "provenance",
            "schema",
            "security",
            "module_split",
            "global_state",
            "plugin_registration",
            "pipeline_class",
            "stage_functions",
            "no_shortcut",
            "coverage",
            "refactor_split",
            "tests_added",
            "edge_case",
        )
    )

    if verifier_group == "outcome" and not static_source:
        return "functional", "Checks observable output or task behaviour.", "high"
    if executes_behaviour and not static_source:
        return "functional", "Executes or inspects produced behaviour rather than code shape.", "high"
    if static_source and broad_contract_signal:
        return "contract", "Statically checks an explicit safety, completeness, schema, or anti-shortcut obligation.", "medium"
    if static_source:
        return "form", "Depends on a specific file, symbol, literal, or source-code structure.", "high"
    if verifier_group == "process" and contract_signal:
        return "contract", "Checks an explicit process or non-functional obligation.", "medium"
    if verifier_group == "outcome":
        return "functional", "Outcome-group check; no source-shape dependency detected.", "medium"
    return "contract", "Process-group check without a clear source-shape dependency.", "low"


def audit(tasks_root: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    task_summaries: dict[str, dict[str, Any]] = {}
    for spec_path in sorted(tasks_root.glob("*/task-spec.yaml")):
        spec = spec_path.read_text(encoding="utf-8")
        task_id = _field(TASK_ID_RE, spec, spec_path)
        if not re.fullmatch(r"E[1-6]-LS[1-5]-T[4-6]", task_id):
            continue
        task_dir = spec_path.parent
        summary = {
            "task_id": task_id,
            "task_slug": _field(TASK_SLUG_RE, spec, spec_path),
            "family_id": _field(FAMILY_RE, spec, spec_path),
            "role": _field(ROLE_RE, spec, spec_path),
            "counts": {"functional": 0, "contract": 0, "form": 0},
            "n_checks": 0,
        }
        for test_path in sorted((task_dir / "tests").glob("test_*.py")):
            verifier_group = "process" if "process" in test_path.stem else "outcome"
            for check in extract_checks(test_path):
                category, rationale, confidence = classify_check(
                    verifier_group=verifier_group,
                    name=check["name"],
                    source=check["source"],
                )
                record = {
                    "task_id": task_id,
                    "task_slug": summary["task_slug"],
                    "family_id": summary["family_id"],
                    "verifier_group": verifier_group,
                    "file": str(test_path.relative_to(tasks_root)),
                    "line": check["line"],
                    "check": check["name"],
                    "category": category,
                    "form_sensitive": category == "form",
                    "rationale": rationale,
                    "confidence": confidence,
                    "extraction": check["extraction"],
                }
                records.append(record)
                summary["counts"][category] += 1
                summary["n_checks"] += 1
        task_summaries[task_id] = summary

    candidate_rows = []
    for item in CANDIDATE_PAIRS:
        summary = task_summaries[item["target_task_id"]]
        candidate_rows.append(
            {
                **item,
                "target_counts": summary["counts"],
                "target_n_checks": summary["n_checks"],
                "residual_form_checks": [
                    record["check"]
                    for record in records
                    if record["task_id"] == item["target_task_id"]
                    and record["category"] == "form"
                ],
            }
        )

    totals = Counter(record["category"] for record in records)
    return {
        "schema_version": "verifier-construct-audit-1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tasks_root": str(tasks_root.resolve()),
        "scope": "All SkillEvolBench T4-T6 tasks",
        "method": "Static AST extraction plus rule-based construct classification; selected pairs manually reviewed.",
        "limitations": [
            "Static classification is a measurement audit, not ground truth.",
            "Low-confidence and contract/form boundary cases require human review before publication.",
            "Overall benchmark score must not be treated as functional utility when form checks differ.",
        ],
        "n_tasks": len(task_summaries),
        "n_checks": len(records),
        "category_totals": dict(totals),
        "candidate_pairs": candidate_rows,
        "tasks": [task_summaries[key] for key in sorted(task_summaries)],
        "checks": records,
    }


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# SkillEvolBench T4-T6 Verifier Construct Audit",
        "",
        f"- Scope: {payload['n_tasks']} tasks, {payload['n_checks']} extracted checks",
        f"- Functional: {payload['category_totals'].get('functional', 0)}",
        f"- Contract: {payload['category_totals'].get('contract', 0)}",
        f"- Form: {payload['category_totals'].get('form', 0)}",
        "",
        "## Definitions",
        "",
        "- **Functional**: executes the solution or inspects its observable output/state.",
        "- **Contract**: enforces an explicit safety, completeness, schema, provenance, or anti-shortcut obligation.",
        "- **Form**: requires a particular file, symbol, literal, import, or code layout even when another implementation could behave correctly.",
        "",
        "The classification is a static first pass. Contract/form boundary cases remain reviewable in the JSON ledger.",
        "",
        "## Selected paired runs",
        "",
        "| Source | Target | Functional | Contract | Form | Review |",
        "|---|---|---:|---:|---:|---|",
    ]
    for pair in payload["candidate_pairs"]:
        counts = pair["target_counts"]
        lines.append(
            f"| `{pair['source_task_id']}` | `{pair['target_task_id']}` | "
            f"{counts['functional']} | {counts['contract']} | {counts['form']} | "
            f"{pair['review']} |"
        )
    lines.extend(
        [
            "",
            "Primary interpretation uses functional outcomes. Contract and form results are reported separately; form failures cannot establish negative functional transfer.",
            "",
            "## All T4-T6 tasks",
            "",
            "| Task | Slug | Functional | Contract | Form |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for task in payload["tasks"]:
        counts = task["counts"]
        lines.append(
            f"| `{task['task_id']}` | `{task['task_slug']}` | "
            f"{counts['functional']} | {counts['contract']} | {counts['form']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "This audit does not change the benchmark verifier. It changes how paired-run evidence is interpreted: functional, contract, and form effects are not collapsed into one causal claim.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks-root", type=Path, default=DEFAULT_TASKS_ROOT)
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path(__file__).resolve().parent / "verifier_construct_audit.json",
    )
    parser.add_argument(
        "--md-output",
        type=Path,
        default=Path(__file__).resolve().parent / "verifier_construct_audit.md",
    )
    args = parser.parse_args()
    if not args.tasks_root.is_dir():
        raise SystemExit(f"Tasks root not found: {args.tasks_root}")
    payload = audit(args.tasks_root)
    args.json_output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_markdown(payload, args.md_output)
    print(
        f"Audited {payload['n_tasks']} tasks and {payload['n_checks']} checks; "
        f"JSON={args.json_output}; Markdown={args.md_output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
