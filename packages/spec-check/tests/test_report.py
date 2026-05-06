"""Tests for spec_check.core.report — the markdown renderer."""

from __future__ import annotations

from pathlib import Path

from spec_check.core.report import (
    render_report,
    severity_summary,
    write_report,
)
from spec_check.core.schema import (
    Confidence,
    Finding,
    FindingsDocument,
    Severity,
)
from spec_check.core.snapshot import paths_for

from tests.fixtures import make_manifest


def _f(rule_id: str, severity: Severity, confidence: Confidence, **extra: object) -> Finding:
    return Finding(
        rule_id=rule_id,
        title=extra.get("title", rule_id),
        severity=severity,
        confidence=confidence,
        knowledge_refs=extra.get("knowledge_refs", ["x.md"]) if severity is not Severity.INFO else [],
        evidence=extra.get("evidence", {}),
        recommended_investigation=extra.get("recommended_investigation", "Why?"),
    )


# ---------------------------------------------------------------------------
# render_report
# ---------------------------------------------------------------------------


def test_render_no_findings() -> None:
    document = FindingsDocument(
        check_id="2026-05-04T12-00-00Z-aaaaaa",
        spec_check_version="0.0.0",
        findings=[],
    )
    body = render_report(manifest=make_manifest(), document=document)
    assert body.startswith("# spec-check report")
    assert "_No findings._" in body
    assert "## Knowledge corpus citations" not in body
    assert body.endswith("\n")


def test_render_with_findings_groups_by_severity() -> None:
    document = FindingsDocument(
        check_id="cid",
        spec_check_version="0.0.0",
        findings=[
            _f("a_high", Severity.HIGH, Confidence.HIGH, knowledge_refs=["k1.md"]),
            _f("b_high", Severity.HIGH, Confidence.MEDIUM, knowledge_refs=["k2.md"]),
            _f("c_med", Severity.MEDIUM, Confidence.HIGH, knowledge_refs=["k1.md"]),
        ],
    )
    body = render_report(manifest=make_manifest(), document=document)
    assert "## High (2)" in body
    assert "## Medium (1)" in body
    # Citations appear once each, in first-seen order.
    citations_section = body.split("## Knowledge corpus citations")[1]
    assert citations_section.index("`k1.md`") < citations_section.index("`k2.md`")


def test_render_includes_evidence_block_and_question() -> None:
    document = FindingsDocument(
        check_id="cid",
        spec_check_version="0.0.0",
        findings=[
            _f(
                "demo",
                Severity.HIGH,
                Confidence.HIGH,
                evidence={"branch": "feat/x", "lines": 42},
                recommended_investigation="Is this right?",
            )
        ],
    )
    body = render_report(manifest=make_manifest(), document=document)
    assert "**Question:** Is this right?" in body
    assert "<details><summary>Evidence</summary>" in body
    assert "branch: feat/x" in body
    assert "lines: 42" in body


def test_render_summary_line_counts_each_severity() -> None:
    document = FindingsDocument(
        check_id="cid",
        spec_check_version="0.0.0",
        findings=[
            _f("h1", Severity.HIGH, Confidence.HIGH),
            _f("h2", Severity.HIGH, Confidence.HIGH),
            _f("m1", Severity.MEDIUM, Confidence.HIGH),
        ],
    )
    body = render_report(manifest=make_manifest(), document=document)
    assert "**3 finding(s)**: 2 High, 1 Medium." in body


def test_render_includes_manifest_metadata() -> None:
    manifest = make_manifest(
        branch="feat/PROJ-1-login",
        head_sha="deadbeef",
        resolution_method="ticket_key",
    )
    document = FindingsDocument(check_id=manifest.check_id, spec_check_version="9.9.9", findings=[])
    body = render_report(manifest=manifest, document=document)
    assert "feat/PROJ-1-login" in body
    assert "deadbeef" in body
    assert "ticket_key" in body
    assert "9.9.9" in body


def test_render_includes_read_only_footer() -> None:
    document = FindingsDocument(check_id="cid", spec_check_version="0.0.0", findings=[])
    body = render_report(manifest=make_manifest(), document=document)
    assert "read-only on git AND on Notion" in body


# ---------------------------------------------------------------------------
# severity_summary
# ---------------------------------------------------------------------------


def test_severity_summary_counts_all_buckets() -> None:
    findings = [
        _f("c1", Severity.CRITICAL, Confidence.HIGH),
        _f("h1", Severity.HIGH, Confidence.HIGH),
        _f("h2", Severity.HIGH, Confidence.HIGH),
        _f("i1", Severity.INFO, Confidence.LOW),
    ]
    counts = severity_summary(findings)
    assert counts["Critical"] == 1
    assert counts["High"] == 2
    assert counts["Medium"] == 0
    assert counts["Low"] == 0
    assert counts["Info"] == 1


# ---------------------------------------------------------------------------
# write_report
# ---------------------------------------------------------------------------


def test_write_report_persists_to_check_dir(tmp_path: Path) -> None:
    snap = tmp_path / "snap"
    snap.mkdir()
    cid = "2026-05-04T12-00-00Z-eeeeee"
    paths = paths_for(snap, cid)
    paths.root.mkdir(parents=True)
    body = "# hello\n"
    written = write_report(paths, body)
    assert written.read_text() == body
    assert written == paths.report
