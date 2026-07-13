# Local Adjudication Reviewer Design

## Goal

Provide Rafael a fast, private browser interface for completing all 70 blinded
P5 adjudication presentations without editing JSON directly.

## Scope

The reviewer runs only on `127.0.0.1`, reads the existing private packet and
source PDFs, and writes completed answers back to the same private packet. It
does not expose lane, selection, graph, pair, or anchor metadata; call external
services; alter the public freeze; reconcile gold; or commit private content.

## Architecture

`athanasor.benchmark.reviewer` owns evidence extraction, visible presentation
construction, answer validation, and atomic persistence. A standalone
`scripts/serve_benchmark_adjudication.py` entry point owns the loopback HTTP
server and an embedded single-page interface. The implementation uses only the
Python standard library, the existing benchmark modules, and the installed
`pdftotext` executable.

The server receives explicit `--private-gold`, `--source-dir`, `--benchmark-root`,
and `--repo-root` paths. Both private inputs must resolve outside the repository.
It binds to `127.0.0.1` on a caller-selected or ephemeral port and generates a
high-entropy session token that is required by every route.

## Review Screen

The page shows exactly one randomized presentation at a time:

- progress as `N / 70` and completed count;
- paper title and authors, but no internal IDs or hidden metadata;
- source-derived abstract or introduction sentences as checkboxes;
- four large radio-style label choices containing the frozen rubric text;
- a required rationale text area;
- Back, Save, and Save & Next controls;
- a visible saved/error state.

At least one evidence sentence from each paper is required. Previously saved
answers reload exactly and remain editable. Navigation alone never saves.

## Evidence Extraction

At startup the reviewer runs `pdftotext` in reading order on pages 1-2 of each
manifest-bound PDF. If neither an abstract nor an introduction is visible, it
extends extraction through page 4 so cover-heavy working papers expose their
substantive opening text. It normalizes whitespace, prefers text between an
`ABSTRACT` marker and the introduction/keywords boundary, splits the result into
nontrivial sentences, and falls back to the first useful prose sentences when no
abstract marker is available. Every submitted evidence span must exactly equal a
sentence offered for that paper; arbitrary or cross-paper evidence is rejected.

## Save Flow

The browser submits presentation ID, integer label, rationale, and checked
evidence spans. The backend verifies that the presentation is part of the
authoritative packet, label is 0-3, rationale is nonempty, both paper roles are
represented, and evidence belongs to the displayed candidates. It updates only
the answer fields and calls the existing `atomic_write_private`, preserving
mode `0600`, parent mode `0700`, hidden topology, and all other answers.

## Safety and Errors

- Refuse startup if either private path is inside or equal to the repository.
- Refuse source files whose bytes do not match the public source manifest.
- Require the random token on page and API routes.
- Send `Cache-Control: no-store`, a restrictive Content Security Policy, and no
  permissive CORS headers.
- Return structured validation errors without tracebacks or private paths.
- Never overwrite an answer through navigation; edits require an explicit save.

## Verification

Unit tests cover evidence normalization, visible-field boundaries, validation,
atomic save and edit behavior, preservation of hidden metadata, and rejection
of unsafe paths or unoffered evidence. Subprocess tests cover loopback binding,
token enforcement, page/API behavior, and successful save-and-reload. Existing
freeze, protocol, and public-tree tests remain authoritative.
