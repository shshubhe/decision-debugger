import unittest
from dataclasses import FrozenInstanceError

from tests.factories import make_example, make_task


class ValidationTests(unittest.TestCase):
    def test_duplicate_ids_and_unknown_labels_rejected(self) -> None:
        from decision_debugger.validation import validate_dataset

        with self.assertRaisesRegex(ValueError, "case-1.*duplicate"):
            validate_dataset(make_task(), [make_example(), make_example()])
        with self.assertRaisesRegex(ValueError, "case-2.*expected"):
            validate_dataset(make_task(), [make_example(id="case-2", expected="sales")])

    def test_missing_and_oversized_inputs_rejected(self) -> None:
        for value in ("", "   ", "x" * 16_001, None, 12):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaisesRegex(ValueError, "input_text"):
                    make_example(input_text=value)

    def test_missing_required_input_is_not_silently_defaulted(self) -> None:
        from decision_debugger.models import Example

        with self.assertRaisesRegex(TypeError, "input_text"):
            Example(id="case-1", expected="billing", split="development")

    def test_group_cannot_span_splits(self) -> None:
        from decision_debugger.validation import validate_dataset

        with self.assertRaisesRegex(ValueError, "group-1.*development.*validation"):
            validate_dataset(
                make_task(),
                [
                    make_example(group_id="group-1"),
                    make_example(id="case-2", split="validation", group_id="group-1"),
                ],
            )

    def test_group_variations_in_one_split_are_valid(self) -> None:
        from decision_debugger.validation import validate_dataset

        dataset = validate_dataset(
            make_task(),
            [
                make_example(group_id="group-1", variation_type="original"),
                make_example(id="case-2", group_id="group-1", variation_type="paraphrase"),
            ],
        )
        self.assertEqual(tuple(case.id for case in dataset.cases), ("case-1", "case-2"))

    def test_case_boundary_is_strict(self) -> None:
        for changes in ({"id": ""}, {"id": 12}, {"expected": None}, {"split": "test"}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    make_example(**changes)

    def test_task_rejects_duplicate_and_ambiguous_labels(self) -> None:
        from decision_debugger.models import ComparisonRules

        with self.assertRaisesRegex(ValueError, "labels"):
            make_task(labels=("billing", "billing"))
        with self.assertRaisesRegex(ValueError, "labels"):
            make_task(
                labels=("billing", "BILLING"),
                comparison=ComparisonRules(normalization="casefold-v1"),
            )

    def test_task_requires_usable_instructions_and_labels(self) -> None:
        for changes in ({"prompt": " "}, {"prompt": "x" * 16_001}, {"labels": ()}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    make_task(**changes)

    def test_extraction_and_unknown_boundary_fields_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "task_type"):
            make_task(task_type="extraction")
        with self.assertRaisesRegex(TypeError, "api_key"):
            make_task(api_key="not-a-real-secret")

    def test_empty_and_oversized_datasets_rejected(self) -> None:
        from decision_debugger.validation import validate_dataset

        with self.assertRaises(ValueError):
            validate_dataset(make_task(), [])
        with self.assertRaises(ValueError):
            validate_dataset(
                make_task(), [make_example(id=f"case-{index}") for index in range(501)]
            )

    def test_maximum_input_length_is_accepted(self) -> None:
        from decision_debugger.validation import validate_dataset

        dataset = validate_dataset(make_task(), [make_example(input_text="x" * 16_000)])
        self.assertEqual(len(dataset.cases[0].input_text), 16_000)

    def test_snapshots_are_immutable(self) -> None:
        from decision_debugger.validation import validate_dataset

        dataset = validate_dataset(make_task(), [make_example()])
        with self.assertRaises(FrozenInstanceError):
            setattr(dataset.task, "prompt", "Changed without a new version.")
        self.assertIsInstance(dataset.cases, tuple)
        self.assertIsInstance(dataset.task.labels, tuple)

    def test_labels_and_cases_cannot_hide_mutable_lists(self) -> None:
        from decision_debugger.models import Dataset

        with self.assertRaisesRegex(ValueError, "labels"):
            make_task(labels=["billing", "technical"])
        with self.assertRaisesRegex(ValueError, "cases"):
            Dataset(task=make_task(), cases=[make_example()])

    def test_unknown_normalization_version_rejected(self) -> None:
        from decision_debugger.models import ComparisonRules

        with self.assertRaisesRegex(ValueError, "normalization"):
            ComparisonRules(normalization="guess")
