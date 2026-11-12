# Decision Debugger

An evidence-backed approach to debugging AI instructions:

**Test -> inspect a failure -> form a hypothesis -> check it -> review a minimal
edit -> approve -> compare fixes and regressions.**

This repository is a **runnable, illustrative offline demonstrator**, not a live
model evaluation service. All responses, diagnostic notes, and behavioral-check
results are authored synthetic evidence. Scoring and comparison are real,
deterministic Python code; the results are not measurements of any model.

## Run it

Use **Python 3.12 or newer**. From the repository root:

```console
python -m decision_debugger
```

There is nothing to install: no third-party packages, API keys, server, or network
access. A virtual environment is optional. This is a run-from-source project,
not a `pip install` package.

The first run shows the baseline, a selected failure, a possible explanation,
the saved check, and the exact proposed prompt diff. It stops before showing
the revised results. After reviewing the diff:

```console
python -m decision_debugger --approve-demo-edit
```

This flag reveals the bundled revised snapshot. It does not call a model, edit
files, or generate new responses. Both runs only print a report.

See the complete [expected output](examples/expected_output.txt).

## What the demonstration shows

Eight synthetic support tickets are classified as `BILLING` or `TECHNICAL`.
The original instructions sometimes prioritize payment wording over a technical
failure. A development-only hypothesis and a wording-change check motivate this
additional instruction:

> If a ticket mentions both payment and a crash or error, choose TECHNICAL.

The authored before/after outcomes deliberately include a downside:

| Cases | Baseline | Revised |
| --- | --- | --- |
| Development | 2/4 correct (50%) | 3/4 correct (75%) |
| Validation | 3/4 correct (75%) | 3/4 correct (75%) |
| Overall | 5/8 correct (62.5%) | 6/8 correct (75%) |

**Two fixes, one regression, five unchanged cases, zero unresolved cases.**
The revised rule mishandles a duplicate-charge refund request (`dev-004`).
Validation performance does not improve, and `val-004` remains wrong.

These numbers demonstrate how the comparison works, **not that this prompt edit
improves a real model**. The hypothesis is not access to internal reasoning.
Repeatedly inspecting or tuning against validation cases weakens their independence.
Model ID, token usage, latency, and cost are unknown; application model calls are zero.

## How it works

The [bundled fixture](decision_debugger/demos/support_tickets.json) contains the
original and revised prompts, examples, saved responses, and development-only
diagnostic evidence. Prompt, dataset, and configuration hashes bind the saved
responses to their snapshots. Changing a prompt, case data, or output contract
without updating its snapshot hash is rejected. No edit generates fresh inference.
These hashes are not signatures or proof that a model ran.

Frozen dataclasses validate inputs. Shared scoring preserves all selected cases
in the denominator, distinguishes invalid responses from provider failures and
missing responses, and reports improved, regressed, unchanged, and unresolved
cases. Non-prompt changes are flagged as confounded comparisons.

The current CLI handles only this classification walkthrough. Live connections,
arbitrary prompt evaluation or dataset imports, extraction, a web UI, and persistent
run storage are **not implemented**.

## Checks and standalone archive

Run the standard-library tests with site packages disabled:

```console
python -S -m unittest discover -s tests -v
```

Build a standalone Python archive without installing build tools:

```console
python -S -m tools.build_demo
```

From the resulting `dist` directory, run:

```console
python -I -S decision-debugger.pyz --approve-demo-edit
```

The archive needs Python, but not the checkout or installed packages. Its explicit
file allowlist includes only the runtime, synthetic fixture, README, and license.
CI is configured for Python 3.12-3.14 on Windows and Linux; tests make no model calls.

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).
Licensed under [MIT](LICENSE).
