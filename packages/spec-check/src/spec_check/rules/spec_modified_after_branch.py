"""Rule: ``spec_modified_after_branch``.

Fires when the resolved Notion page's ``last_edited_time`` is later than
the branch's creation timestamp. The reviewer cannot tell from the diff
alone whether the engineer built against the *current* version of the
spec or an earlier one — this rule surfaces the risk and asks the human
to verify.

Confidence varies with the size of the gap:

* ``last_edited - branch_created > spec_drift_high_confidence_seconds``
  (default 1 hour) → **High** confidence (the edit is unlikely to be a
  trivial typo fix).
* otherwise → **Medium** confidence (the edit may be a clarification, or
  a goalpost move; the reviewer decides).

Grounded in :doc:`spec-drift <../knowledge/spec-drift>`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from spec_check.core.schema import Confidence, Finding, Severity
from spec_check.rules.base import Rule, RuleContext


def _to_utc(value: datetime) -> datetime:
    """Treat naive timestamps as UTC. Notion always returns tz-aware
    ISO-8601, but tests and a future on-disk cache may produce naive
    datetimes; coercing to UTC keeps subtraction safe.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class SpecModifiedAfterBranch:
    """Notion spec was edited after the branch was created."""

    rule_id: str = "spec_modified_after_branch"
    title: str = "Spec was modified after the branch was created"
    knowledge_refs: tuple[str, ...] = ("spec-drift.md",)

    def evaluate(self, ctx: RuleContext) -> list[Finding]:
        if ctx.parsed_spec is None:
            return []
        if ctx.branch_created_at is None:
            # No reflog → can't compare. Stay silent rather than guess.
            return []

        last_edited = _to_utc(ctx.parsed_spec.last_edited_time)
        branch_created = _to_utc(ctx.branch_created_at)
        if last_edited <= branch_created:
            return []

        delta = last_edited - branch_created
        threshold = ctx.settings.spec_drift_high_confidence_seconds
        confidence = (
            Confidence.HIGH if delta.total_seconds() > threshold else Confidence.MEDIUM
        )

        return [
            Finding(
                rule_id=self.rule_id,
                title="Spec was modified after the branch was created",
                severity=Severity.HIGH,
                confidence=confidence,
                knowledge_refs=list(self.knowledge_refs),
                evidence={
                    "notion_page_id": ctx.parsed_spec.notion_page_id,
                    "spec_url": ctx.parsed_spec.url,
                    "spec_last_edited_time": last_edited.isoformat(),
                    "branch_created_at": branch_created.isoformat(),
                    "delta_seconds": int(delta.total_seconds()),
                    "high_confidence_threshold_seconds": threshold,
                    "branch": ctx.manifest.branch,
                    "head_sha": ctx.manifest.head_sha,
                },
                recommended_investigation=(
                    f"The spec page was edited "
                    f"{int(delta.total_seconds())}s after this branch was "
                    "created. Notion's API doesn't expose what changed — can "
                    "the spec author confirm whether the edit was a typo or "
                    "clarification, or did the criteria themselves move "
                    "while the branch was open?"
                ),
            )
        ]


_: Rule = SpecModifiedAfterBranch()
