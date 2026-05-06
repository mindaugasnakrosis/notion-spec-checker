"""Read-only git subprocess wrapper.

This module is the **first** of two read-only firewalls (the other is
``spec_check.core.notion``). Only git subcommands on the explicit allowlist
are permitted; any other subcommand raises :class:`GitWriteRefused`.

Why an allowlist (not a blocklist):
- The set of read-only git subcommands is small and stable.
- The set of write subcommands grows: every git release adds verbs, plugins
  invent more (``git lfs push``, ``git absorb``, …), and a blocklist will
  silently miss them. An allowlist fails closed.

The allowlist lists the subcommand only. Flag-level guards live in
:func:`_assert_no_write_flags` because some "read" subcommands accept write
flags (``git stash list`` is read-only; ``git stash`` without args writes).

This wrapper does not parse output. Each caller decides whether to ask for
``--porcelain``, ``--no-color``, JSON, etc.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

# Subcommands that never modify repository state. Exhaustive for v1; adding a
# new one is a deliberate review event.
READ_ONLY_SUBCOMMANDS: frozenset[str] = frozenset(
    {
        "rev-parse",
        "branch",  # write-flag-guarded below; bare `git branch` lists, `git branch -D` deletes
        "log",
        "show",
        "diff",
        "status",
        "ls-files",
        "ls-tree",
        "cat-file",
        "for-each-ref",
        "merge-base",
        "name-rev",
        "reflog",  # `reflog show` is read-only; write subcommands like `expire`/`delete` are flag-guarded
        "config",  # bare `git config <name>` reads; `--set` / `--unset` / `--add` / `--replace-all` are write-flag-guarded
        "rev-list",
        "describe",
        "shortlog",
        "blame",
        "show-ref",
        "symbolic-ref",  # read-only when called with no extra args; --delete is flag-guarded
        "version",
    }
)

# Per-subcommand flag guards. If a flag in this set is present, refuse the call
# even though the subcommand is on the allowlist.
_WRITE_FLAGS_BY_SUBCOMMAND: dict[str, frozenset[str]] = {
    "branch": frozenset(
        {"-d", "-D", "--delete", "-m", "-M", "--move", "-c", "-C", "--copy", "--edit-description"}
    ),
    "config": frozenset(
        {
            "--set",
            "--add",
            "--replace-all",
            "--unset",
            "--unset-all",
            "--rename-section",
            "--remove-section",
            "--edit",
        }
    ),
    "reflog": frozenset({"expire", "delete"}),  # these are sub-subcommands
    "symbolic-ref": frozenset({"--delete", "-d"}),
}

# Sentinel set of subcommands the caller might *think* are read-only but which
# always write. Listed for explicit error messages and the test guard.
KNOWN_WRITE_SUBCOMMANDS: frozenset[str] = frozenset(
    {
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
        "stash",  # bare `git stash` writes; `git stash list/show` are read but we route those through `log`-style verbs instead
        "clean",
        "restore",
        "apply",
        "am",
        "format-patch",
        "send-email",
        "gc",
        "prune",
        "repack",
        "pack-objects",
        "update-ref",
        "update-index",
        "write-tree",
        "commit-tree",
        "init",
        "clone",
        "submodule",
        "worktree",
        "notes",
        "bundle",
        "fast-import",
        "filter-branch",
        "filter-repo",
        "replace",
        "lfs",  # plugin; always treated as write to stay safe
    }
)


class GitWriteRefused(RuntimeError):
    """Raised when the wrapper is asked to invoke a non-allowlisted git subcommand."""


class GitWrapperError(RuntimeError):
    """Raised when git itself fails (non-zero exit) inside an allowed call."""


@dataclass(frozen=True, slots=True)
class GitResult:
    """Result of a successful read-only git invocation."""

    args: tuple[str, ...]
    stdout: str
    stderr: str
    returncode: int


def _assert_subcommand_allowed(subcommand: str) -> None:
    if subcommand not in READ_ONLY_SUBCOMMANDS:
        raise GitWriteRefused(
            f"git {subcommand!r} is not on spec-check's read-only allowlist. "
            f"spec-check is read-only on git by contract; refusing the call."
        )


def _assert_no_write_flags(subcommand: str, args: Sequence[str]) -> None:
    forbidden = _WRITE_FLAGS_BY_SUBCOMMAND.get(subcommand)
    if not forbidden:
        return
    for token in args:
        if token in forbidden:
            raise GitWriteRefused(
                f"git {subcommand} {token!r} is a write operation. "
                f"spec-check is read-only on git by contract; refusing the call."
            )


def run_git(
    args: Sequence[str],
    *,
    cwd: Path | str | None = None,
    timeout: float | None = 30.0,
    check: bool = True,
) -> GitResult:
    """Invoke ``git <subcommand> [...args]`` with the read-only firewall in place.

    Parameters
    ----------
    args:
        The arguments after ``git``. ``args[0]`` is the subcommand and is
        checked against the allowlist; remaining args are checked against
        per-subcommand write-flag guards.
    cwd:
        Working directory. Required for any subcommand that operates on a
        repository (effectively all of them); the caller is responsible.
    timeout:
        Subprocess timeout in seconds. ``None`` disables.
    check:
        If True (default), non-zero exit raises :class:`GitWrapperError`.

    Raises
    ------
    GitWriteRefused
        If the subcommand or a flag is not on the read-only allowlist.
    GitWrapperError
        If git is not installed, the call times out, or git exits non-zero
        and ``check=True``.
    """
    if not args:
        raise GitWriteRefused("run_git called with no subcommand")

    subcommand = args[0]
    _assert_subcommand_allowed(subcommand)
    _assert_no_write_flags(subcommand, args[1:])

    git_bin = shutil.which("git")
    if git_bin is None:
        raise GitWrapperError("git executable not found on PATH")

    try:
        proc = subprocess.run(  # noqa: S603 — args validated above
            [git_bin, *args],
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitWrapperError(f"git {subcommand} timed out after {timeout}s") from exc

    if check and proc.returncode != 0:
        raise GitWrapperError(
            f"git {' '.join(args)} exited {proc.returncode}: {proc.stderr.strip()}"
        )

    return GitResult(
        args=tuple(args),
        stdout=proc.stdout,
        stderr=proc.stderr,
        returncode=proc.returncode,
    )
