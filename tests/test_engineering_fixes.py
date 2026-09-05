"""Focused regression checks for the local SkillEvolBench runtime fixes."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace


BASELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASELINE_DIR / "SkillEvolBench"))

from skillevolbench.components.skill_author import (
    LiteLLMClient,
    PatchGenerationFailure,
    _coerce_complete_single_upsert,
    _coerce_json,
)
from skillevolbench.components.verifier_adapter import VerifierAdapter
from skillevolbench.metrics.cost import (
    canonicalize_model_name,
    compute_cost_usd,
    deepseek_pricing_tier,
)


class EngineeringFixTests(unittest.TestCase):
    def test_manifest_is_not_resolved_as_trajectory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            trial_dir = Path(temp)
            (trial_dir / "verifier").mkdir()
            (trial_dir / "artifacts").mkdir()
            (trial_dir / "artifacts" / "manifest.json").write_text("{}")
            agent_dir = trial_dir / "agent"
            agent_dir.mkdir()
            expected = agent_dir / "trajectory.json"
            expected.write_text('{"steps": []}')

            actual = VerifierAdapter._resolve_trajectory_path(
                trial_dir / "verifier", None
            )
            self.assertEqual(actual, expected)

    def test_manifest_only_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            trial_dir = Path(temp)
            (trial_dir / "verifier").mkdir()
            (trial_dir / "artifacts").mkdir()
            (trial_dir / "artifacts" / "manifest.json").write_text("{}")
            self.assertIsNone(
                VerifierAdapter._resolve_trajectory_path(
                    trial_dir / "verifier", None
                )
            )

    def test_deepseek_peak_and_off_peak_cost(self) -> None:
        peak = datetime(2026, 9, 2, 3, 23, tzinfo=timezone.utc)
        off_peak = datetime(2026, 9, 2, 5, 0, tzinfo=timezone.utc)
        args = ("deepseek/deepseek-v4-flash", 1_091_633, 29_967, 1_052_416)
        self.assertEqual(canonicalize_model_name(args[0]), "deepseek-v4-flash")
        self.assertEqual(deepseek_pricing_tier(peak), "peak")
        self.assertEqual(deepseek_pricing_tier(off_peak), "off_peak")
        self.assertEqual(compute_cost_usd(*args, at_time=peak), 0.071546)
        self.assertEqual(compute_cost_usd(*args, at_time=off_peak), 0.035773)
        self.assertEqual(
            compute_cost_usd(
                args[0], 39_217, 29_967, 1_052_416,
                at_time=peak, input_includes_cache=False,
            ),
            0.071546,
        )

    def test_deepseek_agent_report_is_audit_only(self) -> None:
        trial = SimpleNamespace(
            agent_result=SimpleNamespace(
                n_input_tokens=1000,
                n_output_tokens=100,
                n_cache_tokens=800,
                cost_usd=9.99,
            ),
            config=SimpleNamespace(
                agent=SimpleNamespace(model_name="deepseek-v4-flash")
            ),
        )
        parsed = VerifierAdapter._parse_agent_cost(trial)
        self.assertEqual(parsed[4], "computed_from_tokens")
        self.assertEqual(parsed[5], 9.99)
        self.assertEqual(parsed[6], "deepseek-v4-flash")
        self.assertIn(parsed[7], {"peak", "off_peak"})

    def test_deepseek_json_author_disables_thinking_and_retries_empty(self) -> None:
        calls = []

        def completion(**kwargs):
            calls.append(kwargs)
            content = "" if len(calls) == 1 else '{"ok": true}'
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
                usage=None,
            )

        fake_litellm = SimpleNamespace(
            completion=completion,
            drop_params=None,
            num_retries=None,
        )
        previous = sys.modules.get("litellm")
        sys.modules["litellm"] = fake_litellm
        try:
            client = LiteLLMClient(
                model="deepseek/deepseek-v4-flash",
                json_mode=True,
                max_tokens=128,
            )
            output = client("return json", system_prompt="json only")
        finally:
            if previous is None:
                sys.modules.pop("litellm", None)
            else:
                sys.modules["litellm"] = previous

        self.assertEqual(output, '{"ok": true}')
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            calls[0]["extra_body"], {"thinking": {"type": "disabled"}}
        )
        self.assertEqual(calls[0]["response_format"], {"type": "json_object"})

    def test_json_author_accepts_literal_control_character_in_string(self) -> None:
        raw = '{"skill": "first line\nsecond line", "ok": true}'
        self.assertEqual(
            _coerce_json(raw),
            {"skill": "first line\nsecond line", "ok": True},
        )

    def test_complete_single_upsert_recovers_unescaped_skill_body(self) -> None:
        raw = '''```json
{
  "summary": "Create a diagnostic skill.",
  "operation_type": "create",
  "upsert_files": {
    "example/SKILL.md": "---\\nname: example\\n---\\nA raw "quoted" rule.\n"
  }
}
```'''
        data = _coerce_complete_single_upsert(raw)
        self.assertEqual(data["summary"], "Create a diagnostic skill.")
        self.assertEqual(
            data["upsert_files"]["example/SKILL.md"],
            '---\nname: example\n---\nA raw "quoted" rule.\n',
        )

    def test_single_upsert_recovery_rejects_truncated_response(self) -> None:
        with self.assertRaises(PatchGenerationFailure):
            _coerce_complete_single_upsert(
                '{"upsert_files":{"example/SKILL.md":"unfinished'
            )


if __name__ == "__main__":
    unittest.main()
