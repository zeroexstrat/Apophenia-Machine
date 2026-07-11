# P3-T1 Wheel Resources and Workspace Initialization Design

**Task:** P3-T1 — Wheel resources and `azoth init`

**Authority:** `PROJECT_ROADMAP.md` remains canonical. This document resolves P3-T1 implementation details only.

## 1. Goal and acceptance boundary

Azoth must operate from a wheel installed outside the source repository on Python 3.10, 3.11, and 3.12. Immutable schemas, default configuration, and Vigil gate definitions ship inside the `athanasor` package. `azoth init <directory>` creates a usable empty runtime workspace without writing into `site-packages`.

P3-T1 does not rewrite Git history, update public branches or tags, build the benchmark, or change scientific and human-review semantics. Those responsibilities remain in later roadmap tasks.

## 2. Baseline failure

The current wheel contains Python modules but no root YAML resources. From a directory outside the clone:

- `azoth ingest` fails because it looks for `SCHEMA.yaml` at the environment's `site-packages` root.
- `azoth init` is not a registered command.
- `validate`, `migrate`, Vigil, and session helpers infer repository-root paths from `__file__`, so an installed package can read or write in `site-packages` or silently skip workspace gates.

An empty `azoth validate --all` can pass without exercising a schema, so it is not sufficient wheel evidence.

## 3. Resource architecture

Create `athanasor/resources/` as a Python package containing immutable copies of:

- `SCHEMA.yaml`
- `EXHAUST_SCHEMA.yaml`
- `RETRIEVAL_SCHEMA.yaml`
- `CONNECT_SCHEMA.yaml`
- `DETECT_SCHEMA.yaml`
- `azoth.config.yaml`
- `vigil/gates.yaml`

Declare these files as package data in `pyproject.toml`. Add one focused resource API that uses `importlib.resources.files()` to read packaged text and YAML. Callers must not infer resource locations with `Path(__file__).parents[...]` and must not mutate packaged resources.

The repository-root copies remain the authoring surfaces for this task. A synchronization test compares their bytes with the packaged copies so future schema edits cannot ship divergent contracts.

## 4. Workspace discovery

Resolve the active workspace in this order:

1. `AZOTH_PROJECT_ROOT`, when set.
2. The nearest ancestor of the current working directory containing `azoth.config.yaml`.
3. The current working directory.

`load_config(path=...)` continues to honor an explicit config path. The bundled config supplies defaults; a workspace `azoth.config.yaml` overrides them. The resolved `Config.project_root` and `paths.project_root` always identify the mutable workspace, never the installed package.

This preserves explicit automation, makes `cd workspace && azoth ...` work naturally, and prevents the wheel from treating `site-packages` as a project.

## 5. `azoth init` contract

Add:

```text
azoth init <directory>
```

The command:

- resolves and creates the target directory;
- copies the bundled default configuration to `azoth.config.yaml` with `paths.project_root` set to the absolute target path;
- creates the empty runtime directories required by pipeline commands;
- creates an empty `albedo/registry.jsonl`;
- creates a minimal generated `athanasor/lapis/state.json` suitable for Vigil close and status reporting;
- does not copy immutable schemas or gate definitions into the workspace;
- does not initialize Git, install dependencies, contact an LLM, or run ingestion;
- never writes into the Python environment or package directory.

The initial directory set is:

```text
nigredo/inbox
nigredo/{configured domains}
albedo/library
albedo/exhaust
citrinitas/retrieval_candidates
citrinitas/within_domain
citrinitas/cross_domain
citrinitas/reports
rubedo/hypotheses
rubedo/drafts
rubedo/reviews
rubedo/experiments
rubedo/promoted
rubedo/prior_art
rubedo/rejections
nigredo/ouroboros
athanasor/lapis
athanasor/vigil/reports
```

Initialization is conflict-safe:

- A missing or empty target is initialized.
- Re-running against a workspace previously initialized by Azoth is idempotent and restores missing empty directories without overwriting existing files.
- A non-empty target without an Azoth config is rejected.
- An existing invalid config, non-file config path, registry directory collision, or state directory collision is rejected with a precise error.
- No `--force` option is added in P3-T1.

Writes use temporary files followed by atomic replacement for the config, registry, and initial state. Validation occurs before filesystem mutation where possible. If a file write fails, the command reports the target and does not claim initialization succeeded.

## 6. Installed Vigil behavior

Vigil remains executable from the repository and becomes callable as an installed module. Its mutable paths derive from the active workspace; schema and gate definitions derive from packaged resources.

Pipeline skills invoke Vigil with the active interpreter as:

```text
python -m athanasor.vigil.verify <mode>
```

with `AZOTH_PROJECT_ROOT` set to the command's resolved workspace. A missing repository-local `athanasor/vigil/verify.py` is no longer a reason to skip gates in an initialized wheel workspace. `AZOTH_SKIP_VIGIL` remains the explicit opt-out used by existing tests and controlled workflows.

Vigil's Git drift gate treats a non-Git initialized workspace as a valid local workspace rather than a subprocess crash or dirty repository. Other structural gates operate on the workspace's runtime artifacts and packaged schemas.

## 7. Validate, migrate, and session boundaries

`validate` and `migrate` resolve artifact paths relative to the active workspace and schema definitions from package resources. The CLI launches installed helper modules with `python -m`, not by constructing repository-relative script paths.

Session commands also resolve mutable roots from the active workspace. `PROJECT_ROADMAP.md` remains repository-only project-control state; an initialized end-user workspace does not receive or require the portfolio roadmap. Incipere reports the roadmap as unavailable outside a development checkout without preventing ordinary pipeline commands.

## 8. Testing and verification

Use test-first implementation. Required coverage:

- Packaged resource API returns all seven immutable resources.
- Packaged resources are byte-identical to their repository authoring copies.
- Workspace discovery honors explicit environment override, nearest config ancestor, and current-directory fallback.
- `azoth init` creates the exact scaffold, sets the target root, and never writes outside the target.
- Repeated initialization is idempotent.
- Conflicting non-empty targets and path-type collisions fail without overwriting data.
- Installed Vigil uses workspace state and packaged contracts.
- Installed `ingest` processes a synthetic text document outside the clone, proving `SCHEMA.yaml` resolution with non-empty data.
- Installed `validate --all`, Vigil start/verify, and CLI help succeed outside the clone.
- Wheel contents explicitly include every resource.

Add a wheel smoke harness that builds once, installs into isolated Python 3.10, 3.11, and 3.12 environments, changes to a directory with no repository checkout on `sys.path`, initializes a workspace, ingests a synthetic text document, validates artifacts, and runs Vigil. CI runs the same supported-version matrix; local closeout records the exact interpreters available and obtains the missing managed interpreter through `uv` when needed.

P3 acceptance requires the focused tests, full suite, existing check scripts, public-tree and hardening audits, `git diff --check`, Vigil verify/close, wheel-content inspection, and all three installed-wheel smoke runs to pass. The canonical roadmap is updated only after those checks succeed.

## 9. Documentation

Update README and user guidance with the installed workflow:

```bash
python -m pip install azoth
azoth init research-workspace
cd research-workspace
azoth status
```

State explicitly that package resources are immutable implementation contracts while the initialized directory holds user-owned runtime data. Do not claim scientific validation, autonomous discovery, or PyPI availability unless separately verified.
