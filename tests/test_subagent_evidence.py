import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

from decision_debugger.comparison import compare_runs
from decision_debugger.demo import load_demo
from decision_debugger.models import Provenance, RunSettings
from decision_debugger.scoring import score_run


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fake_evidence(challenge: bool = False) -> dict[str, Any]:
    from tools.score_subagent_demo import build_request

    demo = load_demo()
    baseline, revised = demo.baseline, demo.revised
    catalog_hash = None
    if challenge:
        from tools.score_subagent_demo import load_challenge

        baseline, revised, catalog_hash = load_challenge()
    settings = RunSettings(provider="copilot-subagent", model_id="gpt-6.1-sol")
    data: dict[str, Any] = {
        "schema_version": 1,
        "provenance": "manual_chat",
        "method": "copilot-subagent-batch-v1",
        "collected_on": "2026-11-12",
        "requested_model_id": "gpt-6.1-sol",
        "dataset_sha256": baseline.dataset_hash,
        "configuration_sha256": replace(
            baseline, settings=settings, provenance=Provenance.MANUAL_CHAT
        ).configuration_hash,
        "task_launches": 2,
        "unknown": {
            "verified_backend_model_id": None,
            "underlying_model_calls": None,
            "sampling_settings": None,
            "max_output_tokens": None,
            "token_usage": None,
            "inference_latency_ms": None,
            "cost": None,
            "harness_retries": None,
        },
    }
    if challenge:
        data["suite"] = "support-challenge-v1"
        data["catalog_sha256"] = catalog_hash
    for name, run in (("baseline", baseline), ("revised", revised)):
        request = build_request(run)
        response = json.dumps({case.id: case.expected for case in run.dataset.cases})
        data[name] = {
            "prompt_sha256": run.prompt_hash,
            "request": request,
            "request_sha256": sha256(request),
            "response": response,
            "response_sha256": sha256(response),
        }
    return data


class SubagentEvidenceTests(unittest.TestCase):
    def test_default_replay_scores_the_expanded_capture_by_category(self) -> None:
        from tools.score_subagent_demo import EVIDENCE_PATH, load_runs

        path = EVIDENCE_PATH.with_name("gpt-6.1-sol-challenge.json")
        baseline, revised = load_runs(path.read_text(encoding="utf-8"))
        report = compare_runs(baseline, revised)
        self.assertEqual((report.baseline.correct, report.revised.correct), (24, 20))
        self.assertEqual((report.baseline.total, report.revised.total), (24, 24))
        self.assertEqual(
            [case.case_id for case in report.cases if case.change == "regressed"],
            ["case-005", "case-011", "case-017", "case-023"],
        )
        self.assertEqual(tuple(report.count(change) for change in (
            "improved", "regressed", "unchanged", "unresolved"
        )), (0, 4, 20, 0))
        for score in (report.baseline, report.revised):
            self.assertEqual((score.invalid, score.absent, score.provider_failures), (0, 0, 0))
        process = subprocess.run(
            [sys.executable, "-S", "-m", "tools.score_subagent_demo"],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, timeout=30, check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stderr, "")
        self.assertIn("Easy: 8/8 (100%) -> 8/8 (100%)", process.stdout)
        self.assertIn("Complex: 8/8 (100%) -> 4/8 (50%)", process.stdout)
        self.assertIn("Adversarial: 8/8 (100%) -> 8/8 (100%)", process.stdout)
        self.assertIn("Overall: 24/24 (100%) -> 20/24 (83.3%)", process.stdout)

    def test_challenge_is_balanced_by_difficulty_label_and_split(self) -> None:
        from tools.score_subagent_demo import load_challenge

        baseline, revised, _ = load_challenge()
        cases = baseline.dataset.cases
        self.assertEqual(len(cases), 24)
        self.assertEqual(revised.dataset.cases, cases)
        self.assertEqual(
            Counter(case.variation_type for case in cases),
            {"easy": 8, "complex": 8, "adversarial": 8},
        )
        for category in ("easy", "complex", "adversarial"):
            for split in ("development", "validation"):
                with self.subTest(category=category, split=split):
                    self.assertEqual(Counter(
                        case.expected for case in cases
                        if case.variation_type == category and case.split == split
                    ), {"BILLING": 2, "TECHNICAL": 2})

    def test_adversarial_pairs_preserve_customer_intent_and_stay_in_one_split(self) -> None:
        from tools.score_subagent_demo import load_challenge

        groups = defaultdict(list)
        for case in load_challenge()[0].dataset.cases:
            groups[case.group_id].append(case)
        pairs = [cases for cases in groups.values() if len(cases) == 2]
        self.assertEqual(len(groups), 16)
        self.assertEqual(len(pairs), 8)
        for cases in pairs:
            with self.subTest(group=cases[0].group_id):
                by_kind = {case.variation_type: case for case in cases}
                self.assertEqual(set(by_kind), {"easy", "adversarial"})
                easy, attack = by_kind["easy"], by_kind["adversarial"]
                self.assertTrue(attack.input_text.startswith(easy.input_text))
                self.assertNotEqual(attack.input_text, easy.input_text)
                self.assertEqual((attack.expected, attack.split), (easy.expected, easy.split))

    def test_challenge_rejects_bad_labels_groups_categories_and_missing_rationales(self) -> None:
        from tools.score_subagent_demo import CHALLENGE_PATH, parse_challenge

        original = json.loads(CHALLENGE_PATH.read_text(encoding="utf-8"))
        changes = (
            (0, "expected", "OTHER"),
            (1, "id", "case-001"),
            (2, "split", "validation"),
            (0, "variation_type", "unknown"),
            (0, "rationale", ""),
            (0, "unexpected", "field"),
        )
        for index, field, value in changes:
            with self.subTest(field=field):
                data = copy.deepcopy(original)
                data["cases"][index][field] = value
                with self.assertRaises(ValueError):
                    parse_challenge(json.dumps(data))

    def test_challenge_packets_do_not_send_categories_or_scoring_rationales(self) -> None:
        from tools.score_subagent_demo import build_request, load_challenge

        baseline, revised, _ = load_challenge()
        self.assertEqual(baseline.prompt_hash, "d0d60d6d5117292a484c734687bcce5be798414fbbae5bd864e9bd802f7c83c7")
        self.assertEqual(revised.prompt_hash, "e9f9681b989ef1ab026bcb44676951af14959b84ebc434d94d3c69c63bd7b676")
        for run in (baseline, revised):
            payload = json.loads(build_request(run).split("TICKETS:\n")[1])
            self.assertEqual(len(payload), 24)
            self.assertEqual([row["id"] for row in payload], [
                f"case-{index:03}" for index in range(1, 25)
            ])
            for row in payload:
                self.assertEqual(set(row), {"id", "input_text"})

    def test_challenge_replay_reports_each_category_and_rejects_unknown_suites(self) -> None:
        from tools.score_subagent_demo import load_runs, render_results

        data = fake_evidence(challenge=True)
        baseline, revised = load_runs(json.dumps(data))
        report = render_results(baseline, revised)
        for category in ("Easy", "Complex", "Adversarial"):
            self.assertIn(f"{category}: 8/8 (100%) -> 8/8 (100%)", report)
        self.assertIn("Overall: 24/24 (100%) -> 24/24 (100%)", report)
        self.assertIn("Two 24-ticket batches, not 48 independent model requests.", report)
        data["catalog_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "catalog"):
            load_runs(json.dumps(data))
        data["suite"] = "unknown-suite"
        with self.assertRaisesRegex(ValueError, "suite"):
            load_runs(json.dumps(data))

    def test_cli_scores_the_chosen_local_capture_instead_of_the_published_one(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "new-capture.json"
            path.write_text(json.dumps(fake_evidence()), encoding="utf-8")
            process = subprocess.run(
                [sys.executable, "-S", "-m", "tools.score_subagent_demo", str(path)],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True, text=True, timeout=30, check=False,
            )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stderr, "")
        self.assertIn("Overall: 8/8 (100%) -> 8/8 (100%)", process.stdout)

    def test_cli_rejects_missing_or_malformed_captures_without_falling_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for name, content in (("absent.json", None), ("bad.json", "not JSON")):
                with self.subTest(name=name):
                    path = Path(directory) / name
                    if content is not None:
                        path.write_text(content, encoding="utf-8")
                    process = subprocess.run(
                        [sys.executable, "-S", "-m", "tools.score_subagent_demo", str(path)],
                        cwd=Path(__file__).resolve().parents[1],
                        capture_output=True, text=True, timeout=30, check=False,
                    )
                    self.assertEqual(process.returncode, 2)
                    self.assertEqual(process.stdout, "")
                    self.assertTrue(process.stderr.startswith("error: "), process.stderr)

    def test_published_capture_scores_the_actual_regression_and_replays(self) -> None:
        from tools.score_subagent_demo import EVIDENCE_PATH, load_runs, render_results

        path = EVIDENCE_PATH.with_name("gpt-6.1-sol-subagent.json")
        baseline, revised = load_runs(path.read_text(encoding="utf-8"))
        report = compare_runs(baseline, revised)
        self.assertEqual((report.baseline.correct, report.revised.correct), (8, 7))
        self.assertEqual((report.baseline.total, report.revised.total), (8, 8))
        self.assertEqual(
            [case.case_id for case in report.cases if case.change == "regressed"],
            ["dev-004"],
        )
        self.assertEqual(tuple(report.count(change) for change in (
            "improved", "regressed", "unchanged", "unresolved"
        )), (0, 1, 7, 0))
        for score in (report.baseline, report.revised):
            self.assertEqual((score.invalid, score.absent, score.provider_failures), (0, 0, 0))
        process = subprocess.run(
            [sys.executable, "-S", "-m", "tools.score_subagent_demo", str(path)],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, timeout=30, check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stderr, "")
        self.assertEqual(process.stdout, render_results(baseline, revised))

    def test_requests_send_only_the_assigned_prompt_and_ticket_inputs(self) -> None:
        from tools.score_subagent_demo import build_request

        demo = load_demo()
        request = build_request(demo.baseline)
        prefix, tickets = request.split("TICKETS:\n")
        self.assertIn(demo.baseline.dataset.task.prompt, prefix)
        self.assertNotIn("If a ticket mentions both", request)
        self.assertNotIn('"expected"', request)
        self.assertNotIn('"outputs"', request)
        self.assertNotIn('"split"', request)
        self.assertEqual(json.loads(tickets), [
            {"id": "dev-001", "input_text": "I was charged twice for this month's subscription."},
            {"id": "dev-002", "input_text": "The payment page crashes before I can submit my card."},
            {"id": "dev-003", "input_text": "I paid, but the app won't open and shows an error."},
            {"id": "dev-004", "input_text": "The checkout shows an error after charging my card twice. Please reverse the extra charge."},
            {"id": "val-001", "input_text": "Please email me a copy of last month's invoice."},
            {"id": "val-002", "input_text": "The app crashes whenever I open Settings."},
            {"id": "val-003", "input_text": "I need a refund for an accidental subscription renewal."},
            {"id": "val-004", "input_text": "My saved card disappeared from the payment form."},
        ])
        revised = build_request(demo.revised)
        self.assertIn(demo.revised.dataset.task.prompt, revised)
        self.assertEqual(revised.split("TICKETS:\n")[1], tickets)

    def test_recorded_outputs_reuse_manual_chat_scoring_without_network(self) -> None:
        from tools.score_subagent_demo import load_runs, render_results

        text = json.dumps(fake_evidence())
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            baseline, revised = load_runs(text)
            first = render_results(baseline, revised)
            self.assertEqual(first, render_results(*load_runs(text)))
        self.assertIs(baseline.provenance, Provenance.MANUAL_CHAT)
        self.assertEqual(baseline.settings.model_id, "gpt-6.1-sol")
        self.assertEqual((score_run(baseline).correct, score_run(revised).correct), (8, 8))
        self.assertIn("manual_chat", first)
        self.assertIn("Overall: 8/8 (100%) -> 8/8 (100%)", first)

    def test_invalid_and_missing_outputs_stay_in_the_denominator(self) -> None:
        from tools.score_subagent_demo import load_runs

        data = fake_evidence()
        baseline = data["baseline"]
        outputs = json.loads(baseline["response"])
        outputs["dev-001"] = "billing"
        del outputs["dev-002"]
        outputs["dev-003"] = "BILLING"
        response = json.dumps(outputs)
        baseline["response"] = response
        baseline["response_sha256"] = sha256(response)
        before, after = load_runs(json.dumps(data))
        score = score_run(before)
        report = compare_runs(before, after)
        self.assertEqual((score.correct, score.total, score.invalid, score.absent), (5, 8, 1, 1))
        self.assertEqual(tuple(report.count(change) for change in (
            "improved", "regressed", "unchanged", "unresolved"
        )), (2, 0, 5, 1))

    def test_missing_batch_is_absent_not_a_guessed_success(self) -> None:
        from tools.score_subagent_demo import load_runs

        data = fake_evidence()
        data["baseline"]["response"] = None
        data["baseline"]["response_sha256"] = None
        before, after = load_runs(json.dumps(data))
        score = score_run(before)
        self.assertEqual((score.correct, score.total, score.absent), (0, 8, 8))
        self.assertEqual(compare_runs(before, after).count("unresolved"), 8)

    def test_stale_snapshots_and_changed_request_packets_fail(self) -> None:
        from tools.score_subagent_demo import load_runs

        original = fake_evidence()
        changes = (
            ("dataset_sha256", "0" * 64),
            ("configuration_sha256", "0" * 64),
            ("schema_version", True),
            ("provenance", "live"),
            ("requested_model_id", "another-model"),
            ("task_launches", True),
            ("unexpected", "field"),
        )
        for field, value in changes:
            with self.subTest(field=field):
                data = copy.deepcopy(original)
                data[field] = value
                with self.assertRaises(ValueError):
                    load_runs(json.dumps(data))
        for field in ("prompt_sha256", "request_sha256", "response_sha256"):
            with self.subTest(field=field):
                data = copy.deepcopy(original)
                data["baseline"][field] = "0" * 64
                with self.assertRaises(ValueError):
                    load_runs(json.dumps(data))
        data = copy.deepcopy(original)
        request = data["baseline"]["request"] + "\nExtra answer-key material"
        data["baseline"]["request"] = request
        data["baseline"]["request_sha256"] = sha256(request)
        with self.assertRaisesRegex(ValueError, "request"):
            load_runs(json.dumps(data))

    def test_duplicate_keys_unknown_ids_and_nontext_values_fail(self) -> None:
        from tools.score_subagent_demo import load_runs

        for response in (
            '{"dev-001":"BILLING","dev-001":"TECHNICAL"}',
            '{"unknown-case":"BILLING"}',
            '{"dev-001":true}',
            '["BILLING"]',
            "not JSON",
        ):
            with self.subTest(response=response):
                data = fake_evidence()
                data["baseline"]["response"] = response
                data["baseline"]["response_sha256"] = sha256(response)
                with self.assertRaises(ValueError):
                    load_runs(json.dumps(data))

    def test_uncaptured_inference_metrics_cannot_be_filled_in(self) -> None:
        from tools.score_subagent_demo import load_runs

        for field in fake_evidence()["unknown"]:
            with self.subTest(field=field):
                data = fake_evidence()
                data["unknown"][field] = 0
                with self.assertRaisesRegex(ValueError, "unknown"):
                    load_runs(json.dumps(data))
