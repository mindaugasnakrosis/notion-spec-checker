"""Rule registry and dispatcher.

``analyse`` reads a check directory (manifest, parsed spec, parsed diff,
branch meta), constructs a :class:`RuleContext`, runs every registered
rule, and writes the resulting :class:`FindingsDocument` to
``findings.yaml``. It does not touch git or Notion — by the time analyse
runs, all read-only side effects have already happened during ``pull``.

Rules are registered as instances in :data:`RULES`. The order of the
tuple is the order findings appear in the report when severity and
confidence tie. Rules added in later steps slot into the tuple
explicitly; there is no auto-discovery (auto-discovery would let a typo
silently disable a rule, which is the worst possible failure mode for a
review tool).
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from spec_check import __version__
from spec_check.core.config import SpecCheckSettings
from spec_check.core.schema import (
    BranchMetaSnapshot,
    CheckManifest,
    Confidence,
    Finding,
    FindingsDocument,
    ParsedDiff,
    ParsedSpec,
    Severity,
)
from spec_check.core.snapshot import CheckPaths, read_manifest
from spec_check.rules import (
    AmbiguousCriterion,
    CriterionWithoutTest,
    LargeDiffWithoutSpec,
    MissingAcceptanceCriteria,
    MissingAcSection,
    MultipleSpecsReferenced,
    Rule,
    RuleContext,
    ScopeCreep,
    SpecModifiedAfterBranch,
    UntestableCriterion,
)

# Order matters: it is the tie-break order in the report when severity and
# confidence are equal. Spec-shape problems first (the reviewer needs to know
# the spec is intact before reading anything else), then size/scope, then
# AC-quality, then drift.
RULES: tuple[Rule, ...] = (
    MissingAcSection(),
    MissingAcceptanceCriteria(),
    LargeDiffWithoutSpec(),
    ScopeCreep(),
    MultipleSpecsReferenced(),
    CriterionWithoutTest(),
    AmbiguousCriterion(),
    UntestableCriterion(),
    SpecModifiedAfterBranch(),
)


_SEVERITY_ORDER: dict[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}
_CONFIDENCE_ORDER: dict[Confidence, int] = {
    Confidence.HIGH: 0,
    Confidence.MEDIUM: 1,
    Confidence.LOW: 2,
}


def sort_findings(findings: list[Finding], rule_order: tuple[str, ...]) -> list[Finding]:
    """Stable order: severity → confidence → registry order → rule_id.

    The registry-order tier exists so that rules listed earlier in
    :data:`RULES` (the "spec is broken" rules) sort above same-severity
    rules listed later (the "spec is fine but large" rules).
    """
    rule_index = {rid: i for i, rid in enumerate(rule_order)}
    return sorted(
        findings,
        key=lambda f: (
            _SEVERITY_ORDER.get(f.severity, 99),
            _CONFIDENCE_ORDER.get(f.confidence, 99),
            rule_index.get(f.rule_id, len(rule_index)),
            f.rule_id,
        ),
    )


def _load_parsed_spec(paths: CheckPaths) -> ParsedSpec | None:
    """Load ``spec/parsed.yaml`` if it exists. ``None`` is a valid state —
    the spec collector or parser may have failed during ``pull``.
    """
    if not paths.spec_parsed.exists():
        return None
    with paths.spec_parsed.open() as fh:
        data = yaml.safe_load(fh)
    if not data:
        return None
    return ParsedSpec.model_validate(data)


def _load_parsed_diff(paths: CheckPaths) -> ParsedDiff | None:
    """Load the ``base_ref..HEAD`` diff (``diff/recent_commits.json``). The
    other two diffs (staged/unstaged) describe the working tree, not the
    branch as a whole; rules want the branch view.
    """
    if not paths.diff_recent_commits.exists():
        return None
    with paths.diff_recent_commits.open() as fh:
        data = json.load(fh)
    return ParsedDiff.model_validate(data)


def _load_branch_meta(paths: CheckPaths) -> BranchMetaSnapshot | None:
    if not paths.branch_meta.exists():
        return None
    with paths.branch_meta.open() as fh:
        data = yaml.safe_load(fh)
    if not data:
        return None
    return BranchMetaSnapshot.model_validate(data)


def build_rule_context(
    *,
    manifest: CheckManifest,
    parsed_spec: ParsedSpec | None,
    parsed_diff: ParsedDiff | None,
    branch_meta: BranchMetaSnapshot | None,
    settings: SpecCheckSettings,
) -> RuleContext:
    """Assemble a :class:`RuleContext` from the loaded artefacts."""
    return RuleContext(
        parsed_spec=parsed_spec,
        parsed_diff=parsed_diff,
        manifest=manifest,
        settings=settings,
        spec_resolution_method=manifest.resolution_method or "unresolved",
        test_files_touched=list(parsed_diff.test_files_touched) if parsed_diff else [],
        referenced_tickets=tuple(branch_meta.referenced_tickets) if branch_meta else (),
        branch_created_at=branch_meta.branch_created_at if branch_meta else None,
    )


def run_rules(ctx: RuleContext, rules: tuple[Rule, ...] = RULES) -> list[Finding]:
    """Run every rule against ``ctx`` and return the merged findings list.

    A rule that raises is *not* allowed to kill the run. We capture the
    exception as an Info finding citing the rule and keep going — the
    point of the tool is to surface signal, and a buggy rule should not
    swallow the rest of the report.
    """
    out: list[Finding] = []
    rule_ids = tuple(r.rule_id for r in rules)
    for rule in rules:
        try:
            out.extend(rule.evaluate(ctx))
        except Exception as exc:  # noqa: BLE001 — defensive at the dispatcher boundary
            out.append(
                Finding(
                    rule_id="rule_runtime_error",
                    title=f"Rule {rule.rule_id!r} raised at evaluate-time",
                    severity=Severity.INFO,
                    confidence=Confidence.LOW,
                    knowledge_refs=[],
                    evidence={"rule_id": rule.rule_id, "error": str(exc)},
                    recommended_investigation=(
                        f"Rule {rule.rule_id!r} raised {type(exc).__name__}: {exc}. "
                        "Is this a bug in the rule, or has the on-disk schema "
                        "drifted from what the rule expects?"
                    ),
                )
            )
    return sort_findings(out, rule_ids)


def analyse(
    *,
    paths: CheckPaths,
    settings: SpecCheckSettings,
    rules: tuple[Rule, ...] = RULES,
) -> FindingsDocument:
    """Load the check directory's artefacts, run every rule, and write
    ``findings.yaml``. Returns the in-memory document the caller can
    render or print.
    """
    manifest = read_manifest(paths)
    parsed_spec = _load_parsed_spec(paths)
    parsed_diff = _load_parsed_diff(paths)
    branch_meta = _load_branch_meta(paths)

    ctx = build_rule_context(
        manifest=manifest,
        parsed_spec=parsed_spec,
        parsed_diff=parsed_diff,
        branch_meta=branch_meta,
        settings=settings,
    )

    findings = run_rules(ctx, rules)
    document = FindingsDocument(
        check_id=manifest.check_id,
        spec_check_version=__version__,
        findings=findings,
    )
    write_findings(paths, document)
    return document


def write_findings(paths: CheckPaths, document: FindingsDocument) -> Path:
    """Serialise a :class:`FindingsDocument` to ``findings.yaml``."""
    payload = document.model_dump(mode="json")
    with paths.findings.open("w") as fh:
        yaml.safe_dump(payload, fh, sort_keys=False)
    return paths.findings


def read_findings(paths: CheckPaths) -> FindingsDocument:
    if not paths.findings.exists():
        raise FileNotFoundError(f"findings.yaml missing at {paths.findings}")
    with paths.findings.open() as fh:
        data = yaml.safe_load(fh) or {}
    return FindingsDocument.model_validate(data)
