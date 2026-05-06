"""Tests for spec_check.rules.scope_creep."""

from __future__ import annotations

from pathlib import Path

from spec_check.core.config import SpecCheckSettings
from spec_check.core.schema import Confidence, Severity
from spec_check.rules import ScopeCreep

from tests.fixtures import make_context, make_criterion, make_diff, make_spec


def _settings(per_criterion: int = 200, tmp: Path | None = None) -> SpecCheckSettings:
    return SpecCheckSettings(
        snapshot_root=(tmp or Path("/tmp/spec-check-test-scope")) / "snap",
        scope_creep_lines_per_criterion=per_criterion,
    )


def test_silent_when_spec_missing() -> None:
    diff = make_diff(additions=10000, deletions=0)
    findings = ScopeCreep().evaluate(make_context(parsed_spec=None, parsed_diff=diff))
    assert findings == []


def test_silent_when_diff_missing() -> None:
    spec = make_spec(criteria=[make_criterion("X")])
    findings = ScopeCreep().evaluate(make_context(parsed_spec=spec, parsed_diff=None))
    assert findings == []


def test_silent_when_resolution_unresolved() -> None:
    # large_diff_without_spec owns the unresolved/ambiguous case.
    spec = make_spec(criteria=[make_criterion("X")])
    diff = make_diff(additions=10000)
    ctx = make_context(
        parsed_spec=spec,
        parsed_diff=diff,
        spec_resolution_method="unresolved",
        settings=_settings(per_criterion=10),
    )
    assert ScopeCreep().evaluate(ctx) == []


def test_silent_when_resolution_ambiguous() -> None:
    spec = make_spec(criteria=[make_criterion("X")])
    diff = make_diff(additions=10000)
    ctx = make_context(
        parsed_spec=spec,
        parsed_diff=diff,
        spec_resolution_method="ambiguous",
        settings=_settings(per_criterion=10),
    )
    assert ScopeCreep().evaluate(ctx) == []


def test_silent_when_no_criteria() -> None:
    # missing_acceptance_criteria / missing_ac_section own this case.
    spec = make_spec(has_ac_section=True, criteria=[])
    diff = make_diff(additions=10000)
    ctx = make_context(
        parsed_spec=spec,
        parsed_diff=diff,
        spec_resolution_method="ticket_key",
        settings=_settings(per_criterion=10),
    )
    assert ScopeCreep().evaluate(ctx) == []


def test_silent_when_within_budget(tmp_path: Path) -> None:
    spec = make_spec(criteria=[make_criterion("AC-1"), make_criterion("AC-2", cid="AC-2")])
    diff = make_diff(additions=200, deletions=100)  # 300 ≤ 2 * 200
    ctx = make_context(
        parsed_spec=spec,
        parsed_diff=diff,
        spec_resolution_method="ticket_key",
        settings=_settings(per_criterion=200, tmp=tmp_path),
    )
    assert ScopeCreep().evaluate(ctx) == []


def test_fires_when_budget_exceeded(tmp_path: Path) -> None:
    spec = make_spec(criteria=[make_criterion("AC-1")])
    diff = make_diff(additions=400, deletions=50, files_changed=8)  # 450 > 1 * 200
    ctx = make_context(
        parsed_spec=spec,
        parsed_diff=diff,
        spec_resolution_method="ticket_key",
        settings=_settings(per_criterion=200, tmp=tmp_path),
    )
    findings = ScopeCreep().evaluate(ctx)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "scope_creep"
    assert f.severity is Severity.MEDIUM
    assert f.confidence is Confidence.MEDIUM
    assert "invest-criteria.md" in f.knowledge_refs
    assert f.evidence["criteria_count"] == 1
    assert f.evidence["total_lines"] == 450
    assert f.evidence["budget_total"] == 200
    assert f.evidence["per_criterion_budget"] == 200
    assert f.evidence["resolution_method"] == "ticket_key"
    assert f.recommended_investigation.endswith("?")


def test_fires_at_strict_inequality(tmp_path: Path) -> None:
    # Equal-to-budget is silent; above-budget fires.
    spec = make_spec(criteria=[make_criterion("AC-1")])
    at_budget = make_diff(additions=100, deletions=0)
    over_budget = make_diff(additions=101, deletions=0)
    ctx_at = make_context(
        parsed_spec=spec,
        parsed_diff=at_budget,
        spec_resolution_method="override",
        settings=_settings(per_criterion=100, tmp=tmp_path),
    )
    ctx_over = make_context(
        parsed_spec=spec,
        parsed_diff=over_budget,
        spec_resolution_method="override",
        settings=_settings(per_criterion=100, tmp=tmp_path),
    )
    assert ScopeCreep().evaluate(ctx_at) == []
    assert len(ScopeCreep().evaluate(ctx_over)) == 1
