# Synthetic agent-input packets

These files are newly authored fictional examples. They are not research findings, benchmark results, or transformed pilot data.

The packets demonstrate the two agent-import contracts:

```bash
azoth connect --from-file examples/synthetic-agent-input/connections.json
azoth detect --from-file examples/synthetic-agent-input/hypotheses.json
```

They are documentation rather than a complete runtime workspace. Before importing them, a target workspace must already contain registry and schema-valid library records for `synthetic_001`, `synthetic_002`, and `synthetic_003`, all in the `operations_research` domain.

Import validation forces every artifact to `pending_review`. It does not accept a connection, establish novelty, or approve a hypothesis.
