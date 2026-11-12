"""A plain-text, explicit-approval replay of authored illustrative evidence."""

import argparse
import difflib
import sys

from .comparison import compare_runs
from .demo import DemoBundle, load_demo
from .scoring import Evaluation, score_case, score_run


def _summary(title: str, result: Evaluation) -> list[str]:
    lines = [
        f"{title}: {result.correct}/{result.total} correct ({result.accuracy:.1%})",
        f"Invalid: {result.invalid}; provider failures: {result.provider_failures}; "
        f"absent: {result.absent}",
    ]
    for split in ("development", "validation"):
        scores = tuple(score for score in result.scores if score.split == split)
        lines.append(f"  {split}: {sum(score.is_correct for score in scores)}/{len(scores)}")
    return lines


def build_report(demo: DemoBundle, *, approved_revision_hash: str | None = None) -> str:
    if approved_revision_hash is not None and approved_revision_hash != demo.revised.prompt_hash:
        raise ValueError("approval does not match the exact revised prompt snapshot")
    baseline = score_run(demo.baseline)
    source = next(
        case for case in demo.baseline.dataset.cases if case.id == demo.check.source_case_id
    )
    source_score = next(score for score in baseline.scores if score.case_id == source.id)
    check_score = score_case(
        demo.baseline.dataset.task, demo.check.example, demo.check.observation
    )
    lines = [
        "DECISION DEBUGGER",
        "Illustrative demonstration - authored synthetic evidence, not live inference.",
        "No credentials or network access. No real model was evaluated.",
        "",
        "1. ORIGINAL INSTRUCTIONS",
        demo.baseline.dataset.task.prompt,
        "",
        "2. BASELINE (bundled responses, scored deterministically)",
        *_summary("Baseline", baseline),
        "",
        f"{'Case':<9} {'Split':<12} {'Expected':<11} {'Saved output':<12} Result",
    ]
    for score in baseline.scores:
        outcome = "correct" if score.is_correct else score.status
        if score.status == "valid" and not score.is_correct:
            outcome = "incorrect"
        lines.append(
            f"{score.case_id:<9} {score.split:<12} {score.expected:<11} "
            f"{score.actual or '(absent)':<12} {outcome}"
        )
    lines.extend([
        "",
        f"3. INSPECT A DEVELOPMENT FAILURE: {source.id}",
        f"Input: {source.input_text}",
        f"Expected: {source.expected}; saved output: {source_score.actual}",
        f"Possible cause: {demo.diagnosis.possible_cause}",
    ])
    for evidence in demo.diagnosis.evidence:
        lines.append(f"Evidence [{evidence.case_id}]: {evidence.note}")
    lines.extend([
        f"Uncertainty: {demo.diagnosis.uncertainty}",
        "",
        "4. TARGETED BEHAVIORAL CHECK (saved illustration, not a new request)",
        demo.check.question,
        f"Changed input: {demo.check.example.input_text}",
        f"Proposed expected answer: {demo.check.example.expected}",
        f"Authored check output: {demo.check.observation.output}",
        f"Check matches proposed answer: {'yes' if check_score.is_correct else 'no'}",
        "This contrast illustrates a testable hypothesis; it does not prove a cause.",
        "",
        "5. REVIEW THE EXACT PROPOSED EDIT",
        *difflib.unified_diff(
            demo.baseline.dataset.task.prompt.splitlines(),
            demo.revised.dataset.task.prompt.splitlines(),
            fromfile="baseline", tofile="revised", lineterm="",
        ),
        f"Regression risk: {demo.diagnosis.regression_risks}",
        "",
    ])
    if approved_revision_hash is None:
        lines.extend([
            "Approval required before showing the revised saved outputs.",
            "Review the diff, then run: python -m decision_debugger --approve-demo-edit",
            "Approval only reveals the bundled snapshot; it makes no model request.",
        ])
    else:
        comparison = compare_runs(demo.baseline, demo.revised)
        lines.extend([
            "6. APPROVED REPLAY AND COMPARISON",
            f"Approved revised prompt SHA-256: {approved_revision_hash}",
            *_summary("Revised", comparison.revised),
            "  ".join(
                f"{label}: {comparison.count(change)}"
                for label, change in (
                    ("Improved", "improved"), ("Regressed", "regressed"),
                    ("Unchanged", "unchanged"), ("Unresolved", "unresolved"),
                )
            ),
            "",
            f"{'Case':<9} {'Baseline':<12} {'Revised':<12} Change",
        ])
        for case in comparison.cases:
            old = case.baseline.actual if case.baseline else "(absent)"
            new = case.revised.actual if case.revised else "(absent)"
            lines.append(f"{case.case_id:<9} {old or '(absent)':<12} "
                         f"{new or '(absent)':<12} {case.change}")
        lines.extend([
            "",
            "Confounded: " + (", ".join(comparison.confounders) or "no"),
            "The original prompt and both snapshots are preserved.",
            "These authored outcomes are not measured improvements or generalization evidence.",
            "Repeated inspection/tuning weakens validation independence.",
        ])
    lines.extend([
        "",
        f"Dataset: {demo.baseline.dataset.task.dataset_version}",
        f"Dataset SHA-256: {demo.baseline.dataset_hash}",
        f"Scoring: {demo.baseline.dataset.task.comparison.normalization}",
        "Provenance: illustrative; model ID, token usage, and latency are unknown.",
        "Model calls: 0. Cost unavailable.",
    ])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay an illustrative AI-instruction debugging cycle; no model calls."
    )
    parser.add_argument(
        "--approve-demo-edit", action="store_true",
        help="after reviewing the diff, reveal the bundled revised outputs (no inference)",
    )
    args = parser.parse_args(argv)
    try:
        demo = load_demo()
        approval = demo.revised.prompt_hash if args.approve_demo_edit else None
        report = build_report(demo, approved_revision_hash=approval)
    except (ValueError, OSError) as error:
        print(f"Cannot replay bundled demonstration: {error}", file=sys.stderr)
        return 2
    print(report, end="")
    return 0
