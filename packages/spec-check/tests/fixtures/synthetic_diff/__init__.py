"""Tiny :class:`ParsedDiff` factory for rule tests."""

from __future__ import annotations

from spec_check.core.schema import ChangedHunk, ParsedDiff


def _hunk(
    file: str,
    *,
    added: list[str] | None = None,
    removed: list[str] | None = None,
    is_test: bool = False,
    start_line: int = 1,
) -> ChangedHunk:
    added_lines = added or []
    removed_lines = removed or []
    end_line = start_line + max(0, len(added_lines) + len(removed_lines) - 1)
    return ChangedHunk(
        file=file,
        start_line=start_line,
        end_line=end_line,
        added_lines=added_lines,
        removed_lines=removed_lines,
        is_test_file=is_test,
    )


def make_diff(
    *,
    branch: str = "feat/PROJ-1-login",
    base_ref: str = "origin/main",
    head_sha: str = "deadbeef",
    additions: int = 10,
    deletions: int = 0,
    files_changed: int = 1,
    hunks: list[ChangedHunk] | None = None,
    test_files_touched: list[str] | None = None,
) -> ParsedDiff:
    return ParsedDiff(
        base_ref=base_ref,
        head_sha=head_sha,
        branch=branch,
        files_changed=files_changed,
        additions=additions,
        deletions=deletions,
        hunks=hunks or [_hunk("src/auth.py", added=["return True"])],
        test_files_touched=test_files_touched or [],
    )
