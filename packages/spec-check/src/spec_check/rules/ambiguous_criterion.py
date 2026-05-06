"""Rule: ``ambiguous_criterion``.

Fires once per acceptance criterion that the parser flagged with one or
more ambiguity phrases. The flags themselves are populated by
``spec_parser._detect_ambiguity`` against ``settings.ambiguity_phrases``;
this rule's job is to translate parser flags into per-criterion findings
the report can render.

Grounded in :doc:`ambiguity-in-acceptance-criteria
<../knowledge/ambiguity-in-acceptance-criteria>`.
"""

from __future__ import annotations

from spec_check.core.schema import Confidence, Finding, Severity
from spec_check.rules.base import Rule, RuleContext


class AmbiguousCriterion:
    """A criterion contains imprecise language."""

    rule_id: str = "ambiguous_criterion"
    title: str = "Acceptance criterion contains ambiguous language"
    knowledge_refs: tuple[str, ...] = ("ambiguity-in-acceptance-criteria.md",)

    def evaluate(self, ctx: RuleContext) -> list[Finding]:
        if ctx.parsed_spec is None:
            return []

        findings: list[Finding] = []
        for criterion in ctx.parsed_spec.criteria:
            if not criterion.ambiguity_flags:
                continue
            phrases = [flag.phrase for flag in criterion.ambiguity_flags]
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    title=f"Ambiguous language in {criterion.id}",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.MEDIUM,
                    knowledge_refs=list(self.knowledge_refs),
                    evidence={
                        "notion_page_id": ctx.parsed_spec.notion_page_id,
                        "spec_url": ctx.parsed_spec.url,
                        "criterion_id": criterion.id,
                        "criterion_text": criterion.text,
                        "criterion_style": criterion.style,
                        "ambiguous_phrases": phrases,
                        "flag_reasons": [flag.reason for flag in criterion.ambiguity_flags],
                    },
                    recommended_investigation=(
                        f"Criterion {criterion.id} contains "
                        f"{_format_phrase_list(phrases)}. Could the criterion "
                        "be re-phrased so a reviewer would not have to guess "
                        "what passing looks like — or is the phrase a "
                        "domain term that the team has agreed to accept?"
                    ),
                )
            )
        return findings


def _format_phrase_list(phrases: list[str]) -> str:
    quoted = [f"{p!r}" for p in phrases]
    if len(quoted) == 1:
        return f"the imprecise phrase {quoted[0]}"
    if len(quoted) == 2:
        return f"the imprecise phrases {quoted[0]} and {quoted[1]}"
    return "the imprecise phrases " + ", ".join(quoted[:-1]) + f", and {quoted[-1]}"


_: Rule = AmbiguousCriterion()
