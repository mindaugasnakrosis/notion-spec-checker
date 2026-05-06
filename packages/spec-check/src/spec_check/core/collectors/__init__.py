"""Collectors gather raw data for one check run.

Each collector is a pure function ``(context) -> CollectorOutput[T]``. A
collector handles its own errors: a failure does not raise out of the
collector, it returns ``CollectorOutput(status="failed", detail=...)`` so
the rest of the run can proceed and rules that depended on this collector
can emit Info findings rather than the whole check exploding.

Four collectors in v1:

- :mod:`spec_check.core.collectors.git_diff` — staged, unstaged, and
  last-N-commit diffs. Writes ``diff/*.json`` artefacts.
- :mod:`spec_check.core.collectors.branch_meta` — branch name, base ref,
  head sha, last commit message + trailers, branch-creation timestamp.
- :mod:`spec_check.core.collectors.notion_spec` — raw Notion page +
  blocks for the resolved spec. Writes ``spec/raw_blocks.json``.
- :mod:`spec_check.core.collectors.test_files` — intersect a parsed diff
  with test-path patterns. No artefact; the result feeds back into the
  diff's ``test_files_touched`` field.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from spec_check.core.schema import CollectorStatus

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class CollectorOutput(Generic[T]):
    """The contract every collector returns.

    ``status`` always populates the manifest. ``data`` is the in-memory
    payload for the orchestrator to hand on to rules; it is ``None`` when
    ``status.state`` is ``failed`` or ``skipped``.
    """

    status: CollectorStatus
    data: T | None = None
