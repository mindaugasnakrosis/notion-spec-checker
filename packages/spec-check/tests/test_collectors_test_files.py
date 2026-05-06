"""Tests for spec_check.core.collectors.test_files."""

from __future__ import annotations

from spec_check.core.collectors.test_files import collect_test_files
from spec_check.core.schema import ChangedHunk, ParsedDiff


def _diff_with(files: list[tuple[str, bool]]) -> ParsedDiff:
    return ParsedDiff(
        base_ref="main",
        head_sha="abcdef1",
        branch="feat/x",
        files_changed=len(files),
        additions=0,
        deletions=0,
        hunks=[
            ChangedHunk(file=f, start_line=1, end_line=1, is_test_file=is_test)
            for f, is_test in files
        ],
    )


def test_collects_files_marked_as_test() -> None:
    diff = _diff_with([("tests/test_a.py", True), ("src/main.py", False)])
    out = collect_test_files(diff)
    assert out.status.state == "ok"
    assert out.data == ["tests/test_a.py"]


def test_falls_back_to_path_heuristic_if_flag_missing() -> None:
    """A hunk that wasn't tagged is_test_file at parse time still gets
    classified by name — the collector layer is the last line of defence.
    """
    diff = _diff_with([("foo/__tests__/x.test.ts", False), ("foo/main.ts", False)])
    out = collect_test_files(diff)
    assert out.data == ["foo/__tests__/x.test.ts"]


def test_dedupes_and_sorts() -> None:
    diff = _diff_with(
        [
            ("tests/test_b.py", True),
            ("tests/test_a.py", True),
            ("tests/test_a.py", True),  # repeat hunk, same file
        ]
    )
    out = collect_test_files(diff)
    assert out.data == ["tests/test_a.py", "tests/test_b.py"]


def test_no_tests_returns_empty_list() -> None:
    diff = _diff_with([("src/main.py", False)])
    out = collect_test_files(diff)
    assert out.data == []
