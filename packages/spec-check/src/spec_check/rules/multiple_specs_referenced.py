"""Rule: ``multiple_specs_referenced``.

Fires when the head commit message names two or more distinct ticket keys
(via ``Refs:`` trailers or ``[PROJ-123]`` brackets). A branch may still be
implementing a single coherent spec — the second ticket might be a
follow-up reference or a related-work note — but spec-check resolves
exactly one Notion page per branch, so any second ticket is content that
won't be reviewed against its spec on this run.

Grounded in :doc:`notion-page-conventions <../knowledge/notion-page-conventions>`
(Convention 3: one spec per branch; multi-spec branches should be reviewed
once per spec via ``--spec``).
"""

from __future__ import annotations

from spec_check.core.schema import Confidence, Finding, Severity
from spec_check.rules.base import Rule, RuleContext


class MultipleSpecsReferenced:
    """Head commit references two or more distinct ticket keys."""

    rule_id: str = "multiple_specs_referenced"
    title: str = "Head commit references more than one ticket"
    knowledge_refs: tuple[str, ...] = ("notion-page-conventions.md",)

    def evaluate(self, ctx: RuleContext) -> list[Finding]:
        # Distinct, order-preserving.
        seen: set[str] = set()
        unique: list[str] = []
        for ticket in ctx.referenced_tickets:
            if ticket and ticket not in seen:
                seen.add(ticket)
                unique.append(ticket)
        if len(unique) < 2:
            return []

        return [
            Finding(
                rule_id=self.rule_id,
                title="Head commit references more than one ticket",
                severity=Severity.MEDIUM,
                confidence=Confidence.HIGH,
                knowledge_refs=list(self.knowledge_refs),
                evidence={
                    "branch": ctx.manifest.branch,
                    "head_sha": ctx.manifest.head_sha,
                    "referenced_tickets": unique,
                    "resolved_spec_id": ctx.manifest.resolved_spec_id,
                    "resolution_method": ctx.spec_resolution_method,
                },
                recommended_investigation=(
                    f"The head commit names {len(unique)} ticket keys "
                    f"({', '.join(unique)}). spec-check reviewed against one "
                    "spec on this run; do the other tickets each have their "
                    "own spec page that needs a separate review pass via "
                    "`--spec <id>`?"
                ),
            )
        ]


_: Rule = MultipleSpecsReferenced()
