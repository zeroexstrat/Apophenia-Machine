# Troubleshooting & operational notes

## "Everything is unclassified" / junk titles like ORCID lines or addresses

The corpus was ingested **without an LLM** (heuristic fallback). Those records carry a
`fallback` tag and their `title`/`claims` are front-matter noise, so classification and
connection have nothing to work with. Fix by re-ingesting with an LLM attached:

```bash
python3 skills/azoth/scripts/preflight.py --project-root <repo>   # must be READY
azoth reclassify --scope unclassified                            # cheap: reuses stored records
# deeper fix — rebuild the records themselves:
azoth ingest <repo>/nigredo/unclassified --reprocess
```

`reclassify` is cheap but limited by whatever text is already stored; `--reprocess` ingest
is the real fix because it rebuilds the library record from the PDF with the LLM.

## Duplicates

Identical content (by hash) is not re-ingested; the file is moved to
`nigredo/duplicates/` and reported. Force a re-ingest with `azoth ingest … --reprocess`.

## Empty exhaustion / connections

Empty buckets usually mean a weak (fallback) library record. Inspect
`albedo/library/<id>.yaml`. Fix the record (LLM re-ingest), then re-exhaust and
`connect --reanalyze-depth-upgrades`.

## Gate checks (Vigil)

Every skill runs gate checks. On a scratch/experimental root set `AZOTH_SKIP_VIGIL=1`.
Gates are also skipped automatically when a root has no `athanasor/vigil/verify.py`.
A dirty git worktree can trip the drift gate — commit or stash pipeline artifacts.

## Cost expectations (rough, cloud model)

- Depth 3 on a ~20-page paper: ~$0.10–0.25
- Depth 5: ~$0.50–1.00 per paper
- Default slice: a few papers per `awaken`. Batch large libraries; re-exhausting the whole
  corpus at depth 4 is a long, real-cost run — confirm scope with the user first.

## Recovery

Slice commands checkpoint to `athanasor/lapis/memory.jsonl`. After an interruption,
`azoth status` shows true state; re-run the interrupted slice (idempotent — already-done
papers are skipped unless `--reprocess`).

## Common errors

| Symptom | Cause / fix |
|---------|-------------|
| `azoth: command not found` | Not installed: `pip install 'git+https://github.com/zeroexstrat/Apophenia-Machine@v0.2.0'` |
| Preflight exit 4 | LLM unreachable — start the backend / sign in / fix base_url, or `--allow-no-llm`. |
| `Hypothesis not found` on triage/review | Wrong `cluster_id`; list with `ls rubedo/hypotheses/`. |
| PDFs all skipped | No PDF extractor — `pip install pymupdf` or install poppler (`pdftotext`). |
| Connections always empty | Too few `exhausted` papers, or fallback-only records with no shared tags. |
