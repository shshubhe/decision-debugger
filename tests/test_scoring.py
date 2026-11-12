import unittest
from dataclasses import replace

from tests.factories import make_example, make_run, make_task


class ScoringTests(unittest.TestCase):
    def test_exact_matching_does_not_silently_normalize(self) -> None:
        from decision_debugger.models import Observation
        from decision_debugger.scoring import score_case

        for output, status, correct in (
            ("billing", "valid", True),
            ("technical", "valid", False),
            ("BILLING", "invalid", False),
            (" billing ", "invalid", False),
            ("billing because it mentions a card", "invalid", False),
            ("", "invalid", False),
            (None, "invalid", False),
        ):
            with self.subTest(output=output):
                result = score_case(make_task(), make_example(), Observation("case-1", output))
                self.assertEqual((result.status, result.is_correct), (status, correct))

    def test_normalization_is_explicit_and_versioned(self) -> None:
        from decision_debugger.models import ComparisonRules, Observation
        from decision_debugger.scoring import score_case

        for version, output in (
            ("trim-v1", " billing \n"),
            ("casefold-v1", "BILLING"),
            ("trim-casefold-v1", " BILLING \n"),
        ):
            with self.subTest(version=version):
                task = make_task(comparison=ComparisonRules(normalization=version))
                self.assertTrue(
                    score_case(task, make_example(), Observation("case-1", output)).is_correct
                )

    def test_failures_and_invalid_outputs_stay_in_denominator(self) -> None:
        from decision_debugger.models import Observation
        from decision_debugger.scoring import score_run

        cases = tuple(make_example(id=f"case-{index}") for index in range(1, 5))
        run = make_run(
            (
                Observation("case-1", "billing"),
                Observation("case-2", "technical"),
                Observation("case-3", "unknown"),
                Observation("case-4", status="provider_failure", error="timeout"),
            ),
            cases,
        )
        result = score_run(run)
        self.assertEqual((result.correct, result.total, result.accuracy), (1, 4, 0.25))
        self.assertEqual((result.invalid, result.provider_failures, result.absent), (1, 1, 0))

    def test_absent_results_are_distinct_and_not_dropped(self) -> None:
        from decision_debugger.models import Observation
        from decision_debugger.scoring import score_run

        result = score_run(
            make_run(
                (Observation("case-1", "billing"),),
                (make_example(), make_example(id="case-2")),
            )
        )
        self.assertEqual((result.correct, result.total, result.absent), (1, 2, 1))
        self.assertEqual(result.scores[1].status, "absent")

    def test_mismatched_case_response_is_rejected(self) -> None:
        from decision_debugger.models import Observation
        from decision_debugger.scoring import score_case

        with self.assertRaisesRegex(ValueError, "case"):
            score_case(make_task(), make_example(), Observation("other-case", "billing"))

    def test_observation_status_cannot_masquerade_as_output(self) -> None:
        from decision_debugger.models import Observation

        for changes in (
            {"status": "success"},
            {"output": 123},
            {"status": "provider_failure", "error": None},
            {"status": "provider_failure", "output": "billing", "error": "timeout"},
            {"status": "absent", "output": "billing"},
            {"error": "unexpected"},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    Observation("case-1", **changes)

    def test_duplicate_and_unknown_observations_rejected(self) -> None:
        from decision_debugger.models import Observation

        for observations in (
            (Observation("case-1", "billing"), Observation("case-1", "technical")),
            (Observation("unknown", "billing"),),
        ):
            with self.assertRaisesRegex(ValueError, "observation"):
                make_run(observations)

    def test_selected_cases_are_unique_known_and_nonempty(self) -> None:
        from decision_debugger.models import Observation

        for selection in ((), ("unknown",), ("case-1", "case-1"), ["case-1"]):
            with self.subTest(selection=selection):
                with self.assertRaisesRegex(ValueError, "selected"):
                    make_run((Observation("case-1", "billing"),), selected_ids=selection)

    def test_generation_settings_are_strict_and_finite(self) -> None:
        from decision_debugger.models import RunSettings

        for changes in (
            {"max_output_tokens": True},
            {"max_output_tokens": 0},
            {"temperature": float("nan")},
            {"temperature": float("inf")},
            {"temperature": "0"},
            {"model_id": ""},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    RunSettings(**changes)

    def test_prompt_edit_does_not_change_dataset_hash(self) -> None:
        from decision_debugger.models import Observation
        from decision_debugger.validation import validate_dataset

        run = make_run((Observation("case-1", "billing"),))
        edited = replace(
            run, dataset=validate_dataset(make_task(prompt="A different prompt."), run.dataset.cases)
        )
        self.assertNotEqual(run.prompt_hash, edited.prompt_hash)
        self.assertEqual(run.dataset_hash, edited.dataset_hash)
        self.assertEqual(run.configuration_hash, edited.configuration_hash)
        self.assertEqual(run.dataset.task.prompt, "Return billing or technical.")


class ComparisonTests(unittest.TestCase):
    def test_all_four_change_categories(self) -> None:
        from decision_debugger.comparison import compare_runs
        from decision_debugger.models import Observation

        cases = tuple(make_example(id=f"case-{index}") for index in range(1, 5))
        baseline = make_run(
            (
                Observation("case-1", "technical"),
                Observation("case-2", "billing"),
                Observation("case-3", "technical"),
                Observation("case-4", status="provider_failure", error="timeout"),
            ),
            cases,
        )
        revised = make_run(
            tuple(Observation(case.id, output) for case, output in zip(
                cases, ("billing", "technical", "technical", "billing"), strict=True
            )),
            cases,
        )
        result = compare_runs(baseline, revised)
        self.assertEqual(
            tuple(row.change for row in result.cases),
            ("improved", "regressed", "unchanged", "unresolved"),
        )
        self.assertFalse(result.confounded)

    def test_invalid_response_can_improve_or_regress(self) -> None:
        from decision_debugger.comparison import compare_runs
        from decision_debugger.models import Observation

        correct = make_run((Observation("case-1", "billing"),))
        invalid = make_run((Observation("case-1", "not a label"),))
        self.assertEqual(compare_runs(invalid, correct).cases[0].change, "improved")
        self.assertEqual(compare_runs(correct, invalid).cases[0].change, "regressed")

    def test_missing_result_remains_unresolved(self) -> None:
        from decision_debugger.comparison import compare_runs
        from decision_debugger.models import Observation

        self.assertEqual(
            compare_runs(make_run(()), make_run((Observation("case-1", "billing"),)))
            .cases[0].change,
            "unresolved",
        )

    def test_prompt_only_edit_is_not_confounded(self) -> None:
        from decision_debugger.comparison import compare_runs
        from decision_debugger.models import Observation
        from decision_debugger.validation import validate_dataset

        baseline = make_run((Observation("case-1", "billing"),))
        revised = replace(
            baseline,
            dataset=validate_dataset(make_task(prompt="New instructions."), baseline.dataset.cases),
        )
        self.assertFalse(compare_runs(baseline, revised).confounded)

    def test_non_prompt_changes_are_flagged(self) -> None:
        from decision_debugger.comparison import compare_runs
        from decision_debugger.models import ComparisonRules, Observation, Provenance, RunSettings
        from decision_debugger.validation import validate_dataset

        baseline = make_run((Observation("case-1", "billing"),))
        revisions = (
            ("settings", replace(baseline, settings=RunSettings(model_id="test-model"))),
            ("settings", replace(baseline, settings=RunSettings(max_output_tokens=128))),
            ("settings", replace(baseline, settings=RunSettings(endpoint="https://example.invalid"))),
            ("provenance", replace(baseline, provenance=Provenance.MANUAL_CHAT)),
            ("output contract", replace(baseline, dataset=validate_dataset(
                make_task(labels=("billing", "technical", "sales")), baseline.dataset.cases
            ))),
            ("scoring rules", replace(baseline, dataset=validate_dataset(
                make_task(comparison=ComparisonRules(normalization="trim-v1")),
                baseline.dataset.cases
            ))),
            ("dataset", replace(baseline, dataset=validate_dataset(
                make_task(dataset_version="test-v2"), baseline.dataset.cases
            ))),
            ("dataset", replace(baseline, dataset=validate_dataset(
                make_task(), (make_example(split="validation"),)
            ))),
            ("dataset", replace(baseline, dataset=validate_dataset(
                make_task(), (make_example(input_text="A different ticket."),)
            ))),
            ("dataset", replace(baseline, dataset=validate_dataset(
                make_task(), (make_example(expected="technical"),)
            ))),
        )
        for reason, revised in revisions:
            with self.subTest(reason=reason, revised=revised):
                result = compare_runs(baseline, revised)
                self.assertTrue(result.confounded)
                self.assertIn(reason, result.confounders)

    def test_selection_change_includes_unpaired_case_as_unresolved(self) -> None:
        from decision_debugger.comparison import compare_runs
        from decision_debugger.models import Observation

        cases = (make_example(), make_example(id="case-2"))
        baseline = make_run(
            (Observation("case-1", "billing"), Observation("case-2", "billing")), cases
        )
        revised = make_run(
            (Observation("case-1", "billing"),), cases, selected_ids=("case-1",)
        )
        result = compare_runs(baseline, revised)
        self.assertIn("selected cases", result.confounders)
        self.assertEqual(result.cases[1].change, "unresolved")
