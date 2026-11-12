import io
import json
import socket
import unittest
from contextlib import redirect_stdout
from importlib.resources import files
from unittest.mock import patch


def fixture_text() -> str:
    return files("decision_debugger").joinpath("demos", "support_tickets.json").read_text(
        encoding="utf-8"
    )


class DemoTests(unittest.TestCase):
    def test_authored_outcomes_include_fixes_and_a_regression(self) -> None:
        from decision_debugger.comparison import compare_runs
        from decision_debugger.demo import load_demo

        demo = load_demo()
        report = compare_runs(demo.baseline, demo.revised)
        self.assertEqual((report.baseline.correct, report.baseline.total), (5, 8))
        self.assertEqual((report.revised.correct, report.revised.total), (6, 8))
        self.assertEqual(
            tuple(report.count(change) for change in
                  ("improved", "regressed", "unchanged", "unresolved")),
            (2, 1, 5, 0),
        )
        self.assertFalse(report.confounded)
        regressed = [case.case_id for case in report.cases if case.change == "regressed"]
        self.assertEqual(regressed, ["dev-004"])

    def test_diagnosis_and_check_use_development_cases_only(self) -> None:
        from decision_debugger.demo import load_demo

        demo = load_demo()
        cases = {case.id: case for case in demo.baseline.dataset.cases}
        self.assertTrue(demo.diagnosis.evidence)
        for item in demo.diagnosis.evidence:
            self.assertEqual(cases[item.case_id].split, "development")
        self.assertEqual(cases[demo.check.source_case_id].split, "development")
        self.assertNotEqual(
            demo.check.example.input_text, cases[demo.check.source_case_id].input_text
        )

    def test_validation_case_cannot_be_substituted_into_saved_diagnosis(self) -> None:
        from decision_debugger.demo import parse_demo

        payload = json.loads(fixture_text())
        payload["diagnosis"]["evidence"][0]["case_id"] = "val-001"
        with self.assertRaisesRegex(ValueError, "development"):
            parse_demo(json.dumps(payload))

    def test_edited_demo_prompt_cannot_claim_fresh_inference(self) -> None:
        from decision_debugger.demo import parse_demo

        payload = json.loads(fixture_text())
        payload["baseline"]["prompt"] += "\nA new rule."
        with self.assertRaisesRegex(ValueError, "prompt.*snapshot"):
            parse_demo(json.dumps(payload))

    def test_edited_dataset_invalidates_saved_evidence(self) -> None:
        from decision_debugger.demo import parse_demo

        payload = json.loads(fixture_text())
        payload["cases"][0]["input_text"] = "An edited input."
        with self.assertRaisesRegex(ValueError, "dataset.*snapshot"):
            parse_demo(json.dumps(payload))

    def test_changed_output_contract_invalidates_saved_evidence(self) -> None:
        from decision_debugger.demo import parse_demo

        payload = json.loads(fixture_text())
        payload["task"]["labels"].append("SALES")
        with self.assertRaisesRegex(ValueError, "configuration.*snapshot"):
            parse_demo(json.dumps(payload))

    def test_check_cannot_reference_validation_data(self) -> None:
        from decision_debugger.demo import parse_demo

        payload = json.loads(fixture_text())
        payload["check"]["source_case_id"] = "val-002"
        with self.assertRaisesRegex(ValueError, "development"):
            parse_demo(json.dumps(payload))

    def test_invalid_or_incomplete_saved_output_is_not_silently_filled(self) -> None:
        from decision_debugger.demo import parse_demo

        payload = json.loads(fixture_text())
        del payload["revised"]["outputs"]["dev-001"]
        with self.assertRaisesRegex(ValueError, "outputs"):
            parse_demo(json.dumps(payload))

    def test_duplicate_json_keys_and_unknown_fields_rejected(self) -> None:
        from decision_debugger.demo import parse_demo

        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_demo('{"schema_version": 1, "schema_version": 1}')
        payload = json.loads(fixture_text())
        payload["api_key"] = "not-a-real-secret"
        with self.assertRaisesRegex(ValueError, "fields"):
            parse_demo(json.dumps(payload))

    def test_illustrative_material_does_not_invent_measured_metadata(self) -> None:
        from decision_debugger.demo import load_demo, parse_demo

        demo = load_demo()
        self.assertIsNone(demo.baseline.settings.model_id)
        self.assertIsNone(demo.baseline.settings.provider)
        self.assertEqual(
            json.loads(fixture_text())["metadata"],
            {"model_id": None, "token_usage": None, "latency_ms": None, "cost": None},
        )
        for key in ("model_id", "token_usage", "latency_ms", "cost"):
            payload = json.loads(fixture_text())
            payload["metadata"][key] = 123
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, "metadata"):
                    parse_demo(json.dumps(payload))

    def test_demo_manual_chat_and_live_provenance_are_distinct(self) -> None:
        from decision_debugger.demo import load_demo
        from decision_debugger.models import Provenance

        self.assertEqual(
            {item.value for item in Provenance},
            {"illustrative", "manual_chat", "live"},
        )
        self.assertEqual(load_demo().baseline.provenance, Provenance.ILLUSTRATIVE)


class WalkthroughTests(unittest.TestCase):
    def test_default_report_stops_at_exact_diff_for_approval(self) -> None:
        from decision_debugger.cli import build_report
        from decision_debugger.demo import load_demo

        output = build_report(load_demo())
        self.assertIn("Illustrative demonstration", output)
        self.assertIn("Baseline: 5/8", output)
        self.assertIn("--- baseline", output)
        self.assertIn("+++ revised", output)
        self.assertIn("Approval required", output)
        self.assertNotIn("Revised: 6/8", output)

    def test_explicit_approval_reveals_saved_results_and_regressions(self) -> None:
        from decision_debugger.cli import build_report
        from decision_debugger.demo import load_demo

        demo = load_demo()
        output = build_report(demo, approved_revision_hash=demo.revised.prompt_hash)
        for expected in (
            "Revised: 6/8", "Improved: 2", "Regressed: 1", "Unchanged: 5",
            "Unresolved: 0", "dev-004", "regressed", "Cost unavailable",
            "Model calls: 0", "independence",
        ):
            self.assertIn(expected, output)
        self.assertEqual(demo.baseline.dataset.task.prompt, json.loads(fixture_text())[
            "baseline"
        ]["prompt"])

    def test_stale_approval_does_not_reveal_revised_results(self) -> None:
        from decision_debugger.cli import build_report
        from decision_debugger.demo import load_demo

        with self.assertRaisesRegex(ValueError, "approval.*snapshot"):
            build_report(load_demo(), approved_revision_hash="old-hash")

    def test_offline_walkthrough_never_uses_network_and_repeats_identically(self) -> None:
        from decision_debugger.cli import main

        reports = []
        with (
            patch.object(socket.socket, "connect", side_effect=AssertionError("network call")),
            patch.object(socket.socket, "connect_ex", side_effect=AssertionError("network call")),
            patch.object(socket, "create_connection", side_effect=AssertionError("network call")),
        ):
            for _ in range(2):
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main(["--approve-demo-edit"]), 0)
                reports.append(output.getvalue())
        self.assertEqual(reports[0], reports[1])
        self.assertIn("Revised: 6/8", reports[0])
