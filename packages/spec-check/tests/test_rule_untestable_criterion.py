"""Tests for spec_check.rules.untestable_criterion."""

from __future__ import annotations

from spec_check.core.schema import AmbiguityFlag, Confidence, Severity
from spec_check.rules import UntestableCriterion

from tests.fixtures import make_context, make_criterion, make_spec


def test_silent_when_no_spec() -> None:
    findings = UntestableCriterion().evaluate(make_context(parsed_spec=None))
    assert findings == []


def test_silent_when_all_criteria_observable() -> None:
    spec = make_spec(
        criteria=[
            make_criterion("User can log in.", cid="AC-1", observable=True),
            make_criterion(
                "Given valid credentials, when the user submits, then the "
                "session cookie is set.",
                cid="AC-2",
                style="given_when_then",
                observable=True,
            ),
        ]
    )
    findings = UntestableCriterion().evaluate(make_context(parsed_spec=spec))
    assert findings == []


def test_silent_when_no_criteria() -> None:
    spec = make_spec(has_ac_section=True, criteria=[])
    findings = UntestableCriterion().evaluate(make_context(parsed_spec=spec))
    assert findings == []


def test_fires_one_finding_per_unobservable_criterion() -> None:
    spec = make_spec(
        criteria=[
            make_criterion("User can log in.", cid="AC-1", observable=True),
            make_criterion(
                "Login is fast.",
                cid="AC-2",
                observable=False,
                ambiguity_flags=[AmbiguityFlag(phrase="fast", reason="imprecise")],
            ),
            make_criterion(
                "The system is robust.",
                cid="AC-3",
                observable=False,
                ambiguity_flags=[AmbiguityFlag(phrase="robust", reason="imprecise")],
            ),
        ]
    )
    findings = UntestableCriterion().evaluate(make_context(parsed_spec=spec))
    assert [f.evidence["criterion_id"] for f in findings] == ["AC-2", "AC-3"]


def test_finding_shape() -> None:
    spec = make_spec(
        criteria=[
            make_criterion(
                "The cache is invalidated.",
                cid="AC-1",
                style="bullet",
                observable=False,
            ),
        ]
    )
    findings = UntestableCriterion().evaluate(make_context(parsed_spec=spec))
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "untestable_criterion"
    assert f.severity is Severity.MEDIUM
    assert f.confidence is Confidence.MEDIUM
    assert "observable-acceptance-criteria.md" in f.knowledge_refs
    assert f.evidence["criterion_id"] == "AC-1"
    assert f.evidence["criterion_text"] == "The cache is invalidated."
    assert f.evidence["criterion_style"] == "bullet"
    assert f.evidence["ambiguity_flag_count"] == 0
    assert f.recommended_investigation.endswith("?")
    assert "AC-1" in f.recommended_investigation


def test_fires_independently_of_ambiguity_flags() -> None:
    # observable=False without any ambiguity flag (a future parser
    # heuristic could legitimately produce this state — the rule must
    # not require flags to fire).
    spec = make_spec(
        criteria=[
            make_criterion(
                "It works as expected.",
                cid="AC-1",
                style="bullet",
                observable=False,
                ambiguity_flags=[],
            ),
        ]
    )
    findings = UntestableCriterion().evaluate(make_context(parsed_spec=spec))
    assert len(findings) == 1
    assert findings[0].evidence["ambiguity_flag_count"] == 0
