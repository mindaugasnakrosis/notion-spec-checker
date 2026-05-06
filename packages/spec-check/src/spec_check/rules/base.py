"""Rule base types: ``RuleContext`` and the ``Rule`` protocol.

Each rule is a small class with class-level metadata and an ``evaluate``
method that returns a list of :class:`Finding` objects (zero, one, or
many). Rules are pure functions of their context: same ``RuleContext`` in,
same findings out. They never write anywhere — that's enforced by every
rule's signature returning a list rather than touching ``ctx``.

Step 15 builds the registry and dispatcher on top of this. Step 11 only
needs the type to exist so the easy three rules can declare it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from spec_check.core.config import SpecCheckSettings
from spec_check.core.schema import CheckManifest, Finding, ParsedDiff, ParsedSpec


@dataclass(frozen=True, slots=True)
class RuleContext:
    """Everything a rule is allowed to look at.

    Anything the rule needs that isn't on this context belongs in a new
    field here, not in a global lookup. That keeps rules trivially
    testable (build a context, call evaluate, assert findings).

    Attributes
    ----------
    parsed_spec
        ``None`` when the Notion spec collector or parser failed. Rules
        that depend on a spec MUST handle ``None`` explicitly.
    parsed_diff
        ``None`` when the git diff collector failed. Same rule.
    manifest
        Always present — the orchestrator writes this last.
    settings
        The merged spec-check settings (for thresholds, ambiguity phrases,
        etc.).
    spec_resolution_method
        One of: ``override``, ``ticket_key``, ``trailer``, ``fuzzy``,
        ``ambiguous``, ``unresolved``.
    test_files_touched
        Test file paths the diff modified (from the test_files collector).
        May be empty.
    referenced_tickets
        Distinct ticket keys mentioned in the head commit message (``Refs:``
        trailers and ``[PROJ-123]`` brackets), as collected by
        :mod:`branch_meta`. Used by ``multiple_specs_referenced``. Empty when
        the branch_meta collector failed or the commit had no trailers.
    branch_created_at
        When the branch was created, as parsed from ``git reflog``.
        ``None`` when the reflog is missing (shallow clones, fresh CI
        checkouts) or when the branch_meta collector failed. Used by
        ``spec_modified_after_branch`` — when ``None`` that rule stays
        silent rather than guessing.
    """

    parsed_spec: ParsedSpec | None
    parsed_diff: ParsedDiff | None
    manifest: CheckManifest
    settings: SpecCheckSettings
    spec_resolution_method: str
    test_files_touched: list[str]
    referenced_tickets: tuple[str, ...] = ()
    branch_created_at: datetime | None = None


@runtime_checkable
class Rule(Protocol):
    """A rule. Class-level metadata + ``evaluate``."""

    rule_id: str
    title: str
    knowledge_refs: tuple[str, ...]

    def evaluate(self, ctx: RuleContext) -> list[Finding]: ...
