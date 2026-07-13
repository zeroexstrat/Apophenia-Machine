#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from athanasor.benchmark.protocol import BenchmarkProtocolError
from athanasor.benchmark.reviewer import ReviewSession, ReviewerError


class TerminalInputError(ValueError):
    """Terminal input does not satisfy the adjudication contract."""


def parse_evidence_numbers(value: str, count: int) -> list[int]:
    parts = value.split(",")
    if not parts or any(not part.strip().isdigit() for part in parts):
        raise TerminalInputError(
            "enter one or more comma-separated evidence numbers"
        )
    selected = [int(part.strip()) for part in parts]
    if any(number < 1 or number > count for number in selected):
        raise TerminalInputError(
            f"evidence numbers must be between 1 and {count}"
        )
    return list(dict.fromkeys(number - 1 for number in selected))


def parse_label(value: str) -> int:
    if value not in {"0", "1", "2", "3"}:
        raise TerminalInputError("label must be 0, 1, 2, or 3")
    return int(value)


@dataclass(frozen=True)
class _Navigation(Exception):
    action: str
    index: int | None = None


class TerminalReviewer:
    def __init__(
        self,
        session: ReviewSession,
        *,
        input_stream: TextIO,
        output_stream: TextIO,
    ) -> None:
        self.session = session
        self.input = input_stream
        self.output = output_stream

    def _write(self, value: str = "") -> None:
        self.output.write(value + "\n")
        self.output.flush()

    def _read(self, prompt: str) -> str:
        while True:
            self.output.write(prompt)
            self.output.flush()
            raw = self.input.readline()
            if raw == "":
                raise EOFError
            value = raw.strip()
            if not value.startswith(":"):
                return value
            command = value.casefold()
            if command in {":back", ":skip", ":progress", ":help", ":quit"}:
                raise _Navigation(command[1:])
            if command.startswith(":edit "):
                number = command[6:].strip()
                if number.isdigit() and int(number) >= 1:
                    raise _Navigation("edit", int(number) - 1)
                self._write("Error: use :edit N with a positive presentation number.")
                continue
            self._write("Error: unknown command. Use :help to list commands.")

    def _render(self, view: dict) -> None:
        self._write()
        self._write(
            f"Presentation {view['position']} of {view['total']} - "
            f"{view['completed']} completed"
        )
        self._write("=" * 64)
        answer = view["answer"]
        for role in ("a", "b"):
            paper = view[f"paper_{role}"]
            selected = set(answer["evidence"][role])
            self._write()
            self._write(f"Paper {role.upper()}: {paper['title']}")
            self._write(f"Authors: {', '.join(paper['authors'])}")
            for index, sentence in enumerate(paper["evidence"], start=1):
                marker = "*" if sentence in selected else " "
                self._write(f"  {marker}[{index}] {sentence}")
        if answer["label"] is not None:
            self._write()
            self._write(f"Existing label: {answer['label']}")
            self._write(f"Existing rationale: {answer['rationale']}")
        self._write()
        self._write("Commands: :back  :skip  :edit N  :progress  :help  :quit")

    def _prompt_evidence(self, role: str, view: dict) -> tuple[list[int], list[str]]:
        offered = view[f"paper_{role}"]["evidence"]
        while True:
            value = self._read(f"Evidence {role.upper()} numbers: ")
            try:
                indexes = parse_evidence_numbers(value, len(offered))
            except TerminalInputError as exc:
                self._write(f"Error: {exc}")
                continue
            return indexes, [offered[index] for index in indexes]

    def _prompt_label(self) -> int:
        while True:
            value = self._read("Label [0-3]: ")
            try:
                return parse_label(value)
            except TerminalInputError as exc:
                self._write(f"Error: {exc}")

    def _prompt_rationale(self) -> str:
        while True:
            rationale = self._read("Rationale: ").strip()
            if rationale:
                return rationale
            self._write("Error: rationale is required")

    def _prompt_confirmation(self) -> bool:
        while True:
            value = self._read("Save this answer? [y/n] ").casefold()
            if value in {"y", "yes"}:
                return True
            if value in {"n", "no"}:
                return False
            self._write("Error: enter y or n")

    def _collect(self, view: dict) -> tuple[int, str, dict[str, list[str]]] | None:
        indexes_a, evidence_a = self._prompt_evidence("a", view)
        indexes_b, evidence_b = self._prompt_evidence("b", view)
        label = self._prompt_label()
        rationale = self._prompt_rationale()
        self._write()
        self._write("Answer summary")
        self._write(f"  Evidence A: {', '.join(str(index + 1) for index in indexes_a)}")
        self._write(f"  Evidence B: {', '.join(str(index + 1) for index in indexes_b)}")
        self._write(f"  Label: {label}")
        self._write(f"  Rationale: {rationale}")
        if not self._prompt_confirmation():
            self._write("Answer not saved.")
            return None
        return label, rationale, {"a": evidence_a, "b": evidence_b}

    def _first_unanswered(self) -> tuple[int | None, int]:
        first = self.session.presentation(0)
        total = first["total"]
        for index in range(total):
            if self.session.presentation(index)["answer"]["label"] is None:
                return index, total
        return None, total

    def _next_unanswered(self, current: int, total: int) -> int | None:
        for offset in range(1, total + 1):
            index = (current + offset) % total
            if self.session.presentation(index)["answer"]["label"] is None:
                return index
        return None

    def _progress(self, total: int) -> None:
        completed = sum(
            self.session.presentation(index)["answer"]["label"] is not None
            for index in range(total)
        )
        self._write(f"Progress: {completed} completed, {total - completed} remaining.")

    def _help(self) -> None:
        self._write(
            "Commands: :back previous; :skip next; :edit N open presentation N; "
            ":progress counts; :help commands; :quit exit."
        )

    def _handle_navigation(
        self, navigation: _Navigation, current: int, total: int
    ) -> tuple[int, bool]:
        if navigation.action == "quit":
            return current, True
        if navigation.action == "back":
            return max(0, current - 1), False
        if navigation.action == "skip":
            return min(total - 1, current + 1), False
        if navigation.action == "edit":
            if navigation.index is not None and 0 <= navigation.index < total:
                return navigation.index, False
            self._write(f"Error: presentation number must be between 1 and {total}.")
            return current, False
        if navigation.action == "progress":
            self._progress(total)
            return current, False
        if navigation.action == "help":
            self._help()
            return current, False
        return current, False

    def run(self) -> int:
        try:
            current, total = self._first_unanswered()
            if current is None:
                current = 0
                self._write(f"All {total} presentations are answered.")
            while True:
                view = self.session.presentation(current)
                self._render(view)
                try:
                    answer = self._collect(view)
                except _Navigation as navigation:
                    current, should_quit = self._handle_navigation(
                        navigation, current, total
                    )
                    if should_quit:
                        self._write("Review stopped; no unsaved answer was written.")
                        return 0
                    continue
                if answer is None:
                    continue
                label, rationale, evidence = answer
                try:
                    self.session.save_answer(
                        current,
                        label=label,
                        rationale=rationale,
                        evidence=evidence,
                    )
                except ReviewerError as exc:
                    self._write(f"Save failed: {exc}")
                    continue
                self._write("Answer saved.")
                next_index = self._next_unanswered(current, total)
                if next_index is None:
                    self._write(f"All {total} presentations are answered.")
                else:
                    current = next_index
        except (EOFError, KeyboardInterrupt):
            self._write("Review stopped; no unsaved answer was written.")
            return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Review the private P5 adjudication packet in the terminal"
    )
    parser.add_argument("--private-gold", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--benchmark-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    try:
        session = ReviewSession.open(
            packet_path=arguments.private_gold,
            source_dir=arguments.source_dir,
            benchmark_root=arguments.benchmark_root,
            repo_root=arguments.repo_root,
        )
    except (ReviewerError, BenchmarkProtocolError) as exc:
        print(f"Reviewer startup failed: {exc}", file=sys.stderr)
        return 2
    return TerminalReviewer(
        session,
        input_stream=sys.stdin,
        output_stream=sys.stdout,
    ).run()


if __name__ == "__main__":
    raise SystemExit(main())
