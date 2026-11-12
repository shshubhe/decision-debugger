# Contributing

Use Python 3.12 or newer. No dependency installation is needed.
From the repository root:

```console
python -S -m unittest discover -s tests -v
python -S -m tools.score_subagent_demo
python -m decision_debugger
python -m decision_debugger --approve-demo-edit
python -S -m tools.build_demo
```

The tests also execute the built archive outside the checkout in isolated Python.
The checked-in expected output must match the approved replay exactly.

Keep changes small and add a focused failing test before implementing behavior.
Keep validation and scoring independent of presentation and reuse the shared
domain rules. Include failed and absent responses in scoring denominators.

Keep the two evidence types separate. The workflow fixture's responses,
hypothesis, and check are authored and explicitly `illustrative`. The published
`manual_chat` captures contain actual visible subagent responses, not application
API telemetry. Preserve exact requests/responses and truthful unknown settings,
backend identity, usage, latency, and cost; never invent metrics or relabel an
authored outcome as measured.

The default scorer replays the 24-case challenge. It also accepts a capture path;
the original eight-case record is `examples\gpt-6.1-sol-subagent.json` (use `/`
instead of `\` on macOS/Linux). This validates these specific experiments, not
arbitrary models. A replay is not a new inference run.

Preserve historical captures. New model experiments need separate records and
explicit execution/publication approval; keep private runs under ignored `runs/`.
Do not send expected answers, rationales, categories, or splits in evaluated
requests. Keep clean/adversarial variants in one split. Use development cases
for diagnosis or repair suggestions, and new unseen cases for future validation.
Report validation outcomes without treating them as repair-design inputs.

A changed illustrative fixture needs consistent versioned snapshots and an
updated expected-output sample, not just a changed answer to make a test pass.
Keep README tables and the illustration aligned with their respective evidence.

Do not add network requests, credentials, or live inference to ordinary tests or
CI. Do not commit real tickets, private datasets, local runs, or environment files.
The archive builder must retain an explicit public-file allowlist.
