"""Tests for spec_check.rules.missing_ac_section."""

from __future__ import annotations

from spec_check.core.schema import Confidence, Severity
from spec_check.rules import MissingAcSection

from tests.fixtures import make_context, make_criterion, make_spec


def test_silent_when_spec_has_ac_section() -> None:
    spec = make_spec(has_ac_section=True, criteria=[make_criterion("User can log in.")])
    findings = MissingAcSection().evaluate(make_context(parsed_spec=spec))
    assert findings == []


def test_silent_when_spec_is_missing() -> None:
    # No spec at all → another rule speaks. This rule must not double up.
    findings = MissingAcSection().evaluate(make_context(parsed_spec=None))
    assert findings == []


def test_fires_when_ac_section_absent() -> None:
    spec = make_spec(has_ac_section=False, criteria=[])
    findings = MissingAcSection().evaluate(make_context(parsed_spec=spec))
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "missing_ac_section"
    assert f.severity is Severity.HIGH
    assert f.confidence is Confidence.HIGH
    assert "notion-page-conventions.md" in f.knowledge_refs
    assert f.evidence["notion_page_id"] == "page-A"
    assert f.evidence["criteria_found"] == 0
    # Recommendation is a question for the human.
    assert f.recommended_investigation.endswith("?")


def test_fires_even_when_some_criteria_were_loose_paragraphs() -> None:
    # A spec without an explicit AC heading is "missing" even if the parser
    # happened to extract paragraphs as fallback criteria — the convention
    # is the named heading.
    spec = make_spec(
        has_ac_section=False,
        criteria=[make_criterion("Some loose paragraph", style="bullet")],
    )
    findings = MissingAcSection().evaluate(make_context(parsed_spec=spec))
    assert len(findings) == 1
    assert findings[0].evidence["criteria_found"] == 1
