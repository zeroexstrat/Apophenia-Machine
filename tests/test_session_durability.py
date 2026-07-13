"""Authoritative sessions must never depend on purgeable worktrees."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

from athanasor.session.durability import assert_durable_worktree, temporary_root_for


def test_durable_worktree_passes(tmp_path: Path) -> None:
    durable_root = tmp_path / "durable"
    durable_root.mkdir()

    assert temporary_root_for(durable_root, roots=(tmp_path / "temporary",)) is None
    assert assert_durable_worktree(durable_root, roots=(tmp_path / "temporary",)) == durable_root.resolve()


@pytest.mark.parametrize("name", ["tmp", "private-tmp", "var-tmp", "platform-temp"])
def test_temporary_worktree_fails_closed(tmp_path: Path, name: str) -> None:
    temporary_root = tmp_path / name
    repo = temporary_root / "apophenia-machine"
    repo.mkdir(parents=True)

    with pytest.raises(RuntimeError, match="temporary storage") as excinfo:
        assert_durable_worktree(repo, roots=(temporary_root,))

    message = str(excinfo.value)
    assert str(repo.resolve()) in message
    assert str(temporary_root.resolve()) in message
    assert "durable" in message


def test_resolved_alias_cannot_bypass_guard(tmp_path: Path) -> None:
    temporary_root = tmp_path / "temporary"
    repo = temporary_root / "repo"
    alias = tmp_path / "alias"
    repo.mkdir(parents=True)
    alias.symlink_to(temporary_root, target_is_directory=True)

    assert temporary_root_for(alias / "repo", roots=(temporary_root,)) == temporary_root.resolve()
    with pytest.raises(RuntimeError, match="temporary storage"):
        assert_durable_worktree(alias / "repo", roots=(temporary_root,))


def test_similar_prefix_is_not_treated_as_descendant(tmp_path: Path) -> None:
    temporary_root = tmp_path / "tmp"
    durable_root = tmp_path / "tmp-durable" / "repo"
    temporary_root.mkdir()
    durable_root.mkdir(parents=True)

    assert temporary_root_for(durable_root, roots=(temporary_root,)) is None


def test_standalone_check_rejects_temporary_root(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "check_durable_worktree.py"

    result = subprocess.run(
        [sys.executable, str(script), "--root", str(tmp_path / "repo")],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "temporary storage" in result.stdout
