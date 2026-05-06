"""Tests for spec_check.rules.criterion_without_test."""

from __future__ import annotations

from spec_check.core.schema import Confidence, Severity
from spec_check.rules import CriterionWithoutTest

from tests.fixtures import make_context, make_criterion, make_diff, make_spec


def test_silent_when_no_spec() -> None:
    diff = make_diff(additions=10)
    findings = CriterionWithoutTest().evaluate(make_context(parsed_spec=None, parsed_diff=diff))
    assert findings == []


def test_silent_when_no_diff() -> None:
    spec = make_spec(criteria=[make_criterion("X")])
    findings = CriterionWithoutTest().evaluate(make_context(parsed_spec=spec, parsed_diff=None))
    assert findings == []


def test_silent_when_spec_has_no_criteria() -> None:
    spec = make_spec(has_ac_section=True, criteria=[])
    diff = make_diff(additions=10)
    findings = CriterionWithoutTest().evaluate(make_context(parsed_spec=spec, parsed_diff=diff))
    assert findings == []


def test_silent_when_test_files_touched() -> None:
    spec = make_spec(criteria=[make_criterion("X")])
    diff = make_diff(additions=10)
    findings = CriterionWithoutTest().evaluate(
        make_context(
            parsed_spec=spec,
            parsed_diff=diff,
            test_files_touched=["tests/test_auth.py"],
        )
    )
    assert findings == []


def test_silent_when_diff_is_empty() -> None:
    spec = make_spec(criteria=[make_criterion("X")])
    diff = make_diff(additions=0, deletions=0)
    findings = CriterionWithoutTest().evaluate(make_context(parsed_spec=spec, parsed_diff=diff))
    assert findings == []


def test_fires_when_spec_has_criteria_and_diff_lacks_tests() -> None:
    spec = make_spec(
        criteria=[
            make_criterion("User can log in.", cid="ac1"),
            make_criterion("User sees an error on bad credentials.", cid="ac2"),
        ]
    )
    diff = make_diff(additions=42, deletions=3, files_changed=2)
    findings = CriterionWithoutTest().evaluate(
        make_context(parsed_spec=spec, parsed_diff=diff, test_files_touched=[])
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "criterion_without_test"
    assert f.severity is Severity.MEDIUM
    assert f.confidence is Confidence.MEDIUM
    assert "invest-criteria.md" in f.knowledge_refs
    assert f.evidence["criteria_count"] == 2
    assert f.evidence["test_files_touched"] == []
    assert f.recommended_investigation.endswith("?")
