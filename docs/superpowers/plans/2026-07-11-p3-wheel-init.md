# P3-T1 Wheel Resources and Workspace Initialization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Azoth's immutable YAML contracts inside the wheel and add a conflict-safe `azoth init <directory>` that creates a usable runtime workspace outside the source repository.

**Architecture:** `athanasor.resources` owns immutable package data and resource access. Configuration discovers a mutable workspace independently from the installed package. Pipeline, validation, migration, and Vigil code consume package resources while writing only beneath the resolved workspace. A real-wheel smoke harness proves the boundary on Python 3.10-3.12.

**Tech Stack:** Python 3.10 standard library (`importlib.resources`, `pathlib`, `tempfile`, `subprocess`, `venv`), PyYAML, Click, setuptools, pytest, uv for multi-interpreter smoke verification.

## Global Constraints

- `PROJECT_ROADMAP.md` remains canonical.
- Immutable schemas, default configuration, and Vigil definitions ship in `athanasor/resources/`.
- Runtime state is written only beneath the initialized workspace.
- Workspace resolution order is `AZOTH_PROJECT_ROOT`, nearest ancestor config, current working directory.
- `azoth init` is idempotent only for an existing Azoth workspace and never overwrites conflicts.
- No `--force`, Git initialization, dependency installation, network access, LLM call, or ingestion during initialization.
- Python 3.10, 3.11, and 3.12 wheel-installed operation is required.
- P4 history rewriting and all later roadmap work remain out of scope.

---

## File Structure

- Create `athanasor/resources/__init__.py`: resource identifiers and text/YAML access.
- Create `athanasor/resources/*.yaml` and `athanasor/resources/vigil/gates.yaml`: immutable package copies.
- Create `athanasor/workspace.py`: discovery and initialization with atomic seed files.
- Modify `athanasor/config.py`: bundled defaults plus workspace-root semantics.
- Modify schema consumers in `athanasor/skills/`, `athanasor/scripts/`, and `athanasor/vigil/verify.py`.
- Modify `athanasor/cli.py`: `init` command and module-based helper launching.
- Modify `pyproject.toml`: package data.
- Create `tests/test_resources.py`, `tests/test_workspace.py`, and `tests/test_wheel_install.py`.
- Create `scripts/check_wheel_install.py`: Python 3.10-3.12 installed-wheel smoke harness.
- Modify README, USER_GUIDE, CLI checks, CI, and canonical roadmap at their appropriate gates.

---

### Task 1: Package immutable resources

**Files:**
- Create: `tests/test_resources.py`
- Create: `athanasor/resources/__init__.py`
- Create: `athanasor/resources/SCHEMA.yaml`
- Create: `athanasor/resources/EXHAUST_SCHEMA.yaml`
- Create: `athanasor/resources/RETRIEVAL_SCHEMA.yaml`
- Create: `athanasor/resources/CONNECT_SCHEMA.yaml`
- Create: `athanasor/resources/DETECT_SCHEMA.yaml`
- Create: `athanasor/resources/azoth.config.yaml`
- Create: `athanasor/resources/vigil/gates.yaml`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `resource_text(name: str) -> str`
- Produces: `resource_yaml(name: str) -> Any`
- Produces: `resource_path(name: str) -> AbstractContextManager[Path]`
- Produces: `RESOURCE_NAMES: tuple[str, ...]`

- [ ] **Step 1: Write failing resource tests**

Test that every declared name loads, parses as a YAML mapping, matches the repository authoring copy byte-for-byte, rejects traversal/unknown names, and appears in a built wheel archive.

- [ ] **Step 2: Verify RED**

Run: `python3 -m pytest tests/test_resources.py -q`

Expected: collection fails because `athanasor.resources` does not exist.

- [ ] **Step 3: Add package resources and accessors**

Use a fixed allowlist mapping to `importlib.resources.files("athanasor.resources")`. Implement `resource_path` with `importlib.resources.as_file()` so callers needing a filesystem path remain zip-safe. Copy authoring YAML bytes without semantic rewriting.

- [ ] **Step 4: Declare package data**

Add setuptools package-data patterns for `*.yaml` and `vigil/*.yaml`.

- [ ] **Step 5: Verify GREEN and commit**

Run:

```bash
python3 -m pytest tests/test_resources.py -q
git diff --check
git add athanasor/resources pyproject.toml tests/test_resources.py
git commit -m "feat: package immutable Azoth resources"
```

Expected: resource tests pass and the commit contains only Task 1 files.

---

### Task 2: Discover and initialize mutable workspaces

**Files:**
- Create: `tests/test_workspace.py`
- Create: `athanasor/workspace.py`
- Modify: `athanasor/config.py`
- Modify: `athanasor/cli.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_cli_errors.py`

**Interfaces:**
- Produces: `discover_workspace(start: Path | None = None) -> Path`
- Produces: `initialize_workspace(target: Path) -> Path`
- Produces: `WorkspaceConflictError(RuntimeError)`
- CLI: `azoth init DIRECTORY`

- [ ] **Step 1: Write failing discovery and init tests**

Cover environment override, nearest ancestor config, CWD fallback, exact scaffold, absolute configured root, empty registry, valid initial state, no writes outside target, idempotent rerun, non-Azoth non-empty rejection, invalid YAML rejection, config-directory collision, registry-directory collision, and state-directory collision.

- [ ] **Step 2: Verify RED**

Run: `python3 -m pytest tests/test_workspace.py tests/test_config.py tests/test_cli_errors.py -q`

Expected: failures for missing workspace module and `init` command.

- [ ] **Step 3: Implement discovery and atomic initialization**

Use `Path.cwd()` only at call time. Validate the target before creating seed files. Write config, registry, and state through same-directory temporary files plus `os.replace`. The initial state must contain project/version metadata, zero pipeline/triage/session counts, and unchecked gate state. Existing valid Azoth config permits idempotent directory restoration without rewriting files.

- [ ] **Step 4: Make config resource-backed**

Load bundled `azoth.config.yaml` as the default mapping, then merge workspace config and environment overrides. Ensure both `Config.project_root` and `paths.project_root` equal the discovered workspace.

- [ ] **Step 5: Register CLI and verify GREEN**

Map `WorkspaceConflictError` to a clean Click error and print the initialized absolute path.

Run:

```bash
python3 -m pytest tests/test_workspace.py tests/test_config.py tests/test_cli_errors.py -q
python3 scripts/check_cli.py
git diff --check
git add athanasor/workspace.py athanasor/config.py athanasor/cli.py tests/test_workspace.py tests/test_config.py tests/test_cli_errors.py scripts/check_cli.py
git commit -m "feat: initialize isolated Azoth workspaces"
```

Expected: focused tests and CLI smoke pass.

---

### Task 3: Route schemas and helper commands through package resources

**Files:**
- Create: `tests/test_installed_boundaries.py`
- Modify: `athanasor/skills/ingest.py`
- Modify: `athanasor/skills/exhaust.py`
- Modify: `athanasor/skills/connect.py`
- Modify: `athanasor/skills/detect.py`
- Modify: `athanasor/scripts/validate.py`
- Modify: `athanasor/scripts/migrate.py`
- Modify: `athanasor/cli.py`

**Interfaces:**
- Schema loaders consume `resource_yaml()` or `resource_path()`.
- Helper CLI runs `python -m athanasor.scripts.validate` and `python -m athanasor.scripts.migrate` with `AZOTH_PROJECT_ROOT` inherited.

- [ ] **Step 1: Write failing installed-boundary tests**

Monkeypatch module `__file__` assumptions out of reach and prove ingest, exhaust, connect, detect, validate, and migrate resolve schemas without root YAML files. Assert validate/migrate inspect the workspace, not package directories.

- [ ] **Step 2: Verify RED**

Run: `python3 -m pytest tests/test_installed_boundaries.py -q`

Expected: missing root-resource failures.

- [ ] **Step 3: Replace root path constants**

Use resource accessors for all five schemas. Give validate/migrate a runtime workspace root from `discover_workspace()` while preserving explicit input paths.

- [ ] **Step 4: Launch helpers as modules**

Replace `_run_python_module(Path, argv)` with `_run_python_module(module_name: str, argv: list[str], root: Path)` and invoke `[sys.executable, "-m", module_name, *argv]` from the active workspace.

- [ ] **Step 5: Verify GREEN and commit**

Run:

```bash
python3 -m pytest tests/test_installed_boundaries.py tests/test_ingest.py tests/test_exhaust.py tests/test_connect_from_file.py tests/test_connect_retrieval.py tests/test_detect_from_file.py -q
python3 scripts/check_pipeline_smoke.py
git diff --check
git add athanasor/skills athanasor/scripts athanasor/cli.py tests/test_installed_boundaries.py
git commit -m "fix: resolve pipeline contracts from package resources"
```

Expected: focused pipeline and installed-boundary tests pass.

---

### Task 4: Make Vigil wheel-safe and workspace-bound

**Files:**
- Modify: `tests/test_vigil_gates.py`
- Create: `tests/test_vigil_workspace.py`
- Modify: `athanasor/vigil/verify.py`
- Modify: `athanasor/skills/common.py`
- Modify: `athanasor/skills/rubedo_common.py`
- Modify: `athanasor/session/commands.py`

**Interfaces:**
- Produces: `configure_workspace(root: Path) -> None` or equivalent path derivation at import/CLI entry.
- Pipeline Vigil launch: `[sys.executable, "-m", "athanasor.vigil.verify", phase]` with `AZOTH_PROJECT_ROOT` set.

- [ ] **Step 1: Write failing Vigil workspace tests**

Cover an initialized non-Git workspace, workspace report/state locations, packaged gates and schemas, module execution, pipeline invocation without a repository-local verifier, explicit `AZOTH_SKIP_VIGIL`, and preservation of direct gate-function tests with an explicit root.

- [ ] **Step 2: Verify RED**

Run: `python3 -m pytest tests/test_vigil_gates.py tests/test_vigil_workspace.py -q`

Expected: failures show Vigil still binds to the installed/source package root.

- [ ] **Step 3: Refactor Vigil paths**

Derive mutable paths from the active workspace. Read schema and gate contracts from package resources. Treat Git exit 128 outside a repository as a valid non-Git workspace with no drift; retain strict status parsing inside repositories.

- [ ] **Step 4: Replace file-script launchers**

Run Vigil as a module from skills and session close with an explicit workspace environment. Do not silently skip merely because `<workspace>/athanasor/vigil/verify.py` is absent.

- [ ] **Step 5: Verify GREEN and commit**

Run:

```bash
python3 -m pytest tests/test_vigil_gates.py tests/test_vigil_workspace.py tests/test_session_commands.py -q
python3 scripts/check_human_gate_contract.py
python3 athanasor/vigil/verify.py verify
git diff --check
git add athanasor/vigil/verify.py athanasor/skills/common.py athanasor/skills/rubedo_common.py athanasor/session/commands.py tests/test_vigil_gates.py tests/test_vigil_workspace.py
git commit -m "fix: bind installed Vigil to runtime workspaces"
```

Expected: Vigil tests and repository Vigil pass.

---

### Task 5: Prove installed-wheel operation on Python 3.10-3.12

**Files:**
- Create: `tests/test_wheel_install.py`
- Create: `scripts/check_wheel_install.py`
- Modify: `.github/workflows/hardening.yml`

**Interfaces:**
- Script options: `--wheel PATH`, repeatable `--python VERSION`, optional `--keep-temp`.
- Each interpreter creates an isolated environment and runs init, status, synthetic text ingest, validate, and Vigil outside the clone.

- [ ] **Step 1: Write failing harness tests**

Test command construction, environment isolation, wheel resource inspection, failure reporting, and successful fake-run aggregation without invoking network installers in unit tests.

- [ ] **Step 2: Verify RED**

Run: `python3 -m pytest tests/test_wheel_install.py -q`

Expected: missing harness import or command failures.

- [ ] **Step 3: Implement harness and CI matrix**

Build the wheel once. For each selected interpreter, create a venv outside the clone, install the wheel, initialize a new workspace, ingest a synthetic `.txt`, validate all, run `python -m athanasor.vigil.verify start` and `verify`, and assert `sys.path` has no repository path. CI must run installed-wheel smoke for its matrix Python version.

- [ ] **Step 4: Verify all supported versions**

Run:

```bash
rm -rf /tmp/azoth-p3-dist
uv build --wheel --out-dir /tmp/azoth-p3-dist
python3 scripts/check_wheel_install.py --wheel /tmp/azoth-p3-dist/azoth-*.whl --python 3.10 --python 3.11 --python 3.12
python3 -m pytest tests/test_wheel_install.py -q
git diff --check
```

Expected: all three versions report PASS from outside the clone.

- [ ] **Step 5: Commit**

```bash
git add scripts/check_wheel_install.py tests/test_wheel_install.py .github/workflows/hardening.yml
git commit -m "test: verify installed wheels across supported Python"
```

---

### Task 6: Documentation, full verification, and roadmap closeout

**Files:**
- Modify: `README.md`
- Modify: `USER_GUIDE.md`
- Modify: `PROJECT_ROADMAP.md` only after every acceptance command passes.

**Interfaces:**
- Documents the `pip install` -> `azoth init` -> `cd` -> `azoth status` flow.
- Records P3 evidence and sets exactly one next task, P4-T1.

- [ ] **Step 1: Update user documentation**

Explain immutable package resources versus mutable workspace data. Do not claim PyPI publication.

- [ ] **Step 2: Run complete verification**

Run:

```bash
python3 -m compileall athanasor scripts tests
python3 -m pytest -q
for check in scripts/check_*.py; do python3 "$check"; done
python3 scripts/hardening_audit.py
python3 scripts/check_public_tree.py
git diff --check
python3 athanasor/vigil/verify.py verify
rm -rf /tmp/azoth-p3-dist
uv build --wheel --out-dir /tmp/azoth-p3-dist
python3 scripts/check_wheel_install.py --wheel /tmp/azoth-p3-dist/azoth-*.whl --python 3.10 --python 3.11 --python 3.12
```

Expected: every command exits 0; all wheel resources are present; all interpreter smoke runs pass.

- [ ] **Step 3: Commit implementation documentation**

```bash
git add README.md USER_GUIDE.md docs/superpowers/plans/2026-07-11-p3-wheel-init.md
git commit -m "docs: explain installed Azoth workspaces"
```

- [ ] **Step 4: Close runtime state and prove clean tracked status**

Run:

```bash
python3 scripts/concludere.py --no-commit -f "P3-T1 wheel installation and workspace initialization verified"
python3 athanasor/vigil/verify.py close
git status --short
```

Expected: ignored recovery/runtime files may update; tracked worktree is clean before roadmap editing.

- [ ] **Step 5: Update and commit canonical roadmap**

Append P3 verification evidence, replace the active-session table with P3 facts, mark P3-T1 completed only after the full checks above, and set exactly one next task: `P4-T1 — Clean public Git lineage`. Then run:

```bash
git diff --check
git add PROJECT_ROADMAP.md
git commit -m "docs: close P3 wheel initialization"
git status --short --branch
```

Expected: roadmap closeout commit succeeds and tracked worktree is clean.
