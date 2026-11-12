"""Load authored evidence, never a provider or a fabricated instrumented run."""

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Literal

from .models import (
    ComparisonRules, Example, Observation, Provenance, RunRecord, TaskDefinition, require_text,
)
from .validation import validate_dataset


@dataclass(frozen=True, slots=True)
class Evidence:
    case_id: str
    note: str


@dataclass(frozen=True, slots=True)
class Hypothesis:
    possible_cause: str
    evidence: tuple[Evidence, ...]
    uncertainty: str
    regression_risks: str


@dataclass(frozen=True, slots=True)
class BehavioralCheck:
    source_case_id: str
    question: str
    example: Example
    observation: Observation


@dataclass(frozen=True, slots=True)
class DemoBundle:
    baseline: RunRecord
    revised: RunRecord
    diagnosis: Hypothesis
    check: BehavioralCheck


def _record(
    value: object, required: tuple[str, ...], context: str,
    optional: tuple[str, ...] = (),
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context}: expected a JSON object")
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(f"{context}: fields must have string names")
        result[key] = item
    if not set(required).issubset(result) or not set(result).issubset((*required, *optional)):
        raise ValueError(f"{context}: missing or unknown fields")
    return result


def _text(value: object, context: str) -> str:
    require_text(value, context)
    if not isinstance(value, str):
        raise ValueError(f"{context}: expected text")
    return value


def _list(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{context}: expected a JSON array")
    return list(value)


def _split(value: object) -> Literal["development", "validation"]:
    if value == "development":
        return "development"
    if value == "validation":
        return "validation"
    raise ValueError("case split must be development or validation")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def parse_demo(text: str) -> DemoBundle:
    payload: object = json.loads(text, object_pairs_hook=_unique_object)
    data = _record(payload, (
        "schema_version", "provenance", "task", "dataset_sha256", "configuration_sha256", "cases",
        "baseline", "revised", "diagnosis", "check", "metadata",
    ), "demo")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("demo schema_version must be 1")
    if data["provenance"] != "illustrative":
        raise ValueError("bundled demo provenance must be illustrative")
    metadata = _record(
        data["metadata"], ("model_id", "token_usage", "latency_ms", "cost"), "metadata"
    )
    if any(value is not None for value in metadata.values()):
        raise ValueError("illustrative metadata must remain unknown, not invented")
    task = _record(data["task"], (
        "name", "description", "labels", "dataset_version", "normalization",
    ), "task")
    if task["normalization"] != "exact-v1":
        raise ValueError("the bundled snapshot uses exact-v1 scoring rules")
    labels = tuple(_text(label, "label") for label in _list(task["labels"], "labels"))
    cases = []
    for value in _list(data["cases"], "cases"):
        row = _record(value, ("id", "input_text", "expected", "split"), "case",
                      ("group_id", "variation_type"))
        cases.append(Example(
            id=_text(row["id"], "case id"),
            input_text=_text(row["input_text"], "input_text"),
            expected=_text(row["expected"], "expected"),
            split=_split(row["split"]),
            group_id=None if row.get("group_id") is None else _text(row["group_id"], "group_id"),
            variation_type=None if row.get("variation_type") is None else
            _text(row["variation_type"], "variation_type"),
        ))

    def snapshot(value: object) -> RunRecord:
        saved = _record(value, ("id", "prompt", "prompt_sha256", "outputs"), "snapshot")
        definition = TaskDefinition(
            name=_text(task["name"], "task name"),
            description=_text(task["description"], "task description"),
            prompt=_text(saved["prompt"], "prompt"),
            labels=labels,
            dataset_version=_text(task["dataset_version"], "dataset_version"),
            comparison=ComparisonRules(),
        )
        dataset = validate_dataset(definition, cases)
        outputs = _record(saved["outputs"], tuple(case.id for case in cases), "outputs")
        run = RunRecord(
            id=_text(saved["id"], "snapshot id"),
            dataset=dataset,
            observations=tuple(
                Observation(case.id, _text(outputs[case.id], f"{case.id} output"))
                for case in cases
            ),
            provenance=Provenance.ILLUSTRATIVE,
        )
        if run.prompt_hash != saved["prompt_sha256"]:
            raise ValueError(
                "prompt differs from its saved snapshot; edited prompts require fresh "
                "inference, which this offline demonstrator does not implement"
            )
        if run.dataset_hash != data["dataset_sha256"]:
            raise ValueError("dataset differs from the saved evidence snapshot")
        if run.configuration_hash != data["configuration_sha256"]:
            raise ValueError("configuration differs from the saved evidence snapshot")
        return run

    baseline, revised = snapshot(data["baseline"]), snapshot(data["revised"])
    development_ids = {case.id for case in cases if case.split == "development"}
    diagnosis = _record(data["diagnosis"], (
        "possible_cause", "evidence", "uncertainty", "regression_risks",
    ), "diagnosis")
    evidence = []
    for value in _list(diagnosis["evidence"], "evidence"):
        item = _record(value, ("case_id", "note"), "evidence")
        case_id = _text(item["case_id"], "evidence case_id")
        if case_id not in development_ids:
            raise ValueError("diagnostic evidence must refer only to development cases")
        evidence.append(Evidence(case_id, _text(item["note"], "evidence note")))
    if not evidence:
        raise ValueError("a saved hypothesis requires development evidence")
    check = _record(data["check"], (
        "source_case_id", "question", "input_text", "expected", "baseline_output",
    ), "check")
    source_id = _text(check["source_case_id"], "check source_case_id")
    if source_id not in development_ids:
        raise ValueError("behavioral check must originate from a development case")
    probe = Example(
        id="check-001", input_text=_text(check["input_text"], "check input_text"),
        expected=_text(check["expected"], "check expected"), split="development",
    )
    validate_dataset(baseline.dataset.task, (probe,))
    return DemoBundle(
        baseline, revised,
        Hypothesis(
            _text(diagnosis["possible_cause"], "possible_cause"), tuple(evidence),
            _text(diagnosis["uncertainty"], "uncertainty"),
            _text(diagnosis["regression_risks"], "regression_risks"),
        ),
        BehavioralCheck(
            source_id, _text(check["question"], "check question"), probe,
            Observation(probe.id, _text(check["baseline_output"], "check output")),
        ),
    )


def load_demo() -> DemoBundle:
    return parse_demo(
        files("decision_debugger").joinpath("demos", "support_tickets.json")
        .read_text(encoding="utf-8")
    )
