"""Deterministic classification scoring; failures stay in the denominator."""

from dataclasses import dataclass
from typing import Literal

from .models import Example, Observation, RunRecord, TaskDefinition


@dataclass(frozen=True, slots=True)
class CaseScore:
    case_id: str
    split: Literal["development", "validation"]
    expected: str
    actual: str | None
    status: Literal["valid", "invalid", "provider_failure", "absent"]
    is_correct: bool


@dataclass(frozen=True, slots=True)
class Evaluation:
    scores: tuple[CaseScore, ...]

    @property
    def total(self) -> int:
        return len(self.scores)

    @property
    def correct(self) -> int:
        return sum(score.is_correct for score in self.scores)

    @property
    def accuracy(self) -> float:
        return self.correct / self.total

    @property
    def invalid(self) -> int:
        return sum(score.status == "invalid" for score in self.scores)

    @property
    def provider_failures(self) -> int:
        return sum(score.status == "provider_failure" for score in self.scores)

    @property
    def absent(self) -> int:
        return sum(score.status == "absent" for score in self.scores)


def score_case(task: TaskDefinition, case: Example, observation: Observation) -> CaseScore:
    if observation.case_id != case.id:
        raise ValueError("observation case ID must match the scored example")
    if case.expected not in task.labels:
        raise ValueError(f"{case.id}: expected must be one of the task labels")
    if observation.status in ("provider_failure", "absent"):
        return CaseScore(
            case.id, case.split, case.expected, None, observation.status, False
        )
    actual = observation.output
    normalize = task.comparison.normalize
    if actual is None or normalize(actual) not in {normalize(label) for label in task.labels}:
        return CaseScore(case.id, case.split, case.expected, actual, "invalid", False)
    return CaseScore(
        case.id, case.split, case.expected, actual, "valid",
        normalize(actual) == normalize(case.expected),
    )


def score_run(run: RunRecord) -> Evaluation:
    examples = {case.id: case for case in run.dataset.cases}
    observations = {item.case_id: item for item in run.observations}
    return Evaluation(tuple(
        score_case(
            run.dataset.task,
            examples[case_id],
            observations.get(case_id, Observation(case_id, status="absent")),
        )
        for case_id in run.case_ids
    ))
