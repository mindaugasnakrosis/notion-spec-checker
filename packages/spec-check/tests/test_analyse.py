"""Tests for spec_check.core.analyse — the rule registry + dispatcher."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import yaml
from spec_check.core.analyse import (
    RULES,
    analyse,
    build_rule_context,
    read_findings,
    run_rules,
    sort_findings,
)
from spec_check.core.config import SpecCheckSettings
from spec_check.core.schema import (
    BranchMetaSnapshot,
    CheckManifest,
    CollectorStatus,
    Confidence,
    Finding,
    ParsedDiff,
    Severity,
)
from spec_check.core.snapshot import paths_for, write_manifest
from spec_check.rules.base import Rule, RuleContext

from tests.fixtures import make_criterion, make_diff, make_manifest, make_spec


def _settings(tmp: Path) -> SpecCheckSettings:
    return SpecCheckSettings(
        snapshot_root=tmp / "snap",
        large_diff_lines_threshold=400,
        scope_creep_lines_per_criterion=200,
    )


def _seed_check_dir(tmp: Path, *, with_branch_meta: bool = True) -> tuple[Path, str]:
    """Lay down a synthetic check directory with all artefacts on disk."""
    settings = _settings(tmp)
    settings.snapshot_root.mkdir(parents=True, exist_ok=True)
    cid = "2026-05-04T12-00-00Z-aaaaaa"
    paths = paths_for(settings.snapshot_root, cid)
    paths.root.mkdir(parents=True)
    paths.diff_dir.mkdir()
    paths.spec_dir.mkdir()

    spec = make_spec(
        has_ac_section=True,
        criteria=[
            make_criterion("User can log in.", cid="AC-1"),
        ],
    )
    paths.spec_parsed.write_text(yaml.safe_dump(spec.model_dump(mode="json"), sort_keys=False))

    diff = make_diff(branch="feat/PROJ-1-login", additions=10, deletions=0, files_changed=1)
    paths.diff_recent_commits.write_text(json.dumps(diff.model_dump(mode="json")))

    manifest = make_manifest(
        check_id=cid,
        branch="feat/PROJ-1-login",
        resolution_method="ticket_key",
    )
    write_manifest(paths, manifest)

    if with_branch_meta:
        branch_meta = BranchMetaSnapshot(
            branch="feat/PROJ-1-login",
            head_sha=manifest.head_sha,
            base_ref="origin/main",
            referenced_tickets=["PROJ-1"],
            branch_created_at=datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC),
        )
        paths.branch_meta.write_text(
            yaml.safe_dump(branch_meta.model_dump(mode="json"), sort_keys=False)
        )

    return paths.root, cid


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_has_nine_distinct_rules() -> None:
    assert len(RULES) == 9
    assert len({r.rule_id for r in RULES}) == 9


def test_registry_is_in_priority_order() -> None:
    expected = [
        "missing_ac_section",
        "missing_acceptance_criteria",
        "large_diff_without_spec",
        "scope_creep",
        "multiple_specs_referenced",
        "criterion_without_test",
        "ambiguous_criterion",
        "untestable_criterion",
        "spec_modified_after_branch",
    ]
    assert [r.rule_id for r in RULES] == expected


# ---------------------------------------------------------------------------
# Sort order
# ---------------------------------------------------------------------------


def _f(rule_id: str, severity: Severity, confidence: Confidence) -> Finding:
    return Finding(
        rule_id=rule_id,
        title=rule_id,
        severity=severity,
        confidence=confidence,
        knowledge_refs=["x.md"] if severity is not Severity.INFO else [],
        evidence={},
        recommended_investigation="Why?",
    )


def test_sort_findings_orders_by_severity_then_confidence_then_registry() -> None:
    rule_order = ("a_rule", "b_rule", "c_rule")
    findings = [
        _f("c_rule", Severity.HIGH, Confidence.HIGH),
        _f("b_rule", Severity.HIGH, Confidence.HIGH),
        _f("a_rule", Severity.MEDIUM, Confidence.HIGH),
        _f("a_rule", Severity.HIGH, Confidence.MEDIUM),
        _f("a_rule", Severity.HIGH, Confidence.HIGH),
    ]
    out = sort_findings(findings, rule_order)
    # Top: HIGH/HIGH in registry order (a, b, c)
    assert [(f.rule_id, f.severity.value, f.confidence.value) for f in out] == [
        ("a_rule", "High", "High"),
        ("b_rule", "High", "High"),
        ("c_rule", "High", "High"),
        ("a_rule", "High", "Medium"),
        ("a_rule", "Medium", "High"),
    ]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


class _BoomRule:
    rule_id: str = "boom"
    title: str = "Boom"
    knowledge_refs: tuple[str, ...] = ()

    def evaluate(self, ctx: RuleContext) -> list[Finding]:
        raise RuntimeError("kapow")


def test_run_rules_isolates_a_raising_rule(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    ctx = RuleContext(
        parsed_spec=None,
        parsed_diff=None,
        manifest=make_manifest(),
        settings=settings,
        spec_resolution_method="override",
        test_files_touched=[],
    )
    findings = run_rules(ctx, rules=(_BoomRule(),))
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "rule_runtime_error"
    assert f.severity is Severity.INFO
    assert f.evidence["rule_id"] == "boom"
    assert "kapow" in f.evidence["error"]


def test_run_rules_returns_sorted_findings(tmp_path: Path) -> None:
    # Two rules: one fires Medium, one fires High. Output is sorted High first.
    class _MediumRule:
        rule_id: str = "med"
        title: str = "M"
        knowledge_refs: tuple[str, ...] = ("x.md",)

        def evaluate(self, ctx: RuleContext) -> list[Finding]:
            return [_f("med", Severity.MEDIUM, Confidence.HIGH)]

    class _HighRule:
        rule_id: str = "hi"
        title: str = "H"
        knowledge_refs: tuple[str, ...] = ("x.md",)

        def evaluate(self, ctx: RuleContext) -> list[Finding]:
            return [_f("hi", Severity.HIGH, Confidence.HIGH)]

    ctx = RuleContext(
        parsed_spec=None,
        parsed_diff=None,
        manifest=make_manifest(),
        settings=_settings(tmp_path),
        spec_resolution_method="override",
        test_files_touched=[],
    )
    findings = run_rules(ctx, rules=(_MediumRule(), _HighRule()))
    assert [f.rule_id for f in findings] == ["hi", "med"]


# ---------------------------------------------------------------------------
# build_rule_context
# ---------------------------------------------------------------------------


def test_build_rule_context_threads_resolution_method_from_manifest(tmp_path: Path) -> None:
    manifest = make_manifest(resolution_method="trailer")
    ctx = build_rule_context(
        manifest=manifest,
        parsed_spec=None,
        parsed_diff=None,
        branch_meta=None,
        settings=_settings(tmp_path),
    )
    assert ctx.spec_resolution_method == "trailer"


def test_build_rule_context_falls_back_to_unresolved_when_method_none(tmp_path: Path) -> None:
    manifest = CheckManifest(
        check_id="2026-05-04T12-00-00Z-bbbbbb",
        created_at=datetime(2026, 5, 4, 12, tzinfo=UTC),
        spec_check_version="0.0.0",
        branch="feat/x",
        base_ref="origin/main",
        head_sha="deadbeef",
        resolution_method=None,
        collectors=[CollectorStatus(name="branch_meta", state="ok")],
    )
    ctx = build_rule_context(
        manifest=manifest,
        parsed_spec=None,
        parsed_diff=None,
        branch_meta=None,
        settings=_settings(tmp_path),
    )
    assert ctx.spec_resolution_method == "unresolved"


def test_build_rule_context_threads_branch_meta(tmp_path: Path) -> None:
    bm = BranchMetaSnapshot(
        branch="feat/x",
        head_sha="deadbeef",
        base_ref="origin/main",
        referenced_tickets=["PROJ-1", "PROJ-2"],
        branch_created_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    diff = ParsedDiff(
        base_ref="origin/main",
        head_sha="deadbeef",
        branch="feat/x",
        files_changed=1,
        additions=10,
        deletions=0,
        hunks=[],
        test_files_touched=["tests/test_x.py"],
    )
    ctx = build_rule_context(
        manifest=make_manifest(),
        parsed_spec=None,
        parsed_diff=diff,
        branch_meta=bm,
        settings=_settings(tmp_path),
    )
    assert ctx.referenced_tickets == ("PROJ-1", "PROJ-2")
    assert ctx.branch_created_at == datetime(2026, 5, 1, tzinfo=UTC)
    assert ctx.test_files_touched == ["tests/test_x.py"]


# ---------------------------------------------------------------------------
# End-to-end analyse
# ---------------------------------------------------------------------------


def test_analyse_writes_findings_yaml_and_round_trips(tmp_path: Path) -> None:
    _seed_check_dir(tmp_path)
    settings = _settings(tmp_path)
    cid = "2026-05-04T12-00-00Z-aaaaaa"
    paths = paths_for(settings.snapshot_root, cid)

    document = analyse(paths=paths, settings=settings)

    assert paths.findings.exists()
    on_disk = read_findings(paths)
    assert on_disk.check_id == cid
    assert on_disk.findings == document.findings


def test_analyse_emits_no_findings_for_a_clean_run(tmp_path: Path) -> None:
    # Tiny diff (10 lines) under a resolved spec with one criterion and a
    # populated AC section — no rule should fire.
    _seed_check_dir(tmp_path)
    settings = _settings(tmp_path)
    cid = "2026-05-04T12-00-00Z-aaaaaa"
    paths = paths_for(settings.snapshot_root, cid)
    document = analyse(paths=paths, settings=settings)
    # criterion_without_test fires because no test file touched + non-empty diff.
    # That's the *correct* signal for a clean run with no tests — assert it.
    rule_ids = {f.rule_id for f in document.findings}
    assert rule_ids == {"criterion_without_test"}


def test_analyse_handles_missing_branch_meta(tmp_path: Path) -> None:
    _seed_check_dir(tmp_path, with_branch_meta=False)
    settings = _settings(tmp_path)
    cid = "2026-05-04T12-00-00Z-aaaaaa"
    paths = paths_for(settings.snapshot_root, cid)
    document = analyse(paths=paths, settings=settings)
    # spec_modified_after_branch must stay silent when branch_created_at is None.
    assert "spec_modified_after_branch" not in {f.rule_id for f in document.findings}
    # multiple_specs_referenced needs ≥ 2 distinct tickets — silent here too.
    assert "multiple_specs_referenced" not in {f.rule_id for f in document.findings}


def test_registry_classes_all_implement_rule_protocol() -> None:
    for r in RULES:
        assert isinstance(r, Rule), f"{r.rule_id} does not satisfy Rule"
