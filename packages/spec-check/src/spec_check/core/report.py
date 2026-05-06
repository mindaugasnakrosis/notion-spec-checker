"""Markdown renderer for ``report.md``.

Reads a :class:`FindingsDocument` plus the manifest and writes a
human-readable review to ``report.md`` in the check directory. The render
is intentionally flat: a header with run metadata, a one-line summary, a
section per severity with one block per finding, and a knowledge-corpus
footer listing every cited document.

No HTML, no JavaScript, no fancy tables — the report is meant to be
pasted into a PR comment, viewed in a terminal, and diffed across runs.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml

from spec_check.core.schema import (
    CheckManifest,
    Confidence,
    Finding,
    FindingsDocument,
    Severity,
)
from spec_check.core.snapshot import CheckPaths

_SEVERITY_HEADINGS: tuple[Severity, ...] = (
    Severity.CRITICAL,
    Severity.HIGH,
    Severity.MEDIUM,
    Severity.LOW,
    Severity.INFO,
)


def render_report(
    *,
    manifest: CheckManifest,
    document: FindingsDocument,
) -> str:
    """Render a :class:`FindingsDocument` to a markdown string.

    Pure: takes only data, returns text. The CLI layer is responsible for
    writing the result to disk.
    """
    lines: list[str] = []
    lines.append(f"# spec-check report — {manifest.branch}")
    lines.append("")
    lines.extend(_header_block(manifest, document))
    lines.append("")
    lines.append(_summary_line(document.findings))
    lines.append("")

    for severity in _SEVERITY_HEADINGS:
        bucket = [f for f in document.findings if f.severity is severity]
        if not bucket:
            continue
        lines.append(f"## {severity.value} ({len(bucket)})")
        lines.append("")
        for finding in bucket:
            lines.extend(_render_finding(finding))
            lines.append("")

    citations = _collect_citations(document.findings)
    if citations:
        lines.append("## Knowledge corpus citations")
        lines.append("")
        for ref in citations:
            lines.append(f"- `{ref}`")
        lines.append("")

    lines.append("---")
    lines.append(
        "_spec-check is read-only on git AND on Notion. "
        "It surfaces questions for the human; it does not block merges._"
    )
    return "\n".join(lines).rstrip() + "\n"


def write_report(paths: CheckPaths, body: str) -> Path:
    """Write the rendered markdown to ``report.md`` in the check directory."""
    paths.report.write_text(body)
    return paths.report


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _header_block(manifest: CheckManifest, document: FindingsDocument) -> list[str]:
    spec_url = manifest.resolved_spec_url or "(unresolved)"
    return [
        f"- **Branch**: `{manifest.branch}`",
        f"- **Base ref**: `{manifest.base_ref}`",
        f"- **Head SHA**: `{manifest.head_sha}`",
        f"- **Spec**: {spec_url}",
        f"- **Resolution method**: `{manifest.resolution_method or 'unresolved'}`",
        f"- **Check id**: `{manifest.check_id}`",
        f"- **Run at**: `{manifest.created_at.isoformat()}`",
        f"- **spec-check version**: `{document.spec_check_version}`",
    ]


def _summary_line(findings: list[Finding]) -> str:
    if not findings:
        return "_No findings._"
    counts = Counter(f.severity for f in findings)
    parts = [
        f"{counts[severity]} {severity.value}"
        for severity in _SEVERITY_HEADINGS
        if counts.get(severity)
    ]
    return f"**{len(findings)} finding(s)**: " + ", ".join(parts) + "."


def _render_finding(f: Finding) -> list[str]:
    out: list[str] = []
    out.append(f"### {f.title}")
    out.append("")
    out.append(
        f"- **Rule**: `{f.rule_id}` &nbsp;·&nbsp; "
        f"**Severity**: {f.severity.value} &nbsp;·&nbsp; "
        f"**Confidence**: {f.confidence.value}"
    )
    if f.knowledge_refs:
        refs = ", ".join(f"`{r}`" for r in f.knowledge_refs)
        out.append(f"- **Knowledge**: {refs}")
    out.append("")
    out.append("**Question:** " + f.recommended_investigation)
    if f.evidence:
        out.append("")
        out.append("<details><summary>Evidence</summary>")
        out.append("")
        out.append("```yaml")
        out.extend(_yaml_block(f.evidence).splitlines())
        out.append("```")
        out.append("")
        out.append("</details>")
    return out


def _yaml_block(evidence: dict) -> str:
    """Render evidence as YAML so pasted reports stay diffable."""
    return yaml.safe_dump(evidence, sort_keys=True, allow_unicode=True).rstrip()


def _collect_citations(findings: list[Finding]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for f in findings:
        for ref in f.knowledge_refs:
            if ref not in seen:
                seen.add(ref)
                ordered.append(ref)
    return ordered


def severity_summary(findings: list[Finding]) -> dict[str, int]:
    """Public helper for callers that want machine-readable counts (e.g.
    a CI step reporting *N* High findings without parsing markdown).
    """
    counts: dict[str, int] = {s.value: 0 for s in _SEVERITY_HEADINGS}
    for f in findings:
        counts[f.severity.value] = counts.get(f.severity.value, 0) + 1
    return counts


# Confidence is currently unused at the summary level but exported here
# so the CLI step (16) doesn't have to re-import the enum just to format
# a one-liner.
__all__ = [
    "Confidence",
    "render_report",
    "severity_summary",
    "write_report",
]
