# Ouroboros Design

## Purpose

Ouroboros turns a Rubedo rejection into a Nigredo expansion path. When prior-art review rejects a hypothesis because the field has already mapped the claim, Azoth should preserve that result as a productive corpus seed: queue the key priors, safely download ingest-ready PDFs where possible, and leave the next `ingest -> exhaust -> connect -> detect` loop explicit.

The feature is not a novelty oracle and not an aggressive crawler. It is a bounded bridge from `rubedo/prior_art/<cluster_id>.yaml` to `nigredo/inbox/` and `nigredo/ouroboros/`.

## Command

```bash
azoth ouroboros <cluster_id>
```

Options:

```bash
--download / --no-download
--include-impact <impact>
--max-sources N
--json
--no-auto-checkpoint
```

Defaults:

- `--download` enabled.
- Include `direct_prior_art` and `related_prior_art`.
- `--max-sources 8`.
- Do not recursively fetch references.
- Do not run ingest automatically.

## Inputs

Primary input:

```text
rubedo/prior_art/<cluster_id>.yaml
```

Required shape:

- `artifact_type: rubedo_prior_art`
- `sources`: list of source objects with `title`, `url`, and optional `impact`
- rejection-like decision evidence, such as:
  - `decision: reject_novelty_claim`
  - `assessment.novelty_result: rejected`

If the prior-art artifact is missing or does not indicate rejected novelty, the command fails with command-level context.

## Outputs

Expansion plan:

```text
nigredo/ouroboros/<cluster_id>_expansion.yaml
```

Run report:

```text
nigredo/ouroboros/<cluster_id>_report.yaml
```

Downloaded PDFs:

```text
nigredo/inbox/<slug>_<source_id>.pdf
```

Each queue item records:

- `title`
- `url`
- `resolved_url`
- `impact`
- `status`: `downloaded`, `queued`, `manual_required`, or `failed`
- `target_path` when downloaded
- `reason`

## URL Resolution

Safe resolution rules:

- `https://arxiv.org/abs/<id>` becomes `https://arxiv.org/pdf/<id>.pdf`
- `https://arxiv.org/html/<id>` becomes `https://arxiv.org/pdf/<id>.pdf`
- direct `.pdf` URLs are downloaded as-is

Unresolved sources remain in the queue with `manual_required`. DOI pages, HTML proceedings pages, paywalled publishers, and ambiguous URLs are not fetched in the first version.

## Data Flow

```text
Rubedo rejected hypothesis
-> rubedo/prior_art/<cluster_id>.yaml
-> azoth ouroboros <cluster_id>
-> nigredo/ouroboros expansion plan and report
-> safe PDFs in nigredo/inbox
-> user runs azoth ingest nigredo/inbox/
```

Ouroboros does not mutate Rubedo hypotheses and does not write registry entries. Separatio/Ingest remains the owner of classification, file movement, Albedo records, embeddings, and registry state.

## Error Handling

The command fails when:

- prior-art artifact is missing
- prior-art artifact is malformed
- prior-art result is not rejection-like
- `max_sources` is below 1

The command does not fail the entire run when one source cannot be downloaded. It marks that item as `failed` or `manual_required` and writes the report.

Downloads use bounded timeouts and validate that the response has PDF-like content or a `.pdf` URL. Existing target files are not overwritten; filename collisions get a stable suffix.

## Testing

Add a focused regression script:

```text
scripts/check_ouroboros.py
```

It must cover:

- expansion queue creation from a rejected prior-art artifact
- safe arXiv URL resolution
- direct PDF URL handling
- manual-required status for unresolved URLs
- download path writing using a fake downloader, without network
- rejection gate: non-rejected prior art does not expand

Extend CLI smoke checks so `azoth ouroboros --help` is listed and works.

## Documentation

Update:

- `README.md`
- `USER_GUIDE.md`

Docs should show the loop:

```bash
azoth ouroboros <cluster_id>
azoth ingest nigredo/inbox/
azoth awaken ML --depth 3 --count 8
azoth connect --within ML --reanalyze-depth-upgrades
azoth detect --domain ML
```

## Non-Goals

- No recursive citation crawling.
- No automatic ingestion.
- No DOI scraping.
- No claim that downloaded priors are sufficient to prove novelty.
- No acceptance/rejection mutation; `azoth promote` remains the decision command.
