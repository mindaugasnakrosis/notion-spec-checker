"""Tiny :class:`ParsedSpec` factory for rule tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from spec_check.core.schema import AcceptanceCriterion, AmbiguityFlag, ParsedSpec


def make_criterion(
    text: str,
    *,
    cid: str = "ac1",
    style: str = "bullet",
    observable: bool = True,
    ambiguity_flags: list[AmbiguityFlag] | None = None,
    line_in_source: int | None = None,
) -> AcceptanceCriterion:
    return AcceptanceCriterion(
        id=cid,
        text=text,
        style=style,  # type: ignore[arg-type]
        observable=observable,
        ambiguity_flags=ambiguity_flags or [],
        line_in_source=line_in_source,
    )


def make_spec(
    *,
    page_id: str = "page-A",
    title: str = "Login flow",
    url: str = "https://notion.so/page-A",
    last_edited_time: datetime | None = None,
    has_ac_section: bool = True,
    criteria: list[AcceptanceCriterion] | None = None,
    other_blocks: dict[str, Any] | None = None,
) -> ParsedSpec:
    return ParsedSpec(
        notion_page_id=page_id,
        title=title,
        url=url,
        last_edited_time=last_edited_time or datetime(2026, 4, 30, 20, 0, 0, tzinfo=UTC),
        has_ac_section=has_ac_section,
        criteria=criteria or [],
        other_blocks=other_blocks or {},
    )
