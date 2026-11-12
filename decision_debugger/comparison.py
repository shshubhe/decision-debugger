"""Paired accuracy changes and explicit non-prompt confounders."""

from dataclasses import dataclass
from typing import Literal

from .models import RunRecord
from .scoring import CaseScore, Evaluation, score_run

Change = Literal["improved", "regressed", "unchanged", "unresolved"]


@dataclass(frozen=True, slots=True)
class CaseComparison:
    case_id: str
    change: Change
    baseline: CaseScore | None
    revised: CaseScore | None


@dataclass(frozen=True, slots=True)
class ComparisonReport:
    baseline: Evaluation
    revised: Evaluation
    cases: tuple[CaseComparison, ...]
    confounders: tuple[str, ...]

    @property
    def confounded(self) -> bool:
        return bool(self.confounders)

    def count(self, change: Change) -> int:
        return sum(case.change == change for case in self.cases)


def compare_runs(baseline: RunRecord, revised: RunRecord) -> ComparisonReport:
    before, after = score_run(baseline), score_run(revised)
    old_scores = {score.case_id: score for score in before.scores}
    new_scores = {score.case_id: score for score in after.scores}
    case_ids = tuple(dict.fromkeys((*baseline.case_ids, *revised.case_ids)))
    changes: list[CaseComparison] = []
    for case_id in case_ids:
        old, new = old_scores.get(case_id), new_scores.get(case_id)
        change: Change
        if old is None or new is None or any(
            score.status in ("provider_failure", "absent") for score in (old, new)
        ):
            change = "unresolved"
        elif new.is_correct and not old.is_correct:
            change = "improved"
        elif old.is_correct and not new.is_correct:
            change = "regressed"
        else:
            change = "unchanged"
        changes.append(CaseComparison(case_id, change, old, new))

    old_task, new_task = baseline.dataset.task, revised.dataset.task
    conditions = (
        ("dataset", baseline.dataset_hash != revised.dataset_hash),
        ("output contract", (old_task.task_type, old_task.labels) !=
         (new_task.task_type, new_task.labels)),
        ("scoring rules", old_task.comparison != new_task.comparison),
        ("settings", baseline.settings != revised.settings),
        ("selected cases", baseline.case_ids != revised.case_ids),
        ("provenance", baseline.provenance != revised.provenance),
        ("schema version", (old_task.schema_version, baseline.schema_version) !=
         (new_task.schema_version, revised.schema_version)),
    )
    return ComparisonReport(
        before, after, tuple(changes),
        tuple(name for name, changed in conditions if changed),
    )
