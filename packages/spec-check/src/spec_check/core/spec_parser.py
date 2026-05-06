"""Parse raw Notion blocks into a :class:`ParsedSpec`.

The parser embodies our **authoring contract** — what we assume "a spec
page" looks like in Notion. Documented authoritatively in
``packages/spec-check/src/spec_check/knowledge/notion-page-conventions.md``
(authored in step 11). The contract:

- A heading whose plain text matches "Acceptance Criteria" (case-insensitive)
  introduces the AC section.
- Direct children of that heading become individual criteria. Recognised
  block types are ``bulleted_list_item``, ``numbered_list_item``, ``to_do``
  (rendered as a checklist), and ``paragraph`` (when the paragraph reads
  like a Given/When/Then sentence).
- The AC section ends at the next heading.
- A criterion in ``Given … When … Then …`` style is classified
  ``given_when_then``; a ``to_do`` becomes ``checklist``; everything else
  is ``bullet``.

Anything outside the AC section is preserved in ``other_blocks`` so rules
can still read context (titles, "Out of scope" sections, etc.) without
re-walking raw JSON.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from spec_check.core.collectors.notion_spec import RawSpecBundle
from spec_check.core.config import SpecCheckSettings
from spec_check.core.schema import AcceptanceCriterion, AmbiguityFlag, ParsedSpec

_AC_HEADING_RE = re.compile(
    r"^\s*(?:acceptance\s+criteria|acceptance\s+criterion|criteria)\s*:?\s*$",
    re.IGNORECASE,
)
_HEADING_TYPES = {"heading_1", "heading_2", "heading_3"}
_CRITERION_BLOCK_TYPES = {"bulleted_list_item", "numbered_list_item", "to_do", "paragraph"}
_GWT_RE = re.compile(
    r"\bgiven\b.*?\bwhen\b.*?\bthen\b",
    re.IGNORECASE | re.DOTALL,
)


def parse_spec(raw: RawSpecBundle, settings: SpecCheckSettings) -> ParsedSpec:
    """Build a :class:`ParsedSpec` from a fetched Notion page + its blocks.

    Failure-tolerant: if the page object is missing fields, fall back to
    sensible placeholders so rules can still emit Info findings rather than
    the parser dying. Only the page id is strictly required.
    """
    page = raw.page or {}
    page_id = _coerce_str(page.get("id")) or "(unknown)"
    title = _extract_page_title(page) or "(untitled)"
    url = _coerce_str(page.get("url")) or ""
    last_edited = _parse_iso(page.get("last_edited_time"))

    ambiguity_phrases = list(settings.ambiguity_phrases)
    criteria: list[AcceptanceCriterion] = []
    other_blocks: dict[str, Any] = {"pre_ac": [], "post_ac": []}

    in_ac_section = False
    seen_ac_section = False
    counter = 0

    for index, block in enumerate(raw.blocks):
        if not isinstance(block, dict):
            continue
        block_type = _coerce_str(block.get("type")) or ""

        if block_type in _HEADING_TYPES:
            if _is_ac_heading(block):
                in_ac_section = True
                seen_ac_section = True
                continue
            if in_ac_section:
                in_ac_section = False  # leaving the AC section
            other_blocks["post_ac" if seen_ac_section else "pre_ac"].append(_block_summary(block))
            continue

        if in_ac_section and block_type in _CRITERION_BLOCK_TYPES:
            text = _block_plain_text(block).strip()
            if not text:
                continue
            counter += 1
            criteria.append(
                _build_criterion(counter, text, block_type, ambiguity_phrases, line_in_source=index)
            )
            continue

        # Non-criterion content (paragraphs outside AC, callouts, dividers …)
        other_blocks["post_ac" if seen_ac_section else "pre_ac"].append(_block_summary(block))

    return ParsedSpec(
        notion_page_id=page_id,
        title=title,
        url=url or f"https://notion.so/{page_id}",
        last_edited_time=last_edited,
        has_ac_section=seen_ac_section,
        criteria=criteria,
        other_blocks=other_blocks,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_ac_heading(block: dict[str, Any]) -> bool:
    text = _block_plain_text(block).strip()
    return bool(_AC_HEADING_RE.match(text))


def _build_criterion(
    counter: int,
    text: str,
    block_type: str,
    ambiguity_phrases: list[str],
    *,
    line_in_source: int,
) -> AcceptanceCriterion:
    style = _classify_style(text, block_type)
    flags = _detect_ambiguity(text, ambiguity_phrases)
    observable = _is_observable(style, flags)
    return AcceptanceCriterion(
        id=f"AC-{counter}",
        text=text,
        style=style,
        observable=observable,
        ambiguity_flags=flags,
        line_in_source=line_in_source,
    )


def _classify_style(text: str, block_type: str) -> str:
    if _GWT_RE.search(text):
        return "given_when_then"
    if block_type == "to_do":
        return "checklist"
    return "bullet"


def _detect_ambiguity(text: str, phrases: list[str]) -> list[AmbiguityFlag]:
    """Flag every ambiguity phrase whose token appears in the criterion.

    Match is case-insensitive and word-boundary-aware so ``"some"`` doesn't
    flag ``"something"``. Multi-word phrases match as substrings.
    """
    found: list[AmbiguityFlag] = []
    haystack = text.lower()
    for phrase in phrases:
        needle = phrase.lower()
        if " " in needle or "-" in needle:
            if needle in haystack:
                found.append(
                    AmbiguityFlag(phrase=phrase, reason=f"contains imprecise phrase {phrase!r}")
                )
            continue
        if re.search(rf"\b{re.escape(needle)}\b", haystack):
            found.append(AmbiguityFlag(phrase=phrase, reason=f"contains imprecise word {phrase!r}"))
    return found


def _is_observable(style: str, flags: list[AmbiguityFlag]) -> bool:
    # Given/When/Then is observable by construction — it has a When (trigger)
    # and a Then (verifiable outcome). For bullets/checklists, presence of
    # any ambiguity flag tips into "not observable" until clarified.
    if style == "given_when_then":
        return True
    return not flags


def _block_plain_text(block: dict[str, Any]) -> str:
    """Concatenate all ``plain_text`` fragments inside a Notion block,
    regardless of which rich-text bucket they live in.
    """
    block_type = block.get("type")
    if not isinstance(block_type, str):
        return ""
    payload = block.get(block_type)
    if not isinstance(payload, dict):
        return ""
    rich = payload.get("rich_text")
    if not isinstance(rich, list):
        return ""
    parts: list[str] = []
    for fragment in rich:
        if not isinstance(fragment, dict):
            continue
        text = fragment.get("plain_text")
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def _block_summary(block: dict[str, Any]) -> dict[str, Any]:
    """Trim a block down to ``{type, text}`` for storage in ``other_blocks``.

    We don't preserve the full rich-text tree because the rules that read
    ``other_blocks`` only ever look at plain text (e.g. "is there an
    'Out of scope' heading anywhere?"). Storing less keeps ``parsed.yaml``
    readable.
    """
    return {"type": block.get("type"), "text": _block_plain_text(block).strip()}


def _extract_page_title(page: dict[str, Any]) -> str:
    """Mirror of resolver._extract_title, kept local so the parser doesn't
    depend on the resolver. Tries the three common Notion shapes.
    """
    props = page.get("properties")
    if isinstance(props, dict):
        title_prop = props.get("title")
        if isinstance(title_prop, dict):
            rich = title_prop.get("title")
            if isinstance(rich, list):
                texts = [
                    t.get("plain_text") for t in rich if isinstance(t, dict) and t.get("plain_text")
                ]
                if texts:
                    return "".join(texts)

    title = page.get("title")
    if isinstance(title, list):
        texts = [t.get("plain_text") for t in title if isinstance(t, dict) and t.get("plain_text")]
        if texts:
            return "".join(texts)
    if isinstance(title, str) and title:
        return title

    return ""


def _coerce_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _parse_iso(value: Any) -> datetime:
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(UTC)
