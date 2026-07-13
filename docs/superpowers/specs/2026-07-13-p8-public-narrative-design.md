# P8 Public Narrative and Rejection Case Design

**Task:** P8-T1 — Public README and rejection/reframe case study

**Status:** Approved for implementation

**Goal:** Make Azoth's public engineering evidence understandable in five minutes without expanding any benchmark, scientific-validity, novelty, or model-identity claim beyond the committed P7 evidence.

## Scope

P8 changes the public documentation surface only where the roadmap requires it:

- reorganize the root `README.md` around one runnable five-minute workflow;
- publish a compact, denominator-bearing P7 results table sourced from the committed aggregate result;
- add a public looped-transformer case study that records candidate, primary-source prior-art rejection, and a comparison/replication reframe;
- add one newly authored fictional text input for the five-minute workflow;
- add an executable documentation audit and tests so public claims cannot silently drift from the committed result or lose their scope limitations;
- update `PROJECT_ROADMAP.md` only after implementation verification.

P8 does not change benchmark inputs, gold labels, prompts, metrics, thresholds, scores, package version, release metadata, website content, or runtime research semantics. Those remain P7 evidence or P9 work.

## Public information architecture

The root README will use this order:

1. Product position and the human authority boundary.
2. **Five-minute demo** using a clone, editable install, `azoth init`, a fictional text record, no-LLM ingestion, status, and Vigil verification.
3. **What the demo proves** and what it does not prove.
4. **Measured evaluation** with a selected P7 model table containing value, numerator/denominator, uncertainty, and threshold outcome.
5. **Architecture** and artifact flow.
6. **Engineering decisions**: package-resident contracts, mutable workspace separation, deterministic retrieval versus substantive assessment, atomic imports, persistent rejection fingerprints, and fail-closed benchmark isolation.
7. **Rejection case** summary linked to the full case-study document.
8. Installation, operating workflow, Vigil gates, verification, limitations, and license.

The README will remain a product entry point rather than duplicating every P7 metric or every prior-art detail. The existing aggregate results page remains the complete 91-record benchmark report.

## Five-minute demo

Create `examples/five-minute-demo/queueing-note.txt` as a newly authored fictional operations-research note. The README will run only public, local paths:

```bash
git clone https://github.com/zeroexstrat/Apophenia-Machine.git
cd Apophenia-Machine
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
azoth init .demo-workspace
cp examples/five-minute-demo/queueing-note.txt .demo-workspace/nigredo/inbox/
cd .demo-workspace
azoth ingest nigredo/inbox/queueing-note.txt --domain-override operations_research --no-llm
azoth status
python -m athanasor.vigil.verify verify
```

The demo proves workspace initialization, text ingestion, schema-validated fallback extraction, registry persistence, status reporting, and structural-gate execution. It does not demonstrate model generation, pair-ranking quality, substantive connection validity, novelty, or benchmark performance.

## Measured table contract

The README will select the model run's most decision-relevant P7 metrics from `benchmarks/operations-decision-support-v1/results/aggregate.json`:

- macro-F1;
- claim precision;
- reference recall;
- candidate recall;
- workload reduction;
- precision@5;
- nDCG@10;
- evidence support;
- supported items;
- useful items;
- redundancy;
- unsafe OOD assignment and unsupported-derived items as explicitly undefined zero-denominator populations.

Every row will carry the exact value, numerator, denominator, uncertainty, and threshold result from the aggregate. The table introduction will say that it covers one frozen 12-paper, 66-pair suite. The adjacent limitation will state that provider model identity was not exposed or independently verified and that the suite does not establish external validity, scientific validity, or novelty.

## Rejection/reframe case

Create `docs/case-studies/looped-transformer-prior-art.md`. It will be a sanitized public narrative, not a copied runtime artifact and not a new research finding.

The document will show four states without contradiction:

1. **Candidate:** a generated gap proposed that spectral constraints used for stable iterative dynamics had not been applied to looped transformers.
2. **Review requirement:** the candidate remained `pending_review`; its novelty checklist explicitly required an external prior-art search.
3. **Human decision:** primary sources directly contradicted the novelty premise, so the novelty claim was rejected and its rejection fingerprint was retained.
4. **Valid reframe:** compare or replicate stability mechanisms on one controlled looped-transformer backbone; do not claim the comparison was run or that the reframe is novel.

The strongest direct sources are:

- Parcae, which constrains a stable looped architecture through a spectral parameterization: `https://arxiv.org/html/2604.12946v1`;
- STARS, which applies Jacobian spectral-radius regularization to looped language models: `https://arxiv.org/html/2605.26733v1`;
- CART, which reports a learned LTI recurrence gate with spectral radius below one: `https://arxiv.org/abs/2606.01495`.

Supporting context may cite residual scaling for weight-tied transformers, enforced Lipschitz transformer training, and the PMLR self-attention Lipschitz analysis. These sources support the rejection or comparison design; they do not prove literature-wide completeness.

The reframe will compare Parcae-style spectral parameterization, STARS-style Jacobian regularization, CART-style learned LTI gating, and loop-aware residual scaling. The smallest proposed experiment holds backbone, data, parameter count, optimizer, token budget, loop depths, and seeds constant, then measures divergence events, hidden-state or Jacobian growth, validation loss, task quality, and compute-normalized performance. It is a proposed replication/comparison protocol only.

## Executable public-claim audit

Add `scripts/check_public_narrative.py` with a small importable API and CLI. It will:

- load the committed aggregate JSON and locate `model_5_6_sol`;
- verify each selected README metric's rendered value, numerator/denominator, uncertainty, and threshold label against the aggregate;
- require the five-minute-demo heading to precede architecture and installation detail;
- require the README and case study to preserve the 12-paper/66-pair boundary, provider-identity limitation, human validity/novelty boundary, rejected decision, and comparison/replication wording;
- require the three direct primary-source URLs;
- reject phrases that claim the case was discovered, proven, confirmed, novel, or experimentally validated;
- fail with field-addressed diagnostics and a nonzero exit code.

`tests/test_public_narrative.py` will test the live documents and mutation cases for metric drift, missing scope, contradictory case state, missing source provenance, and unsupported completion language. The implementation will follow red-green TDD.

## Verification

P8 acceptance requires fresh evidence for all of the following:

1. The public narrative test fails before the documents/auditor exist or satisfy the contract, then passes after implementation.
2. The README demo runs successfully in a fresh temporary clone or copied tracked tree and produces one exhausted or ingested registry entry plus a green Vigil verification without network or model access.
3. The narrative audit passes against the committed aggregate.
4. The full test suite, every maintained `scripts/check_*.py` check, public-tree audit, hardening audit, compileall, and `git diff --check` pass.
5. Vigil `verify` and `close` pass on the final tracked state.
6. `PROJECT_ROADMAP.md` records P8 completion evidence and exactly one next task, P9-T1.

## Risks and controls

- **Metric cherry-picking:** publish misses and undefined populations alongside strengths; link the complete aggregate report.
- **Scientific overclaim:** keep schema/evidence support separate from truth, usefulness, novelty, and external validity.
- **Model provenance overclaim:** describe `5.6 Sol` only as the frozen backend label and state that provider identity is unverified.
- **Pilot-data leakage:** author the public prose from the reviewed state transition and primary sources; do not copy private IDs, filenames, source bytes, rationales, or runtime artifacts.
- **Demo drift:** run the exact README commands in isolation and bind required headings/claims in the audit.
- **Prior-art completeness:** call the search sufficient to reject the specific premise, not an exhaustive novelty search.

## Acceptance summary

P8 is complete only when a new reader can run one local workflow, see exact bounded P7 evidence including misses, follow one honest rejection-to-reframe trace, and encounter no public statement that exceeds the committed artifacts or human-review boundary.
