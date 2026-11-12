# Security and data handling

This offline demonstrator has no provider integration, credential handling,
network client, telemetry, web server, or automatic code execution from model
output. It reads a bundled synthetic JSON fixture and prints plain text.
It does not evaluate arbitrary user prompts or import external datasets.

The demonstration responses and diagnostic notes are untrusted content, not
instructions for the program. Keep them as text. Do not add `eval`, `exec`,
shell execution, or unsafe HTML rendering for fixture or response content.

Do not put real customer tickets, personal information, API keys, or other
secrets in fixtures, screenshots, reports, or issue descriptions. Redirected
output becomes a local file; review it before sharing.

Snapshot hashes detect inconsistent edits but do not authenticate the fixture
or prove inference occurred. The approval flag reveals saved results only;
it is not a security boundary or permission to contact a provider.

For an ordinary bug, open an issue with synthetic reproduction data. For a
sensitive report, use GitHub's private vulnerability reporting if enabled on
the repository. If it is unavailable, do not disclose secrets or exploit details
in a public issue; request a private reporting channel first.
