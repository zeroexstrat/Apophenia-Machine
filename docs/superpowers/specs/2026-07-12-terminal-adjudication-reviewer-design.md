# Terminal Adjudication Reviewer Design

## Goal

Provide Rafael a fast sequential terminal workflow for completing or editing the
70 blinded P5 adjudication presentations without editing JSON directly.

## Scope

The command is a second interface over `athanasor.benchmark.reviewer.ReviewSession`.
It reads the same private packet and source PDFs as the browser reviewer and
writes through the same validation and atomic persistence path. It does not
reimplement packet topology, evidence extraction, source verification, or save
logic. It never prints lane, selection, graph, pair, paper ID, or anchor metadata.

## Command

Create `scripts/review_benchmark_adjudication.py` with required arguments
`--private-gold`, `--source-dir`, `--benchmark-root`, and `--repo-root`.
The command opens `ReviewSession`, finds the first unanswered presentation, and
starts an interactive loop. If all presentations are answered, it shows the
completed count and asks whether to edit a numbered presentation or quit.

## Presentation Flow

For the current presentation, print:

- `Presentation N of 70 - M completed`;
- Paper A title and authors;
- every offered Paper A evidence sentence with a 1-based number;
- Paper B title, authors, and numbered evidence in the same form;
- any existing label, evidence selections, and rationale when editing.

Then prompt in this order:

1. Paper A evidence numbers, comma-separated;
2. Paper B evidence numbers, comma-separated;
3. label `0`, `1`, `2`, or `3`;
4. nonempty rationale;
5. confirmation: `Save this answer? [y/n]`.

On `y`, call `ReviewSession.save_answer` and move to the next unanswered
presentation. On `n`, return to the current presentation without changing the
packet. Evidence and rationale are never inferred or autofilled.

## Commands

At any prompt, accept commands prefixed by a colon:

- `:back` moves to the previous presentation without saving current input;
- `:skip` moves to the next presentation without saving;
- `:edit N` opens 1-based presentation N;
- `:progress` prints completed and remaining counts, then redraws the current
  presentation;
- `:quit` exits without changing unsaved input;
- `:help` prints the command list.

End-of-file and keyboard interruption behave like `:quit` and print a concise
message. Navigation never saves. A saved answer remains editable by `:edit N`.

## Parsing and Validation

Evidence input accepts whitespace and comma-separated positive integers, removes
duplicates while preserving order, and rejects empty, nonnumeric, zero, negative,
or out-of-range selections. The label parser rejects booleans, words, and values
outside `0-3`. Rationale is stripped and must remain nonempty. The terminal layer
maps selected numbers back to the exact evidence strings from the current visible
presentation and delegates authoritative validation to `ReviewSession`.

Malformed input prints one actionable error and repeats only that prompt. Any
`ReviewerError` during startup exits nonzero without a traceback. A save error
leaves the packet unchanged and returns to the answer summary.

## Components

- `TerminalReviewer`: owns current index, resume selection, presentation rendering,
  prompt sequencing, navigation commands, confirmation, and progress output.
- `parse_evidence_numbers`: pure parser from user text and evidence count to
  zero-based indexes.
- `parse_label`: pure parser from user text to integer label.
- `main`: parses paths, opens `ReviewSession`, runs the terminal loop, and maps
  startup errors or interrupts to deterministic exit codes.

Input and output streams are injectable so the whole interaction can be tested
without a real terminal.

## Verification

Unit tests cover parsing, first-unanswered resume, blinded rendering, successful
save, declined confirmation, navigation without writes, editing, progress, EOF,
interrupt, and invalid input recovery. A live smoke test opens the real packet,
prints Presentation 2, and quits without saving. Existing reviewer, freeze,
protocol, and public-boundary tests remain authoritative.
