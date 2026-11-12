# Contributing

Use Python 3.12 or newer. No dependency installation is needed.
From the repository root:

```console
python -S -m unittest discover -s tests -v
python -m decision_debugger
python -m decision_debugger --approve-demo-edit
python -S -m tools.build_demo
```

The tests also execute the built archive outside the checkout in isolated Python.
The checked-in expected output must match the approved replay exactly.

Keep changes small and add a focused failing test before implementing behavior.
Keep validation and scoring independent of presentation and reuse the shared
domain rules. Include failed and absent responses in scoring denominators.

Fixtures must remain synthetic and explicitly illustrative. Do not invent model
identifiers, usage, latency, or cost, or describe authored outcomes as measured
improvements. A changed fixture needs consistent versioned snapshots and an
updated expected-output sample, not just a changed answer to make a test pass.
Use development cases for diagnostic evidence; preserve the validation split.

Do not add network requests, credentials, or live inference to ordinary tests or
CI. Do not commit real tickets, private datasets, local runs, or environment files.
The archive builder must retain an explicit public-file allowlist.
