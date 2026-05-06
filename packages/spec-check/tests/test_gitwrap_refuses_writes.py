"""The git read-only firewall.

This is the load-bearing safety test for the first of spec-check's two
read-only surfaces. If a future change lets any write subcommand or write
flag through ``run_git``, this file fails the build.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from spec_check.core.gitwrap import (
    KNOWN_WRITE_SUBCOMMANDS,
    READ_ONLY_SUBCOMMANDS,
    GitResult,
    GitWrapperError,
    GitWriteRefused,
    run_git,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Build a tiny throwaway git repo with one commit so read-only verbs have
    something to chew on. We use ``subprocess.run(["git", ...])`` directly here
    because :func:`run_git` *cannot* perform the write operations needed to set
    a fixture up — that's exactly the contract under test.
    """
    if shutil.which("git") is None:
        pytest.skip("git not installed")

    def _git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True, text=True)

    _git("init", "-q", "-b", "main")
    _git("config", "user.email", "test@example.com")
    _git("config", "user.name", "test")
    (tmp_path / "README.md").write_text("hi\n")
    _git("add", "README.md")
    _git("commit", "-q", "-m", "initial")
    return tmp_path


# ---------------------------------------------------------------------------
# Subcommand-level firewall
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subcommand",
    [
        "commit",
        "push",
        "pull",
        "fetch",
        "checkout",
        "switch",
        "reset",
        "rebase",
        "merge",
        "cherry-pick",
        "revert",
        "add",
        "rm",
        "mv",
        "tag",
        "stash",
        "clean",
        "restore",
        "apply",
        "am",
        "init",
        "clone",
        "gc",
        "prune",
        "repack",
        "pack-objects",
        "update-ref",
        "update-index",
        "write-tree",
        "commit-tree",
        "submodule",
        "worktree",
        "notes",
        "bundle",
        "fast-import",
        "filter-branch",
        "filter-repo",
        "replace",
        "lfs",
        "format-patch",
        "send-email",
    ],
)
def test_known_write_subcommand_is_refused(subcommand: str) -> None:
    """Every known-write subcommand from the PRD's enumeration must be refused
    *before* a subprocess runs. We pass `cwd=None` because the call should
    never reach git in the first place.
    """
    with pytest.raises(GitWriteRefused, match=subcommand):
        run_git([subcommand])


def test_every_known_write_subcommand_is_listed_in_the_blocklist_sentinel() -> None:
    """Sanity: KNOWN_WRITE_SUBCOMMANDS must not accidentally include a verb
    that's also on the read-only allowlist. If this test fires, someone added
    a write verb to the allowlist by mistake.
    """
    overlap = KNOWN_WRITE_SUBCOMMANDS & READ_ONLY_SUBCOMMANDS
    assert overlap == set(), f"verbs in both allow + write lists: {overlap}"


def test_unknown_subcommand_is_refused() -> None:
    """Subcommands that aren't on the allowlist are refused even if they
    aren't on KNOWN_WRITE_SUBCOMMANDS — the firewall fails closed.
    """
    with pytest.raises(GitWriteRefused, match="not on spec-check's read-only allowlist"):
        run_git(["wibble"])


def test_empty_args_refused() -> None:
    with pytest.raises(GitWriteRefused, match="no subcommand"):
        run_git([])


# ---------------------------------------------------------------------------
# Flag-level firewall (subcommands that look read-only but accept write flags)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        ["branch", "-d", "feature"],
        ["branch", "-D", "feature"],
        ["branch", "--delete", "feature"],
        ["branch", "-m", "old", "new"],
        ["branch", "-M", "old", "new"],
        ["branch", "--move", "old", "new"],
        ["branch", "-c", "old", "new"],
        ["branch", "-C", "old", "new"],
    ],
)
def test_branch_write_flags_are_refused(args: list[str]) -> None:
    with pytest.raises(GitWriteRefused, match="write operation"):
        run_git(args)


@pytest.mark.parametrize(
    "args",
    [
        ["config", "--set", "user.name", "x"],
        ["config", "--add", "remote.origin.url", "x"],
        ["config", "--unset", "user.name"],
        ["config", "--replace-all", "user.email", "x"],
        ["config", "--remove-section", "remote.origin"],
        ["config", "--rename-section", "old", "new"],
        ["config", "--edit"],
    ],
)
def test_config_write_flags_are_refused(args: list[str]) -> None:
    with pytest.raises(GitWriteRefused, match="write operation"):
        run_git(args)


@pytest.mark.parametrize(
    "args",
    [
        ["reflog", "expire", "--expire=now"],
        ["reflog", "delete", "HEAD@{0}"],
    ],
)
def test_reflog_write_subverbs_refused(args: list[str]) -> None:
    with pytest.raises(GitWriteRefused, match="write operation"):
        run_git(args)


def test_symbolic_ref_delete_refused() -> None:
    with pytest.raises(GitWriteRefused, match="write operation"):
        run_git(["symbolic-ref", "--delete", "HEAD"])


# ---------------------------------------------------------------------------
# Allowed subcommands actually work end-to-end
# ---------------------------------------------------------------------------


def test_rev_parse_head_works(repo: Path) -> None:
    result = run_git(["rev-parse", "HEAD"], cwd=repo)
    assert isinstance(result, GitResult)
    assert result.returncode == 0
    assert len(result.stdout.strip()) == 40


def test_branch_show_current_works(repo: Path) -> None:
    result = run_git(["branch", "--show-current"], cwd=repo)
    assert result.stdout.strip() == "main"


def test_log_works(repo: Path) -> None:
    result = run_git(["log", "--oneline"], cwd=repo)
    assert "initial" in result.stdout


def test_diff_no_color_works(repo: Path) -> None:
    result = run_git(["diff", "--no-color"], cwd=repo)
    assert result.returncode == 0


def test_status_porcelain_works(repo: Path) -> None:
    result = run_git(["status", "--porcelain"], cwd=repo)
    assert result.returncode == 0


def test_config_read_works(repo: Path) -> None:
    # Bare config read is allowed (no write flags).
    result = run_git(["config", "user.email"], cwd=repo)
    assert result.stdout.strip() == "test@example.com"


def test_check_false_returns_nonzero_without_raising(repo: Path) -> None:
    # rev-parse on a bogus ref fails. With check=False we should get the
    # non-zero result rather than an exception.
    result = run_git(["rev-parse", "definitely-not-a-ref"], cwd=repo, check=False)
    assert result.returncode != 0


def test_check_true_raises_on_nonzero(repo: Path) -> None:
    with pytest.raises(GitWrapperError, match="exited"):
        run_git(["rev-parse", "definitely-not-a-ref"], cwd=repo, check=True)
