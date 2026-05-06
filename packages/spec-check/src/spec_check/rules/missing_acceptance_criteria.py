"""Rule: ``missing_acceptance_criteria``.

Distinct from ``missing_ac_section``. The named heading exists, but the
section under it has zero criteria — the spec exposes a placeholder, not a
contract. Without criteria the diff has nothing to be reviewed against;
this rule speaks at the spec level so the reviewer notices before reading
findings that depend on a populated criteria list.

Grounded in :doc:`notion-page-conventions <../knowledge/notion-page-conventions>`
(Convention 2: criteria are the leaf items under the heading; an empty
section breaks the contract just as surely as a missing heading).
"""

from __future__ import annotations

from spec_check.core.schema import Confidence, Finding, Severity
from spec_check.rules.base import Rule, RuleContext


class MissingAcceptanceCriteria:
    """Spec has the AC heading but no criteria items under it."""

    rule_id: str = "missing_acceptance_criteria"
    title: str = "Spec has an Acceptance Criteria section but no criteria"
    knowledge_refs: tuple[str, ...] = ("notion-page-conventions.md",)

    def evaluate(self, ctx: RuleContext) -> list[Finding]:
        if ctx.parsed_spec is None:
            return []
        if not ctx.parsed_spec.has_ac_section:
            return []  # missing_ac_section owns this signal
        if ctx.parsed_spec.criteria:
            return []

        return [
            Finding(
                rule_id=self.rule_id,
                title="Spec has an Acceptance Criteria section but no criteria",
                severity=Severity.HIGH,
                confidence=Confidence.HIGH,
                knowledge_refs=list(self.knowledge_refs),
                evidence={
                    "notion_page_id": ctx.parsed_spec.notion_page_id,
                    "spec_title": ctx.parsed_spec.title,
                    "spec_url": ctx.parsed_spec.url,
                },
                recommended_investigation=(
                    "The Acceptance Criteria heading is present but the "
                    "parser found no bullets, numbered items, checkboxes, "
                    "or Given/When/Then paragraphs underneath it. Have the "
                    "criteria not been written yet, or do they live in a "
                    "nested block the parser doesn't follow?"
                ),
            )
        ]


_: Rule = MissingAcceptanceCriteria()
