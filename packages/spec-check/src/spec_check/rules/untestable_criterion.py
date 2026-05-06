"""Rule: ``untestable_criterion``.

Fires once per acceptance criterion the parser believes lacks an
observable outcome (``observable=False``). Currently the parser couples
that signal to ambiguity flags for non-GWT criteria; future parser
revisions may set ``observable=False`` for additional reasons (no actor,
no trigger, implementation-coupled outcome). This rule speaks for *all*
of them, because it operates on the parser's classification, not on the
underlying heuristic.

Grounded in :doc:`observable-acceptance-criteria
<../knowledge/observable-acceptance-criteria>`.
"""

from __future__ import annotations

from spec_check.core.schema import Confidence, Finding, Severity
from spec_check.rules.base import Rule, RuleContext


class UntestableCriterion:
    """A criterion has no observable outcome."""

    rule_id: str = "untestable_criterion"
    title: str = "Acceptance criterion has no observable outcome"
    knowledge_refs: tuple[str, ...] = ("observable-acceptance-criteria.md",)

    def evaluate(self, ctx: RuleContext) -> list[Finding]:
        if ctx.parsed_spec is None:
            return []

        findings: list[Finding] = []
        for criterion in ctx.parsed_spec.criteria:
            if criterion.observable:
                continue
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    title=f"Untestable criterion {criterion.id}",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.MEDIUM,
                    knowledge_refs=list(self.knowledge_refs),
                    evidence={
                        "notion_page_id": ctx.parsed_spec.notion_page_id,
                        "spec_url": ctx.parsed_spec.url,
                        "criterion_id": criterion.id,
                        "criterion_text": criterion.text,
                        "criterion_style": criterion.style,
                        "ambiguity_flag_count": len(criterion.ambiguity_flags),
                    },
                    recommended_investigation=(
                        f"Criterion {criterion.id} reads as a quality "
                        "statement without a concrete observable outcome. "
                        "Could it be re-phrased so an outside-the-system "
                        "actor (a test, a reviewer with no source-code "
                        "access) could decide whether it has been satisfied?"
                    ),
                )
            )
        return findings


_: Rule = UntestableCriterion()
