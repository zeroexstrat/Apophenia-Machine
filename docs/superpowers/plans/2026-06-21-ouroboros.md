# Ouroboros Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `azoth ouroboros <cluster_id>` so a rejected Rubedo prior-art result becomes a bounded Nigredo expansion queue with safe PDF downloads.

**Architecture:** Add one focused skill module, `athanasor/skills/ouroboros.py`, that reads `rubedo/prior_art/<cluster_id>.yaml`, resolves safe source URLs, writes expansion/report YAML under `nigredo/ouroboros/`, and optionally downloads PDFs into `nigredo/inbox/`. Wire it into `athanasor/cli.py` and existing smoke/docs surfaces without mutating Rubedo hypotheses or registry entries.

**Tech Stack:** Python standard library (`urllib.request`, `urllib.parse`, `hashlib`, `pathlib`), PyYAML via existing `write_yaml`, Click CLI.

## Global Constraints

- Default command is `azoth ouroboros <cluster_id>`.
- Default `--download` is enabled.
- Default impacts are `direct_prior_art` and `related_prior_art`.
- Default `--max-sources` is `8`.
- Do not recursively fetch references.
- Do not run ingest automatically.
- Do not mutate Rubedo hypotheses or registry entries.
- Only arXiv abs/html URLs and direct `.pdf` URLs are safe-downloadable in the first version.
- Unknown URLs must become `manual_required`, not failed command runs.

---

## File Structure

- Create `athanasor/skills/ouroboros.py`: core expansion, URL resolution, safe download, output artifact writing.
- Modify `athanasor/skills/__init__.py`: export `ouroboros`.
- Modify `athanasor/cli.py`: add `azoth ouroboros` command and checkpoint wiring.
- Create `scripts/check_ouroboros.py`: direct regression tests using a fake downloader and temp project root.
- Modify `scripts/check_cli.py`: include `ouroboros` help smoke.
- Modify `README.md` and `USER_GUIDE.md`: document the rejection-to-expansion loop.

---

### Task 1: Add Failing Ouroboros Regression

**Files:**
- Create: `scripts/check_ouroboros.py`

**Interfaces:**
- Consumes: planned `run_ouroboros(cluster_id, config, download, include_impacts, max_sources, downloader) -> pathlib.Path`
- Produces: failing tests that define expansion-plan behavior before implementation.

- [ ] **Step 1: Write the failing test script**

```python
from athanasor.skills.ouroboros import run_ouroboros, resolve_source_url

def fake_downloader(url, target_path, timeout=30):
    target_path.write_bytes(b"%PDF-1.4\nfixture\n")
    return {"ok": True, "bytes": target_path.stat().st_size}

assert resolve_source_url("https://arxiv.org/abs/2604.12946v1") == "https://arxiv.org/pdf/2604.12946v1.pdf"
path = run_ouroboros(cluster_id, config=cfg, download=True, downloader=fake_downloader)
payload = yaml.safe_load(path.read_text())
assert payload["artifact_type"] == "nigredo_ouroboros_expansion"
assert any(item["status"] == "downloaded" for item in payload["items"])
assert any(item["status"] == "manual_required" for item in payload["items"])
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python3 scripts/check_ouroboros.py
```

Expected: fails with `ModuleNotFoundError: No module named 'athanasor.skills.ouroboros'`.

---

### Task 2: Implement Ouroboros Skill

**Files:**
- Create: `athanasor/skills/ouroboros.py`
- Modify: `athanasor/skills/__init__.py`

**Interfaces:**
- Produces:
  - `resolve_source_url(url: str) -> str | None`
  - `run_ouroboros(cluster_id: str, *, config: Config | None = None, download: bool = True, include_impacts: list[str] | None = None, max_sources: int = 8, downloader: Callable[..., dict[str, Any]] | None = None) -> Path`

- [ ] **Step 1: Implement minimal code**

Required behavior:

```python
DEFAULT_IMPACTS = ["direct_prior_art", "related_prior_art"]

def resolve_source_url(url: str) -> str | None:
    if "arxiv.org/abs/" in url:
        return "https://arxiv.org/pdf/<id>.pdf"
    if "arxiv.org/html/" in url:
        return "https://arxiv.org/pdf/<id>.pdf"
    if url.lower().split("?")[0].endswith(".pdf"):
        return url
    return None
```

`run_ouroboros` must:

- load `rubedo/prior_art/<cluster_id>.yaml`
- require rejected novelty
- filter sources by impact and `max_sources`
- write `nigredo/ouroboros/<cluster_id>_expansion.yaml`
- write `nigredo/ouroboros/<cluster_id>_report.yaml`
- download safe URLs when `download=True`
- generate stable target filenames with `slugify(title)` and a short source hash
- leave unresolved sources as `manual_required`
- return the expansion path

- [ ] **Step 2: Run focused test**

Run:

```bash
python3 scripts/check_ouroboros.py
```

Expected: all Ouroboros checks pass.

---

### Task 3: Wire CLI and Docs

**Files:**
- Modify: `athanasor/cli.py`
- Modify: `scripts/check_cli.py`
- Modify: `README.md`
- Modify: `USER_GUIDE.md`

**Interfaces:**
- Consumes: `ouroboros_skill.run_ouroboros(...)`
- Produces: `azoth ouroboros <cluster_id>` with:
  - `--download/--no-download`
  - `--include-impact`
  - `--max-sources`
  - `--json`
  - `--no-auto-checkpoint`

- [ ] **Step 1: Add CLI command**

Add import:

```python
from .skills import ouroboros as ouroboros_skill
```

Add Click command:

```python
@main.command("ouroboros")
@click.argument("cluster_id")
@click.option("--download/--no-download", default=True)
@click.option("--include-impact", multiple=True)
@click.option("--max-sources", default=8, type=click.IntRange(min=1))
@click.option("--json", "json_output", is_flag=True)
@click.option("--no-auto-checkpoint", is_flag=True)
def cmd_ouroboros(...):
    ...
```

- [ ] **Step 2: Extend CLI smoke**

Add `ouroboros` to the command lists in `scripts/check_cli.py`.

- [ ] **Step 3: Update docs**

Add the loop:

```bash
azoth ouroboros <cluster_id>
azoth ingest nigredo/inbox/
azoth awaken ML --depth 3 --count 8
azoth connect --within ML --reanalyze-depth-upgrades
azoth detect --domain ML
```

- [ ] **Step 4: Run tests**

Run:

```bash
python3 scripts/check_ouroboros.py
python3 scripts/check_cli.py
```

Expected: both pass.

---

### Task 4: Verify and Commit

**Files:**
- All files from Tasks 1-3.

**Interfaces:**
- Consumes: implemented command and tests.
- Produces: committed Ouroboros product feature.

- [ ] **Step 1: Run full verification**

Run:

```bash
python3 -m compileall athanasor scripts
python3 scripts/check_ouroboros.py
python3 scripts/check_cli.py
python3 scripts/check_rubedo_review_path.py
python3 scripts/check_pipeline_smoke.py
python3 scripts/hardening_audit.py
git diff --check
python3 athanasor/vigil/verify.py verify
```

Expected: every command exits 0.

- [ ] **Step 2: Run real dry expansion**

Run:

```bash
python3 -m athanasor.cli ouroboros cluster_loopedworldmodels_903887879_paper_397502697_3 --no-download
```

Expected: writes expansion/report YAML and does not place PDFs into `nigredo/inbox/`.

- [ ] **Step 3: Commit**

Run:

```bash
git add README.md USER_GUIDE.md athanasor/cli.py athanasor/skills/__init__.py athanasor/skills/ouroboros.py scripts/check_cli.py scripts/check_ouroboros.py docs/superpowers/plans/2026-06-21-ouroboros.md
git commit -m "Add Ouroboros prior-art expansion"
```

Expected: commit succeeds with a clean tracked worktree, apart from intentionally ignored runtime artifacts if the real command was run.
