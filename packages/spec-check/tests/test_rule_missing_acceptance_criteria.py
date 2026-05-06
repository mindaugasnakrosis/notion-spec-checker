"""Tests for spec_check.rules.missing_acceptance_criteria."""

from __future__ import annotations

from spec_check.core.schema import Confidence, Severity
from spec_check.rules import MissingAcceptanceCriteria

from tests.fixtures import make_context, make_criterion, make_spec


def test_silent_when_no_spec() -> None:
    findings = MissingAcceptanceCriteria().evaluate(make_context(parsed_spec=None))
    assert findings == []


def test_silent_when_section_missing() -> None:
    # missing_ac_section owns this case; this rule must stay quiet.
    spec = make_spec(has_ac_section=False, criteria=[])
    findings = MissingAcceptanceCriteria().evaluate(make_context(parsed_spec=spec))
    assert findings == []


def test_silent_when_section_has_criteria() -> None:
    spec = make_spec(
        has_ac_section=True,
        criteria=[make_criterion("User can log in.")],
    )
    findings = MissingAcceptanceCriteria().evaluate(make_context(parsed_spec=spec))
    assert findings == []


def test_fires_when_section_present_but_empty() -> None:
    spec = make_spec(has_ac_section=True, criteria=[])
    findings = MissingAcceptanceCriteria().evaluate(make_context(parsed_spec=spec))
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "missing_acceptance_criteria"
    assert f.severity is Severity.HIGH
    assert f.confidence is Confidence.HIGH
    assert "notion-page-conventions.md" in f.knowledge_refs
    assert f.evidence["notion_page_id"] == "page-A"
    assert f.recommended_investigation.endswith("?")
