"""Tests for spec_check.core.spec_parser."""

from __future__ import annotations

from typing import Any

import pytest
from spec_check.core.collectors.notion_spec import RawSpecBundle
from spec_check.core.config import SpecCheckSettings
from spec_check.core.spec_parser import parse_spec

# ---------------------------------------------------------------------------
# Block builders — keep tests readable
# ---------------------------------------------------------------------------


def _heading(level: int, text: str) -> dict[str, Any]:
    key = f"heading_{level}"
    return {"type": key, key: {"rich_text": [{"plain_text": text}]}}


def _bullet(text: str) -> dict[str, Any]:
    return {
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": [{"plain_text": text}]},
    }


def _todo(text: str, *, checked: bool = False) -> dict[str, Any]:
    return {
        "type": "to_do",
        "to_do": {"rich_text": [{"plain_text": text}], "checked": checked},
    }


def _paragraph(text: str) -> dict[str, Any]:
    return {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": text}]}}


def _page(*, page_id: str = "page-1", title: str = "Login feature") -> dict[str, Any]:
    return {
        "id": page_id,
        "url": f"https://notion.so/{page_id}",
        "last_edited_time": "2026-04-30T20:31:12+00:00",
        "properties": {"title": {"title": [{"plain_text": title}]}},
    }


def _bundle(blocks: list[dict[str, Any]], *, page: dict[str, Any] | None = None) -> RawSpecBundle:
    return RawSpecBundle(page=page or _page(), blocks=blocks)


@pytest.fixture
def settings() -> SpecCheckSettings:
    return SpecCheckSettings()


# ---------------------------------------------------------------------------
# Page metadata
# ---------------------------------------------------------------------------


class TestPageMetadata:
    def test_extracts_title_url_and_id(self, settings: SpecCheckSettings) -> None:
        spec = parse_spec(_bundle([]), settings)
        assert spec.notion_page_id == "page-1"
        assert spec.title == "Login feature"
        assert spec.url == "https://notion.so/page-1"

    def test_falls_back_when_title_missing(self, settings: SpecCheckSettings) -> None:
        page = {"id": "page-x", "url": "https://notion.so/page-x"}
        spec = parse_spec(_bundle([], page=page), settings)
        assert spec.title == "(untitled)"

    def test_last_edited_time_parsed(self, settings: SpecCheckSettings) -> None:
        spec = parse_spec(_bundle([]), settings)
        assert spec.last_edited_time.year == 2026
        assert spec.last_edited_time.minute == 31


# ---------------------------------------------------------------------------
# AC-section detection
# ---------------------------------------------------------------------------


class TestAcSectionDetection:
    def test_no_heading_no_section(self, settings: SpecCheckSettings) -> None:
        spec = parse_spec(_bundle([_paragraph("Some prose.")]), settings)
        assert spec.has_ac_section is False
        assert spec.criteria == []

    def test_heading_with_ac_text_starts_section(self, settings: SpecCheckSettings) -> None:
        blocks = [
            _heading(2, "Overview"),
            _heading(2, "Acceptance Criteria"),
            _bullet("User can log in."),
        ]
        spec = parse_spec(_bundle(blocks), settings)
        assert spec.has_ac_section is True
        assert len(spec.criteria) == 1

    def test_case_insensitive_heading_match(self, settings: SpecCheckSettings) -> None:
        spec = parse_spec(_bundle([_heading(3, "ACCEPTANCE CRITERIA"), _bullet("x")]), settings)
        assert spec.has_ac_section is True

    def test_section_ends_at_next_heading(self, settings: SpecCheckSettings) -> None:
        blocks = [
            _heading(2, "Acceptance Criteria"),
            _bullet("In-section bullet."),
            _heading(2, "Out of scope"),
            _bullet("Out-of-scope bullet."),
        ]
        spec = parse_spec(_bundle(blocks), settings)
        assert len(spec.criteria) == 1
        assert "In-section" in spec.criteria[0].text


# ---------------------------------------------------------------------------
# Criterion classification
# ---------------------------------------------------------------------------


class TestCriterionStyles:
    def test_bullet_is_bullet(self, settings: SpecCheckSettings) -> None:
        blocks = [_heading(2, "Acceptance Criteria"), _bullet("User can log in.")]
        spec = parse_spec(_bundle(blocks), settings)
        assert spec.criteria[0].style == "bullet"

    def test_to_do_is_checklist(self, settings: SpecCheckSettings) -> None:
        blocks = [_heading(2, "Acceptance Criteria"), _todo("Login button visible.")]
        spec = parse_spec(_bundle(blocks), settings)
        assert spec.criteria[0].style == "checklist"

    def test_given_when_then_paragraph_classified(self, settings: SpecCheckSettings) -> None:
        gwt = "Given a registered user, when they submit valid credentials, then they reach /home."
        blocks = [_heading(2, "Acceptance Criteria"), _paragraph(gwt)]
        spec = parse_spec(_bundle(blocks), settings)
        assert spec.criteria[0].style == "given_when_then"

    def test_given_when_then_bullet_also_classified(self, settings: SpecCheckSettings) -> None:
        # Given/When/Then in a bullet still classifies — style follows text shape,
        # not block type.
        gwt = "Given login screen, when user clicks SSO, then redirect to identity provider."
        spec = parse_spec(_bundle([_heading(2, "Acceptance Criteria"), _bullet(gwt)]), settings)
        assert spec.criteria[0].style == "given_when_then"


# ---------------------------------------------------------------------------
# Ambiguity detection
# ---------------------------------------------------------------------------


class TestAmbiguity:
    def test_word_level_phrase_flagged(self, settings: SpecCheckSettings) -> None:
        blocks = [_heading(2, "Acceptance Criteria"), _bullet("The page should load fast.")]
        spec = parse_spec(_bundle(blocks), settings)
        flagged = {f.phrase for f in spec.criteria[0].ambiguity_flags}
        assert "should" in flagged
        assert "fast" in flagged

    def test_multi_word_phrase_flagged(self, settings: SpecCheckSettings) -> None:
        blocks = [
            _heading(2, "Acceptance Criteria"),
            _bullet("Lots of users can sign in."),
        ]
        spec = parse_spec(_bundle(blocks), settings)
        flagged = {f.phrase for f in spec.criteria[0].ambiguity_flags}
        assert "lots of" in flagged

    def test_word_boundary_avoids_false_positives(self, settings: SpecCheckSettings) -> None:
        # "some" is in the ambiguity list but "something" must not match.
        blocks = [_heading(2, "Acceptance Criteria"), _bullet("Something specific happens.")]
        spec = parse_spec(_bundle(blocks), settings)
        flagged = {f.phrase for f in spec.criteria[0].ambiguity_flags}
        assert "some" not in flagged

    def test_observable_false_when_ambiguous(self, settings: SpecCheckSettings) -> None:
        spec = parse_spec(
            _bundle([_heading(2, "Acceptance Criteria"), _bullet("It should be fast.")]),
            settings,
        )
        assert spec.criteria[0].observable is False

    def test_observable_true_for_given_when_then_even_with_ambiguity(
        self, settings: SpecCheckSettings
    ) -> None:
        # GWT shape is observable by construction. Ambiguity_flags still
        # populate so the AC-quality rule (step 12) can call this out, but
        # observable=True because the When/Then carries a measurable signal.
        gwt = (
            "Given a slow connection, when the user opens /home, then a spinner appears within 1s."
        )
        spec = parse_spec(_bundle([_heading(2, "Acceptance Criteria"), _paragraph(gwt)]), settings)
        c = spec.criteria[0]
        assert c.style == "given_when_then"
        assert c.observable is True
        assert any(f.phrase == "slow" for f in c.ambiguity_flags)


# ---------------------------------------------------------------------------
# Other blocks preservation
# ---------------------------------------------------------------------------


class TestOtherBlocks:
    def test_pre_and_post_ac_blocks_preserved(self, settings: SpecCheckSettings) -> None:
        blocks = [
            _paragraph("Pre-AC summary."),
            _heading(2, "Acceptance Criteria"),
            _bullet("AC body."),
            _heading(2, "Out of scope"),
            _bullet("Not this."),
        ]
        spec = parse_spec(_bundle(blocks), settings)
        pre = [b["text"] for b in spec.other_blocks.get("pre_ac", [])]
        post = [b["text"] for b in spec.other_blocks.get("post_ac", [])]
        assert "Pre-AC summary." in pre
        assert any("Out of scope" in t for t in post)
        assert any("Not this." in t for t in post)


# ---------------------------------------------------------------------------
# Resilience to malformed input
# ---------------------------------------------------------------------------


class TestResilience:
    def test_skips_non_dict_blocks(self, settings: SpecCheckSettings) -> None:
        blocks: list[Any] = [_heading(2, "Acceptance Criteria"), "garbage", None, _bullet("x")]
        spec = parse_spec(_bundle(blocks), settings)
        assert len(spec.criteria) == 1
        assert spec.criteria[0].text == "x"

    def test_empty_rich_text_block_skipped(self, settings: SpecCheckSettings) -> None:
        empty = {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": []}}
        blocks = [_heading(2, "Acceptance Criteria"), empty, _bullet("non-empty")]
        spec = parse_spec(_bundle(blocks), settings)
        assert [c.text for c in spec.criteria] == ["non-empty"]

    def test_minimal_page_with_no_metadata(self, settings: SpecCheckSettings) -> None:
        spec = parse_spec(RawSpecBundle(page={"id": "p"}, blocks=[]), settings)
        assert spec.notion_page_id == "p"
        assert spec.title == "(untitled)"
        # Fallback URL when none supplied.
        assert spec.url.endswith("/p")
