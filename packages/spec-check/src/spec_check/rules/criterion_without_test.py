"""Rule: ``criterion_without_test``.

Fires when the spec lists acceptance criteria but the diff didn't touch
any test files. INVEST's *Testable* property treats writing the test as
part of *done*; a criterion the diff doesn't exercise is a Testable claim
with no test.

This is intentionally a coarse signal. We can't tell from the diff alone
*which* criterion a given test covers — so the rule speaks at the
diff/spec level, not at the per-criterion level. Per-criterion test
mapping is a future rule.

Grounded in :doc:`invest-criteria <../knowledge/invest-criteria>`.
"""

from __future__ import annotations

from spec_check.core.schema import Confidence, Finding, Severity
from spec_check.rules.base import Rule, RuleContext


class CriterionWithoutTest:
    """Spec has criteria but the diff modifies no test file."""

    rule_id: str = "criterion_without_test"
    title: str = "Spec has criteria but the diff has no test changes"
    knowledge_refs: tuple[str, ...] = ("invest-criteria.md",)

    def evaluate(self, ctx: RuleContext) -> list[Finding]:
        if ctx.parsed_spec is None or ctx.parsed_diff is None:
            return []
        if not ctx.parsed_spec.criteria:
            return []
        if ctx.test_files_touched:
            return []
        # If the diff is *purely* a docs/spec/config change with no production
        # source either, we can't know whether tests should exist. Stay quiet.
        if ctx.parsed_diff.additions == 0 and ctx.parsed_diff.deletions == 0:
            return []

        return [
            Finding(
                rule_id=self.rule_id,
                title="Spec has criteria but the diff has no test changes",
                severity=Severity.MEDIUM,
                confidence=Confidence.MEDIUM,
                knowledge_refs=list(self.knowledge_refs),
                evidence={
                    "notion_page_id": ctx.parsed_spec.notion_page_id,
                    "spec_url": ctx.parsed_spec.url,
                    "criteria_count": len(ctx.parsed_spec.criteria),
                    "branch": ctx.parsed_diff.branch,
                    "files_changed": ctx.parsed_diff.files_changed,
                    "test_files_touched": list(ctx.test_files_touched),
                },
                recommended_investigation=(
                    f"The spec lists {len(ctx.parsed_spec.criteria)} acceptance "
                    "criteria but the diff modifies no test file. Are the "
                    "criteria covered by existing tests this PR didn't need "
                    "to touch, or is there test work missing from this PR?"
                ),
            )
        ]


_: Rule = CriterionWithoutTest()
