"""Pydantic schemas for spec-check.

Two-axis findings (severity × confidence), parsed Notion specs, parsed git
diffs, and the on-disk check manifest. The rule layer consumes these and
produces Findings; the report layer renders Findings to markdown + YAML.
"""

from spec_check.core.schema.diff import ChangedHunk, ParsedDiff
from spec_check.core.schema.finding import Confidence, Finding, Severity
from spec_check.core.schema.findings_doc import BranchMetaSnapshot, FindingsDocument
from spec_check.core.schema.manifest import CheckManifest, CollectorStatus
from spec_check.core.schema.spec import AcceptanceCriterion, AmbiguityFlag, ParsedSpec

__all__ = [
    "AcceptanceCriterion",
    "AmbiguityFlag",
    "BranchMetaSnapshot",
    "ChangedHunk",
    "CheckManifest",
    "CollectorStatus",
    "Confidence",
    "Finding",
    "FindingsDocument",
    "ParsedDiff",
    "ParsedSpec",
    "Severity",
]
