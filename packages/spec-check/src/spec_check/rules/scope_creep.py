"""Rule: ``scope_creep``.

Fires when a *resolved* spec exists but the diff is much larger than the
spec's criteria count would justify. The signal is intentionally crude —
``(additions + deletions) > criteria_count * settings.scope_creep_lines_per_criterion``
— because anything subtler veers into pretending we understand the
semantics of the diff. A reviewer with this finding in hand asks: *is the
diff really doing what the spec asked for, or did it grow into adjacent
territory?*

Grounded in :doc:`invest-criteria <../knowledge/invest-criteria>`
(*S — Small* and *I — Independent*: a story that ships much more code than
its criteria justify has almost certainly absorbed work that belongs to a
different story).
"""

from __future__ import annotations

from spec_check.core.schema import Confidence, Finding, Severity
from spec_check.rules.base import Rule, RuleContext

# Resolution methods that mean "we believe a single spec genuinely backs
# this branch" — the only states in which scope_creep can speak.
# ``unresolved`` and ``ambiguous`` are owned by ``large_diff_without_spec``.
_RESOLVED_METHODS: frozenset[str] = frozenset({"override", "ticket_key", "trailer", "fuzzy"})


class ScopeCreep:
    """Diff size exceeds a per-criterion budget under a resolved spec."""

    rule_id: str = "scope_creep"
    title: str = "Diff exceeds the spec's criteria budget"
    knowledge_refs: tuple[str, ...] = ("invest-criteria.md",)

    def evaluate(self, ctx: RuleContext) -> list[Finding]:
        if ctx.parsed_spec is None or ctx.parsed_diff is None:
            return []
        if ctx.spec_resolution_method not in _RESOLVED_METHODS:
            return []
        criteria_count = len(ctx.parsed_spec.criteria)
        if criteria_count == 0:
            # ``missing_acceptance_criteria`` (or ``missing_ac_section``) owns
            # the "no criteria to compare against" signal.
            return []

        per_criterion_budget = ctx.settings.scope_creep_lines_per_criterion
        budget = criteria_count * per_criterion_budget
        total_lines = ctx.parsed_diff.additions + ctx.parsed_diff.deletions
        if total_lines <= budget:
            return []

        return [
            Finding(
                rule_id=self.rule_id,
                title="Diff exceeds the spec's criteria budget",
                severity=Severity.MEDIUM,
                confidence=Confidence.MEDIUM,
                knowledge_refs=list(self.knowledge_refs),
                evidence={
                    "notion_page_id": ctx.parsed_spec.notion_page_id,
                    "spec_url": ctx.parsed_spec.url,
                    "criteria_count": criteria_count,
                    "branch": ctx.parsed_diff.branch,
                    "additions": ctx.parsed_diff.additions,
                    "deletions": ctx.parsed_diff.deletions,
                    "total_lines": total_lines,
                    "files_changed": ctx.parsed_diff.files_changed,
                    "per_criterion_budget": per_criterion_budget,
                    "budget_total": budget,
                    "resolution_method": ctx.spec_resolution_method,
                },
                recommended_investigation=(
                    f"This diff touches {total_lines} lines under a spec with "
                    f"{criteria_count} criteria (budget {budget} lines at "
                    f"{per_criterion_budget} per criterion). Is the extra "
                    "work all in service of those criteria, or has the PR "
                    "absorbed adjacent work that belongs in its own spec?"
                ),
            )
        ]


_: Rule = ScopeCreep()
