"""Shared dataset validation used by fixtures, scoring, and reports."""

from collections.abc import Sequence

from .models import Dataset, Example, TaskDefinition


def validate_dataset(task: TaskDefinition, cases: Sequence[Example]) -> Dataset:
    return Dataset(task=task, cases=tuple(cases))
