"""Tests for spec_check.rules.large_diff_without_spec."""

from __future__ import annotations

from pathlib import Path

from spec_check.core.config import SpecCheckSettings
from spec_check.core.schema import Confidence, Severity
from spec_check.rules import LargeDiffWithoutSpec

from tests.fixtures import make_context, make_diff


def _settings(threshold: int = 100, tmp: Path | None = None) -> SpecCheckSettings:
    return SpecCheckSettings(
        snapshot_root=(tmp or Path("/tmp/spec-check-test-large")) / "snap",
        large_diff_lines_threshold=threshold,
    )


def test_silent_when_diff_missing() -> None:
    findings = LargeDiffWithoutSpec().evaluate(make_context(parsed_diff=None))
    assert findings == []


def test_silent_when_spec_resolved() -> None:
    diff = make_diff(additions=500, deletions=500, files_changed=20)
    ctx = make_context(
        parsed_diff=diff,
        spec_resolution_method="ticket_key",
        settings=_settings(threshold=100),
    )
    assert LargeDiffWithoutSpec().evaluate(ctx) == []


def test_silent_when_diff_below_threshold() -> None:
    diff = make_diff(additions=50, deletions=20)
    ctx = make_context(
        parsed_diff=diff,
        spec_resolution_method="unresolved",
        settings=_settings(threshold=400),
    )
    assert LargeDiffWithoutSpec().evaluate(ctx) == []


def test_fires_unresolved_high_confidence(tmp_path: Path) -> None:
    diff = make_diff(additions=400, deletions=50, files_changed=12)
    ctx = make_context(
        parsed_diff=diff,
        spec_resolution_method="unresolved",
        settings=_settings(threshold=400, tmp=tmp_path),
    )
    findings = LargeDiffWithoutSpec().evaluate(ctx)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "large_diff_without_spec"
    assert f.severity is Severity.HIGH
    assert f.confidence is Confidence.HIGH
    assert "invest-criteria.md" in f.knowledge_refs
    assert f.evidence["total_lines"] == 450
    assert f.evidence["threshold"] == 400
    assert f.evidence["resolution_method"] == "unresolved"
    assert f.recommended_investigation.endswith("?")


def test_fires_ambiguous_medium_confidence(tmp_path: Path) -> None:
    diff = make_diff(additions=600, deletions=0)
    ctx = make_context(
        parsed_diff=diff,
        spec_resolution_method="ambiguous",
        settings=_settings(threshold=400, tmp=tmp_path),
    )
    findings = LargeDiffWithoutSpec().evaluate(ctx)
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.MEDIUM
