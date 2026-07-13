# Operations Decision Support v1

This directory freezes the public metadata for a 12-source benchmark spanning
prescriptive operations, ML/data-science planning, and human/organizational
decision-making. The balanced 4/4/4 slate yields 66 canonical unordered pairs.

`sources.yaml` is the identity-bearing manifest. Its canonical JSON digest is
used by the later benchmark freeze. `selection-log.yaml` records the one
human-approved replacement and the source-access evidence that motivated it.

Third-party source bytes are never committed. Every record is `fetch_only`,
including sources whose authors selected a Creative Commons license. Exact PDF
bytes and retrieval evidence belong in the operator-controlled private source
directory. Rights descriptions report only terms directly declared by the
source record or PDF; absence of a document-specific license is not interpreted
as permission to redistribute.

The source text was checked as readable, born-digital PDF text. These records do
not contain gold pair labels, adjudication, or benchmark acceptance decisions.

The benchmark protocol is frozen. The public freeze manifest commits to the
private, Rafael-authoritative 66-pair gold packet and complete blinded-generation
schema by canonical SHA-256 without publishing labels, rationales, evidence,
source filenames, or private paths.

## P6 benchmark tooling

The P6 CLI keeps public preparation and generation separate from private
scoring. Use explicit paths; the commands do not discover gold through an
environment variable, parent directory, or conventional filename.

```bash
BENCHMARK=benchmarks/operations-decision-support-v1
PRIVATE_ROOT=/absolute/path/outside/this/repository

azoth benchmark validate --benchmark-root "$BENCHMARK"

azoth benchmark fetch \
  --benchmark-root "$BENCHMARK" \
  --source-dir "$PRIVATE_ROOT/sources" \
  --repo-root .

azoth benchmark prepare \
  --benchmark-root "$BENCHMARK" \
  --source-dir "$PRIVATE_ROOT/sources" \
  --output "$PRIVATE_ROOT/prepared.json" \
  --repo-root .

azoth benchmark run \
  --prepared "$PRIVATE_ROOT/prepared.json" \
  --output "$PRIVATE_ROOT/run.json" \
  --backend fallback \
  --seed 5607
```

The fallback is a deterministic engineering baseline over blinded visible
records. It is not a model-quality result. Externally generated responses can
instead be locked with `azoth benchmark run --responses RESPONSES.json`; the
import must cover every prepared pair and cannot contain gold-only fields.

Only after the run is locked may the explicit scoring path receive gold:

```bash
azoth benchmark score \
  --benchmark-root "$BENCHMARK" \
  --run "$PRIVATE_ROOT/run.json" \
  --gold "$PRIVATE_ROOT/gold/operations-decision-support-v1.json" \
  --output "$PRIVATE_ROOT/score.json" \
  --repo-root .

azoth benchmark report \
  --score "$PRIVATE_ROOT/score.json" \
  --output "$PRIVATE_ROOT/report.md"
```

`azoth benchmark validate --artifact PATH` validates prepared, run, or score
JSON without loading private gold. `score` verifies the exact frozen gold
commitment before calculation. Metrics requiring separate OOD or human-review
annotations remain undefined with numerator and denominator zero unless an
explicit external `--annotations` packet is supplied.

The six fictional records in `synthetic/` exercise the same contracts in the
test suite, including offline fetch, all 15 fictional pairs, deterministic run,
all 13 metric records, and byte-identical report rendering. Every fictional
report is marked:

**SYNTHETIC CONTRACT TEST — NOT A PERFORMANCE CLAIM**

No fictional value supports a claim about the frozen 12-paper benchmark or any
model.

## P7 locked execution

P7 adds a preregistered execution amendment before any real output or score.
It defines the six deterministic comparisons, the qualitative model-response
adapter, exact lock order, and model-provenance limitation without changing the
P5 gold commitment, rubric, metrics, thresholds, or no-retuning rule.

The completed aggregate evaluation is in [`results/`](results/README.md), with
all seven run identities and all 13 frozen metric records per run. The public
files contain no raw gold labels, human rationales, source bytes, private paths,
or pair-level failure details. Missed thresholds and undefined populations are
retained without retuning or imputation.

Validate the amendment and generate each gold-blind baseline from one prepared
artifact:

```bash
azoth benchmark validate \
  --benchmark-root "$BENCHMARK" \
  --artifact "$BENCHMARK/execution-manifest.yaml"

azoth benchmark baseline \
  --prepared "$PRIVATE_ROOT/lock/prepared.json" \
  --execution-manifest "$BENCHMARK/execution-manifest.yaml" \
  --run-id shared_tag \
  --output "$PRIVATE_ROOT/lock/runs/shared_tag.json" \
  --repo-root .
```

After producing one validated raw response JSON per blinded pair, adapt the
complete model run and seal all seven runs:

```bash
azoth benchmark adapt \
  --prepared "$PRIVATE_ROOT/lock/prepared.json" \
  --execution-manifest "$BENCHMARK/execution-manifest.yaml" \
  --responses-dir "$PRIVATE_ROOT/responses/accepted" \
  --provenance "$PRIVATE_ROOT/responses/provenance.json" \
  --output "$PRIVATE_ROOT/lock/runs/model_5_6_sol.json" \
  --repo-root .

azoth benchmark lock \
  --benchmark-root "$BENCHMARK" \
  --prepared "$PRIVATE_ROOT/lock/prepared.json" \
  --execution-manifest "$BENCHMARK/execution-manifest.yaml" \
  --run model_5_6_sol="$PRIVATE_ROOT/lock/runs/model_5_6_sol.json" \
  --run deterministic_routing="$PRIVATE_ROOT/lock/runs/deterministic_routing.json" \
  --run all_pairs="$PRIVATE_ROOT/lock/runs/all_pairs.json" \
  --run shared_tag="$PRIVATE_ROOT/lock/runs/shared_tag.json" \
  --run hash_embedding="$PRIVATE_ROOT/lock/runs/hash_embedding.json" \
  --run current_score="$PRIVATE_ROOT/lock/runs/current_score.json" \
  --run fixed_seed_random="$PRIVATE_ROOT/lock/runs/fixed_seed_random.json" \
  --output "$PRIVATE_ROOT/lock/lock-manifest.json" \
  --repo-root . \
  --implementation-git-sha "$(git rev-parse HEAD)"
```

Only after the sealed lock verifies may the operator create annotations, score,
report, and compare:

```bash
azoth benchmark annotations \
  --benchmark-root "$BENCHMARK" \
  --run "$PRIVATE_ROOT/lock/runs/model_5_6_sol.json" \
  --lock "$PRIVATE_ROOT/lock/lock-manifest.json" \
  --output "$PRIVATE_ROOT/evaluation/annotations.json" \
  --repo-root .

azoth benchmark score \
  --benchmark-root "$BENCHMARK" \
  --run "$PRIVATE_ROOT/lock/runs/model_5_6_sol.json" \
  --lock "$PRIVATE_ROOT/lock/lock-manifest.json" \
  --execution-manifest "$BENCHMARK/execution-manifest.yaml" \
  --gold "$PRIVATE_ROOT/../p5-benchmark/gold/operations-decision-support-v1.json" \
  --annotations "$PRIVATE_ROOT/evaluation/annotations.json" \
  --output "$PRIVATE_ROOT/evaluation/model-score.json" \
  --repo-root .

azoth benchmark report \
  --score "$PRIVATE_ROOT/evaluation/model-score.json" \
  --output "$PRIVATE_ROOT/evaluation/model-report.md"

azoth benchmark compare \
  --lock "$PRIVATE_ROOT/lock/lock-manifest.json" \
  --score model_5_6_sol="$PRIVATE_ROOT/evaluation/model-score.json" \
  --output "$PRIVATE_ROOT/evaluation/comparison.json" \
  --repo-root .
```

`compare` requires all seven `--score RUN_ID=PATH` values; the shortened example
shows the option shape only. Full failure-analysis rendering additionally
requires all seven `--run` values and explicit gold/annotation/output paths.
Neither `baseline`, `adapt`, nor `lock` accepts gold.

## Private local adjudication

The human authority can review the randomized packet through a loopback-only
browser interface. The command refuses private inputs inside the repository,
verifies the source bytes against `sources.yaml`, and saves each explicit answer
atomically to the private packet:

```bash
uv run python scripts/serve_benchmark_adjudication.py \
  --private-gold "$AZOTH_P5_PRIVATE_ROOT/gold/operations-decision-support-v1.json" \
  --source-dir "$AZOTH_P5_PRIVATE_ROOT/sources" \
  --benchmark-root benchmarks/operations-decision-support-v1 \
  --repo-root . \
  --open
```

The page shows one pair at a time and does not expose lane, selection, graph,
pair, or repeated-anchor metadata. It binds only to `127.0.0.1`; stopping the
process closes the reviewer.

For a sequential shell workflow over the same private packet, run:

```bash
uv run python scripts/review_benchmark_adjudication.py \
  --private-gold "$AZOTH_P5_PRIVATE_ROOT/gold/operations-decision-support-v1.json" \
  --source-dir "$AZOTH_P5_PRIVATE_ROOT/sources" \
  --benchmark-root benchmarks/operations-decision-support-v1 \
  --repo-root .
```

The command resumes at the first unanswered presentation. Enter comma-separated
evidence numbers for both papers, a label from `0` to `3`, a brief rationale,
and confirm before saving. Use `:help` at any prompt for navigation and editing
commands. Terminal and browser saves use the same atomic private writer.
