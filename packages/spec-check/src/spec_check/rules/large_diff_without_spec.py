"""Rule: ``large_diff_without_spec``.

Fires when a diff above ``settings.large_diff_lines_threshold`` lands
without a resolved spec. INVEST's *Small* property says a story is at
most a few person-weeks of work; a sizable diff with no story behind it
has almost certainly bundled multiple stories and lost the ability to be
estimated, negotiated, or rolled back independently.

Grounded in :doc:`invest-criteria <../knowledge/invest-criteria>`.
"""

from __future__ import annotations

from spec_check.core.schema import Confidence, Finding, Severity
from spec_check.rules.base import Rule, RuleContext

_RESOLVED_METHODS: frozenset[str] = frozenset(
    {"override", "ticket_key", "trailer", "fuzzy"}
)


class LargeDiffWithoutSpec:
    """Diff is large, no spec resolved."""

    rule_id: str = "large_diff_without_spec"
    title: str = "Large diff with no resolved spec"
    knowledge_refs: tuple[str, ...] = ("invest-criteria.md",)

    def evaluate(self, ctx: RuleContext) -> list[Finding]:
        if ctx.parsed_diff is None:
            return []
        if ctx.spec_resolution_method in _RESOLVED_METHODS:
            return []

        threshold = ctx.settings.large_diff_lines_threshold
        total_lines = ctx.parsed_diff.additions + ctx.parsed_diff.deletions
        if total_lines < threshold:
            return []

        # Confidence is High when we are certain there is no spec, Medium
        # when the resolver gave back an ambiguous answer (the human may
        # still be able to point at the right page).
        if ctx.spec_resolution_method == "ambiguous":
            confidence = Confidence.MEDIUM
        else:
            confidence = Confidence.HIGH

        return [
            Finding(
                rule_id=self.rule_id,
                title="Large diff with no resolved spec",
                severity=Severity.HIGH,
                confidence=confidence,
                knowledge_refs=list(self.knowledge_refs),
                evidence={
                    "branch": ctx.parsed_diff.branch,
                    "additions": ctx.parsed_diff.additions,
                    "deletions": ctx.parsed_diff.deletions,
                    "total_lines": total_lines,
                    "files_changed": ctx.parsed_diff.files_changed,
                    "threshold": threshold,
                    "resolution_method": ctx.spec_resolution_method,
                },
                recommended_investigation=(
                    f"This diff touches {total_lines} lines (threshold "
                    f"{threshold}) with resolution_method "
                    f"{ctx.spec_resolution_method!r}. Is the work covered by "
                    "a spec the resolver couldn't find — and if not, should "
                    "this PR be split into smaller stories that each have "
                    "their own spec?"
                ),
            )
        ]


_: Rule = LargeDiffWithoutSpec()
