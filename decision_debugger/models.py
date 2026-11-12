"""Strict, immutable classification boundaries with no third-party imports."""

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Literal


def require_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 16_000:
        raise ValueError(f"{field_name} must be a non-empty string of at most 16000 characters")


@dataclass(frozen=True, slots=True)
class ComparisonRules:
    normalization: Literal[
        "exact-v1", "trim-v1", "casefold-v1", "trim-casefold-v1"
    ] = "exact-v1"

    def __post_init__(self) -> None:
        if self.normalization not in (
            "exact-v1", "trim-v1", "casefold-v1", "trim-casefold-v1"
        ):
            raise ValueError("normalization must name a supported, versioned rule")

    def normalize(self, value: str) -> str:
        if self.normalization in ("trim-v1", "trim-casefold-v1"):
            value = value.strip()
        if self.normalization in ("casefold-v1", "trim-casefold-v1"):
            value = value.casefold()
        return value


@dataclass(frozen=True, slots=True)
class TaskDefinition:
    name: str
    description: str
    prompt: str
    labels: tuple[str, ...]
    dataset_version: str
    comparison: ComparisonRules = field(default_factory=ComparisonRules)
    task_type: Literal["classification"] = "classification"
    schema_version: int = 1

    def __post_init__(self) -> None:
        for name in ("name", "description", "prompt", "dataset_version"):
            require_text(getattr(self, name), name)
        if self.task_type != "classification":
            raise ValueError("task_type must be classification in this demonstrator")
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("schema_version must be 1")
        if not isinstance(self.comparison, ComparisonRules):
            raise ValueError("comparison must be ComparisonRules")
        if not isinstance(self.labels, tuple) or not self.labels:
            raise ValueError("labels must be a non-empty tuple")
        for label in self.labels:
            require_text(label, "labels")
        normalized = tuple(self.comparison.normalize(label) for label in self.labels)
        if len(set(normalized)) != len(normalized):
            raise ValueError("labels must be unique under the selected comparison rules")


@dataclass(frozen=True, slots=True)
class Example:
    id: str
    input_text: str
    expected: str
    split: Literal["development", "validation"]
    group_id: str | None = None
    variation_type: str | None = None

    def __post_init__(self) -> None:
        for name in ("id", "input_text", "expected"):
            require_text(getattr(self, name), name)
        if self.split not in ("development", "validation"):
            raise ValueError(f"{self.id}: split must be development or validation")
        for name in ("group_id", "variation_type"):
            value = getattr(self, name)
            if value is not None:
                require_text(value, name)


@dataclass(frozen=True, slots=True)
class Dataset:
    task: TaskDefinition
    cases: tuple[Example, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.task, TaskDefinition):
            raise ValueError("task must be a TaskDefinition")
        if not isinstance(self.cases, tuple) or not 1 <= len(self.cases) <= 500:
            raise ValueError("cases must be a tuple containing 1 to 500 examples")
        seen: set[str] = set()
        groups: dict[str, str] = {}
        for case in self.cases:
            if not isinstance(case, Example):
                raise ValueError("cases must contain Example values")
            if case.id in seen:
                raise ValueError(f"{case.id}: duplicate example ID")
            seen.add(case.id)
            if case.expected not in self.task.labels:
                raise ValueError(f"{case.id}: expected must be one of the task labels")
            if case.group_id is not None:
                prior_split = groups.setdefault(case.group_id, case.split)
                if prior_split != case.split:
                    raise ValueError(
                        f"{case.group_id}: group cannot span development and validation"
                    )


class Provenance(StrEnum):
    ILLUSTRATIVE = "illustrative"
    MANUAL_CHAT = "manual_chat"
    LIVE = "live"


@dataclass(frozen=True, slots=True)
class RunSettings:
    provider: str | None = None
    endpoint: str | None = None
    model_id: str | None = None
    max_output_tokens: int | None = None
    temperature: float | None = None

    def __post_init__(self) -> None:
        for name in ("provider", "endpoint", "model_id"):
            value = getattr(self, name)
            if value is not None:
                require_text(value, name)
        if self.max_output_tokens is not None and (
            type(self.max_output_tokens) is not int or self.max_output_tokens <= 0
        ):
            raise ValueError("max_output_tokens must be a positive integer or None")
        if self.temperature is not None and (
            type(self.temperature) not in (int, float) or not math.isfinite(self.temperature)
        ):
            raise ValueError("temperature must be finite numeric data or None")


@dataclass(frozen=True, slots=True)
class Observation:
    case_id: str
    output: str | None = None
    status: Literal["response", "provider_failure", "absent"] = "response"
    error: str | None = None

    def __post_init__(self) -> None:
        require_text(self.case_id, "case_id")
        if self.status not in ("response", "provider_failure", "absent"):
            raise ValueError("observation status is not supported")
        if self.output is not None and not isinstance(self.output, str):
            raise ValueError("observation output must be text or None")
        if self.status != "response" and self.output is not None:
            raise ValueError("failure/absent observation cannot contain output")
        if self.status == "provider_failure":
            require_text(self.error, "provider_failure error")
        elif self.error is not None:
            raise ValueError("only a provider_failure observation may contain an error")


def content_hash(value: object) -> str:
    serialized = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RunRecord:
    id: str
    dataset: Dataset
    observations: tuple[Observation, ...]
    settings: RunSettings = field(default_factory=RunSettings)
    provenance: Provenance = Provenance.ILLUSTRATIVE
    selected_ids: tuple[str, ...] | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        require_text(self.id, "run id")
        if not isinstance(self.dataset, Dataset) or not isinstance(self.settings, RunSettings):
            raise ValueError("run dataset/settings must use the validated models")
        if not isinstance(self.provenance, Provenance):
            raise ValueError("run provenance must be an explicit Provenance value")
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("run schema_version must be 1")
        selection = self.case_ids
        if (
            not isinstance(selection, tuple)
            or not selection
            or not all(isinstance(item, str) for item in selection)
            or len(set(selection)) != len(selection)
            or not set(selection).issubset(case.id for case in self.dataset.cases)
        ):
            raise ValueError("selected IDs must be a non-empty tuple of unique known case IDs")
        if not isinstance(self.observations, tuple):
            raise ValueError("observations must be a tuple")
        seen: set[str] = set()
        for observation in self.observations:
            if not isinstance(observation, Observation):
                raise ValueError("observations must contain Observation values")
            if observation.case_id not in selection or observation.case_id in seen:
                raise ValueError("observation IDs must be unique and belong to selected cases")
            seen.add(observation.case_id)

    @property
    def case_ids(self) -> tuple[str, ...]:
        if self.selected_ids is None:
            return tuple(case.id for case in self.dataset.cases)
        return self.selected_ids

    @property
    def prompt_hash(self) -> str:
        return hashlib.sha256(self.dataset.task.prompt.encode("utf-8")).hexdigest()

    @property
    def dataset_hash(self) -> str:
        return content_hash({
            "version": self.dataset.task.dataset_version,
            "cases": [asdict(case) for case in self.dataset.cases],
        })

    @property
    def configuration_hash(self) -> str:
        task = self.dataset.task
        return content_hash({
            "task_type": task.task_type,
            "task_schema_version": task.schema_version,
            "run_schema_version": self.schema_version,
            "labels": task.labels,
            "normalization": task.comparison.normalization,
            "settings": asdict(self.settings),
            "selected_ids": self.case_ids,
            "provenance": self.provenance,
        })
