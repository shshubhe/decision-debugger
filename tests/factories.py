from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decision_debugger.models import Example, Observation, RunRecord, TaskDefinition


def make_task(**changes: object) -> TaskDefinition:
    from decision_debugger.models import TaskDefinition

    return replace(
        TaskDefinition(
            name="Support tickets",
            description="Classify synthetic support tickets.",
            prompt="Return billing or technical.",
            labels=("billing", "technical"),
            dataset_version="test-v1",
        ),
        **changes,
    )


def make_example(**changes: object) -> Example:
    from decision_debugger.models import Example

    return replace(
        Example(
            id="case-1",
            input_text="My card was charged twice.",
            expected="billing",
            split="development",
        ),
        **changes,
    )


def make_run(
    observations: tuple[Observation, ...],
    cases: tuple[Example, ...] | None = None,
    **changes: object,
) -> RunRecord:
    from decision_debugger.models import RunRecord
    from decision_debugger.validation import validate_dataset

    return replace(
        RunRecord(
            id="test-run",
            dataset=validate_dataset(make_task(), cases or (make_example(),)),
            observations=observations,
        ),
        **changes,
    )
