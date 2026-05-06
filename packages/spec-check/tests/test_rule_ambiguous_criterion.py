"""Tests for spec_check.rules.ambiguous_criterion."""

from __future__ import annotations

from spec_check.core.schema import AmbiguityFlag, Confidence, Severity
from spec_check.rules import AmbiguousCriterion

from tests.fixtures import make_context, make_criterion, make_spec


def _flag(phrase: str) -> AmbiguityFlag:
    return AmbiguityFlag(phrase=phrase, reason=f"contains imprecise phrase {phrase!r}")


def test_silent_when_no_spec() -> None:
    findings = AmbiguousCriterion().evaluate(make_context(parsed_spec=None))
    assert findings == []


def test_silent_when_spec_has_no_criteria() -> None:
    spec = make_spec(criteria=[])
    findings = AmbiguousCriterion().evaluate(make_context(parsed_spec=spec))
    assert findings == []


def test_silent_when_no_criterion_has_flags() -> None:
    spec = make_spec(
        criteria=[
            make_criterion("User can log in.", cid="AC-1"),
            make_criterion("User receives a 401 on bad credentials.", cid="AC-2"),
        ]
    )
    findings = AmbiguousCriterion().evaluate(make_context(parsed_spec=spec))
    assert findings == []


def test_fires_one_finding_per_flagged_criterion() -> None:
    spec = make_spec(
        criteria=[
            make_criterion("User can log in.", cid="AC-1"),
            make_criterion(
                "Login should be fast.",
                cid="AC-2",
                ambiguity_flags=[_flag("fast")],
            ),
            make_criterion(
                "Errors are handled appropriately and remain user-friendly.",
                cid="AC-3",
                ambiguity_flags=[_flag("appropriately"), _flag("user-friendly")],
            ),
        ]
    )
    findings = AmbiguousCriterion().evaluate(make_context(parsed_spec=spec))
    assert [f.evidence["criterion_id"] for f in findings] == ["AC-2", "AC-3"]


def test_finding_shape_for_single_phrase() -> None:
    spec = make_spec(
        criteria=[
            make_criterion(
                "Login should be fast.",
                cid="AC-1",
                ambiguity_flags=[_flag("fast")],
            ),
        ]
    )
    findings = AmbiguousCriterion().evaluate(make_context(parsed_spec=spec))
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "ambiguous_criterion"
    assert f.severity is Severity.MEDIUM
    assert f.confidence is Confidence.MEDIUM
    assert "ambiguity-in-acceptance-criteria.md" in f.knowledge_refs
    assert f.evidence["criterion_id"] == "AC-1"
    assert f.evidence["criterion_text"] == "Login should be fast."
    assert f.evidence["ambiguous_phrases"] == ["fast"]
    assert f.evidence["flag_reasons"] == ["contains imprecise phrase 'fast'"]
    assert f.recommended_investigation.endswith("?")
    assert "'fast'" in f.recommended_investigation


def test_recommended_investigation_lists_all_phrases() -> None:
    spec = make_spec(
        criteria=[
            make_criterion(
                "Errors are handled appropriately and remain user-friendly.",
                cid="AC-1",
                ambiguity_flags=[_flag("appropriately"), _flag("user-friendly")],
            ),
        ]
    )
    findings = AmbiguousCriterion().evaluate(make_context(parsed_spec=spec))
    rec = findings[0].recommended_investigation
    assert "'appropriately'" in rec
    assert "'user-friendly'" in rec
