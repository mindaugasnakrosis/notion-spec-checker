"""Tests for spec_check.rules.multiple_specs_referenced."""

from __future__ import annotations

from spec_check.core.schema import Confidence, Severity
from spec_check.rules import MultipleSpecsReferenced

from tests.fixtures import make_context


def test_silent_when_no_referenced_tickets() -> None:
    findings = MultipleSpecsReferenced().evaluate(make_context(referenced_tickets=()))
    assert findings == []


def test_silent_when_one_ticket_referenced() -> None:
    findings = MultipleSpecsReferenced().evaluate(
        make_context(referenced_tickets=("PROJ-1",))
    )
    assert findings == []


def test_silent_when_only_duplicates() -> None:
    # Duplicated mention of the same ticket must not trip the rule.
    findings = MultipleSpecsReferenced().evaluate(
        make_context(referenced_tickets=("PROJ-1", "PROJ-1"))
    )
    assert findings == []


def test_fires_when_two_distinct_tickets() -> None:
    findings = MultipleSpecsReferenced().evaluate(
        make_context(referenced_tickets=("PROJ-1", "PROJ-2"))
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "multiple_specs_referenced"
    assert f.severity is Severity.MEDIUM
    assert f.confidence is Confidence.HIGH
    assert "notion-page-conventions.md" in f.knowledge_refs
    assert f.evidence["referenced_tickets"] == ["PROJ-1", "PROJ-2"]
    assert "PROJ-1" in f.recommended_investigation
    assert "PROJ-2" in f.recommended_investigation
    assert f.recommended_investigation.endswith("?")


def test_deduplicates_preserving_order() -> None:
    findings = MultipleSpecsReferenced().evaluate(
        make_context(referenced_tickets=("PROJ-2", "PROJ-1", "PROJ-2", "PROJ-3"))
    )
    assert len(findings) == 1
    assert findings[0].evidence["referenced_tickets"] == ["PROJ-2", "PROJ-1", "PROJ-3"]


def test_evidence_carries_manifest_context() -> None:
    findings = MultipleSpecsReferenced().evaluate(
        make_context(referenced_tickets=("PROJ-1", "PROJ-2"))
    )
    f = findings[0]
    assert f.evidence["branch"] == "feat/PROJ-1-login"
    assert f.evidence["resolved_spec_id"] == "page-A"
    assert f.evidence["resolution_method"] == "override"
