"""Identify test files inside a parsed diff.

Used by the ``criterion_without_test`` rule (step 11) to ask "is there at
least one test file changed alongside this diff?" — and indirectly by
the orchestrator to populate ``ParsedDiff.test_files_touched``.

This module is a derivation, not an IO collector: it does not write to
disk. It exists as a separate collector so the rule layer has a stable
manifest entry to depend on.
"""

from __future__ import annotations

from spec_check.core.collectors.git_diff import _looks_like_test_file
from spec_check.core.schema import CollectorStatus, ParsedDiff

from . import CollectorOutput


def collect_test_files(diff: ParsedDiff) -> CollectorOutput[list[str]]:
    """Return the test files touched by the diff, sorted and deduplicated.

    Always succeeds. The empty-list case is meaningful — it tells the
    ``criterion_without_test`` rule that the diff has no test coverage
    delta at all.
    """
    files = sorted({h.file for h in diff.hunks if h.is_test_file or _looks_like_test_file(h.file)})
    return CollectorOutput(
        status=CollectorStatus(name="test_files", state="ok"),
        data=files,
    )
