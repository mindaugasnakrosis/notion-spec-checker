"""Rule: ``missing_ac_section``.

Fires when the resolved spec has no recognised "Acceptance Criteria"
heading. Without that heading the page is, for review purposes, a spec
without criteria — there is nothing for the review to compare the diff
against.

Grounded in :doc:`notion-page-conventions <../knowledge/notion-page-conventions>`.
"""

from __future__ import annotations

from spec_check.core.schema import Confidence, Finding, Severity
from spec_check.rules.base import Rule, RuleContext


class MissingAcSection:
    """The resolved spec has no Acceptance Criteria heading."""

    rule_id: str = "missing_ac_section"
    title: str = "Spec has no Acceptance Criteria section"
    knowledge_refs: tuple[str, ...] = ("notion-page-conventions.md",)

    def evaluate(self, ctx: RuleContext) -> list[Finding]:
        # No spec at all → other rules (large_diff_without_spec) own the
        # signal. This rule only speaks when we *have* a spec to inspect.
        if ctx.parsed_spec is None:
            return []
        if ctx.parsed_spec.has_ac_section:
            return []

        return [
            Finding(
                rule_id=self.rule_id,
                title="Spec has no Acceptance Criteria section",
                severity=Severity.HIGH,
                confidence=Confidence.HIGH,
                knowledge_refs=list(self.knowledge_refs),
                evidence={
                    "notion_page_id": ctx.parsed_spec.notion_page_id,
                    "spec_title": ctx.parsed_spec.title,
                    "spec_url": ctx.parsed_spec.url,
                    "criteria_found": len(ctx.parsed_spec.criteria),
                },
                recommended_investigation=(
                    "Is there an Acceptance Criteria section on this page that "
                    "uses a different heading the parser doesn't recognise, or "
                    "have the criteria not been written yet?"
                ),
            )
        ]


_: Rule = MissingAcSection()  # static check that the class implements Rule
