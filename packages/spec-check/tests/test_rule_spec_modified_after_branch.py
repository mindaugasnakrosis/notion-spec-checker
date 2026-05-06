"""Tests for spec_check.rules.spec_modified_after_branch."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from spec_check.core.config import SpecCheckSettings
from spec_check.core.schema import Confidence, Severity
from spec_check.rules import SpecModifiedAfterBranch

from tests.fixtures import make_context, make_spec


def _settings(threshold: int = 3600, tmp: Path | None = None) -> SpecCheckSettings:
    return SpecCheckSettings(
        snapshot_root=(tmp or Path("/tmp/spec-check-test-drift")) / "snap",
        spec_drift_high_confidence_seconds=threshold,
    )


_BRANCH_CREATED = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)


def test_silent_when_no_spec() -> None:
    findings = SpecModifiedAfterBranch().evaluate(
        make_context(parsed_spec=None, branch_created_at=_BRANCH_CREATED)
    )
    assert findings == []


def test_silent_when_no_branch_creation_time() -> None:
    spec = make_spec(last_edited_time=_BRANCH_CREATED + timedelta(days=1))
    findings = SpecModifiedAfterBranch().evaluate(
        make_context(parsed_spec=spec, branch_created_at=None)
    )
    assert findings == []


def test_silent_when_spec_edited_before_branch() -> None:
    spec = make_spec(last_edited_time=_BRANCH_CREATED - timedelta(hours=1))
    findings = SpecModifiedAfterBranch().evaluate(
        make_context(parsed_spec=spec, branch_created_at=_BRANCH_CREATED)
    )
    assert findings == []


def test_silent_when_edit_equals_branch_creation() -> None:
    spec = make_spec(last_edited_time=_BRANCH_CREATED)
    findings = SpecModifiedAfterBranch().evaluate(
        make_context(parsed_spec=spec, branch_created_at=_BRANCH_CREATED)
    )
    assert findings == []


def test_fires_high_confidence_when_gap_above_threshold(tmp_path: Path) -> None:
    spec = make_spec(last_edited_time=_BRANCH_CREATED + timedelta(hours=2))
    ctx = make_context(
        parsed_spec=spec,
        branch_created_at=_BRANCH_CREATED,
        settings=_settings(threshold=3600, tmp=tmp_path),
    )
    findings = SpecModifiedAfterBranch().evaluate(ctx)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "spec_modified_after_branch"
    assert f.severity is Severity.HIGH
    assert f.confidence is Confidence.HIGH
    assert "spec-drift.md" in f.knowledge_refs
    assert f.evidence["delta_seconds"] == 7200
    assert f.evidence["high_confidence_threshold_seconds"] == 3600
    assert f.evidence["branch"] == "feat/PROJ-1-login"
    assert f.recommended_investigation.endswith("?")


def test_fires_medium_confidence_when_gap_below_threshold(tmp_path: Path) -> None:
    spec = make_spec(last_edited_time=_BRANCH_CREATED + timedelta(minutes=10))
    ctx = make_context(
        parsed_spec=spec,
        branch_created_at=_BRANCH_CREATED,
        settings=_settings(threshold=3600, tmp=tmp_path),
    )
    findings = SpecModifiedAfterBranch().evaluate(ctx)
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.MEDIUM
    assert findings[0].evidence["delta_seconds"] == 600


def test_at_threshold_is_medium_confidence(tmp_path: Path) -> None:
    # Strict inequality on the High side: equal-to-threshold stays Medium.
    spec = make_spec(last_edited_time=_BRANCH_CREATED + timedelta(seconds=3600))
    ctx = make_context(
        parsed_spec=spec,
        branch_created_at=_BRANCH_CREATED,
        settings=_settings(threshold=3600, tmp=tmp_path),
    )
    findings = SpecModifiedAfterBranch().evaluate(ctx)
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.MEDIUM


def test_handles_naive_branch_timestamp_as_utc(tmp_path: Path) -> None:
    # If a future on-disk cache returns a naive datetime, the rule must
    # not crash on tz-aware vs tz-naive subtraction.
    naive_branch = datetime(2026, 5, 1, 12, 0, 0)
    spec = make_spec(last_edited_time=_BRANCH_CREATED + timedelta(hours=3))
    ctx = make_context(
        parsed_spec=spec,
        branch_created_at=naive_branch,
        settings=_settings(threshold=3600, tmp=tmp_path),
    )
    findings = SpecModifiedAfterBranch().evaluate(ctx)
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.HIGH
