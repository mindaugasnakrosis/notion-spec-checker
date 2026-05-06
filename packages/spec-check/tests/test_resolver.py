"""Tests for spec_check.core.resolver."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import pytest
from spec_check.core.collectors.branch_meta import BranchMeta
from spec_check.core.config import SpecCheckSettings
from spec_check.core.notion import NotionWrapper
from spec_check.core.resolver import (
    ResolutionCandidate,
    SpecResolution,
    _branch_slug,
    _extract_search_pages,
    _extract_tickets,
    resolve_spec,
)

# ---------------------------------------------------------------------------
# Test plumbing
# ---------------------------------------------------------------------------


class _SearchTransport:
    """Minimal transport that lets each test scripts canned ``search`` results.

    Each call to ``search(query)`` consults ``self.results_for[query]`` (or
    ``default_results`` if absent) and returns ``{"results": [...]}``.
    """

    def __init__(self) -> None:
        self.results_for: dict[str, list[dict[str, Any]]] = {}
        self.default_results: list[dict[str, Any]] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, method: str, /, **kwargs: Any) -> Any:
        self.calls.append((method, dict(kwargs)))
        if method != "search":
            raise RuntimeError(f"unexpected method {method}")
        query = kwargs.get("query", "")
        results = self.results_for.get(query, self.default_results)
        return {"results": results}


@pytest.fixture
def settings() -> SpecCheckSettings:
    return SpecCheckSettings()


@pytest.fixture
def transport() -> _SearchTransport:
    return _SearchTransport()


@pytest.fixture
def notion(transport: _SearchTransport) -> NotionWrapper:
    return NotionWrapper(transport)


def _branch_meta(
    *,
    branch: str = "feat/x",
    trailers: list[str] | None = None,
    brackets: list[str] | None = None,
) -> BranchMeta:
    return BranchMeta(
        branch=branch,
        head_sha="abcdef1",
        base_ref="main",
        last_commit_subject="x",
        last_commit_body="x",
        ticket_trailers=trailers or [],
        bracketed_tickets=brackets or [],
        branch_created_at=datetime(2026, 4, 30),
    )


def _page(page_id: str, title: str, url: str = "") -> dict[str, Any]:
    return {
        "id": page_id,
        "url": url or f"https://notion.so/{page_id}",
        "properties": {"title": {"title": [{"plain_text": title}]}},
    }


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_extract_tickets_finds_branch_ticket(self) -> None:
        pat = re.compile(r"[A-Z][A-Z0-9]+-\d+")
        assert _extract_tickets("feat/PROJ-123-login", pat) == ["PROJ-123"]

    def test_extract_tickets_dedupes(self) -> None:
        pat = re.compile(r"[A-Z][A-Z0-9]+-\d+")
        assert _extract_tickets("feat/PROJ-1-thing-PROJ-1", pat) == ["PROJ-1"]

    @pytest.mark.parametrize(
        ("branch", "expected"),
        [
            ("feat/PROJ-123-add-login-flow", "add login flow"),
            ("feature/APP-7-something_or_other", "something or other"),
            ("PROJ-1", ""),
            ("just-words", "just words"),
            ("fix/PROJ-9", ""),
        ],
    )
    def test_branch_slug(self, branch: str, expected: str) -> None:
        pat = re.compile(r"[A-Z][A-Z0-9]+-\d+")
        assert _branch_slug(branch, pat) == expected

    def test_extract_search_pages_handles_results_dict(self) -> None:
        pages = _extract_search_pages({"results": [_page("p1", "Login flow")]})
        assert pages == [{"id": "p1", "title": "Login flow", "url": "https://notion.so/p1"}]

    def test_extract_search_pages_handles_bare_list(self) -> None:
        pages = _extract_search_pages([_page("p1", "Login")])
        assert pages and pages[0]["id"] == "p1"

    def test_extract_search_pages_handles_alt_title_shape(self) -> None:
        # ``title`` directly on the page object instead of in properties.
        page = {"id": "p1", "url": "u", "title": [{"plain_text": "Direct title"}]}
        pages = _extract_search_pages({"results": [page]})
        assert pages[0]["title"] == "Direct title"

    def test_extract_search_pages_handles_none(self) -> None:
        assert _extract_search_pages(None) == []


# ---------------------------------------------------------------------------
# Resolution paths
# ---------------------------------------------------------------------------


class TestExplicitOverride:
    def test_override_always_wins(
        self, notion: NotionWrapper, settings: SpecCheckSettings, transport: _SearchTransport
    ) -> None:
        result = resolve_spec(
            notion,
            _branch_meta(branch="feat/PROJ-1-thing"),
            settings,
            explicit_spec_id="manual-page-id",
        )
        assert result.is_resolved
        assert result.spec_id == "manual-page-id"
        assert result.resolution_method == "override"
        # Override must short-circuit before any Notion search.
        assert transport.calls == []


class TestTicketKeyResolution:
    def test_branch_ticket_with_title_match_resolves(
        self, notion: NotionWrapper, settings: SpecCheckSettings, transport: _SearchTransport
    ) -> None:
        transport.results_for["PROJ-123"] = [_page("page-A", "PROJ-123 Login flow")]
        result = resolve_spec(notion, _branch_meta(branch="feat/PROJ-123-login"), settings)
        assert result.is_resolved
        assert result.spec_id == "page-A"
        assert result.resolution_method == "ticket_key"

    def test_trailer_ticket_resolves_when_branch_has_no_ticket(
        self, notion: NotionWrapper, settings: SpecCheckSettings, transport: _SearchTransport
    ) -> None:
        transport.results_for["APP-7"] = [_page("page-T", "APP-7 Profile screen")]
        result = resolve_spec(
            notion, _branch_meta(branch="feat/profile-screen", trailers=["APP-7"]), settings
        )
        assert result.spec_id == "page-T"
        assert result.resolution_method == "trailer"

    def test_branch_ticket_takes_priority_over_trailer(
        self, notion: NotionWrapper, settings: SpecCheckSettings, transport: _SearchTransport
    ) -> None:
        transport.results_for["PROJ-123"] = [_page("branch-page", "PROJ-123 X")]
        # If the resolver tried the trailer too, it would also score 1.0 and
        # we'd get an ambiguous answer. The contract is: branch ticket first;
        # trailers only consulted on miss.
        transport.results_for["PROJ-999"] = [_page("trailer-page", "PROJ-999 Y")]
        result = resolve_spec(
            notion,
            _branch_meta(branch="feat/PROJ-123-x", trailers=["PROJ-123"]),
            settings,
        )
        assert result.spec_id == "branch-page"


class TestFuzzyResolution:
    def test_fuzzy_resolves_against_title(
        self, notion: NotionWrapper, settings: SpecCheckSettings, transport: _SearchTransport
    ) -> None:
        transport.default_results = [_page("page-fuzzy", "Add login flow")]
        result = resolve_spec(notion, _branch_meta(branch="feat/add-login-flow"), settings)
        assert result.is_resolved
        assert result.spec_id == "page-fuzzy"
        assert result.resolution_method == "fuzzy"

    def test_fuzzy_below_threshold_unresolved(
        self, notion: NotionWrapper, settings: SpecCheckSettings, transport: _SearchTransport
    ) -> None:
        transport.default_results = [_page("page-x", "completely different topic about widgets")]
        result = resolve_spec(notion, _branch_meta(branch="feat/payment-rails"), settings)
        assert not result.is_resolved
        assert result.resolution_method == "unresolved"


class TestAmbiguity:
    def test_multiple_distinct_tickets_returns_ambiguous(
        self, notion: NotionWrapper, settings: SpecCheckSettings
    ) -> None:
        result = resolve_spec(
            notion,
            _branch_meta(branch="feat/PROJ-1-x", trailers=["PROJ-2"]),
            settings,
        )
        assert not result.is_resolved
        assert result.resolution_method == "ambiguous"
        assert "more than one ticket" in result.detail

    def test_two_close_fuzzy_candidates_returns_ambiguous(
        self, notion: NotionWrapper, settings: SpecCheckSettings, transport: _SearchTransport
    ) -> None:
        # Two distinct candidate titles, neither an exact match for the slug.
        # Both will score < 1.0 with similar ratios, so the near-tie band
        # triggers ambiguity.
        transport.default_results = [
            _page("page-1", "Login workflow design"),
            _page("page-2", "Login workflows draft"),
        ]
        result = resolve_spec(notion, _branch_meta(branch="feat/login-workflow"), settings)
        assert not result.is_resolved
        assert result.resolution_method == "ambiguous"
        assert len(result.candidates) >= 2

    def test_exact_title_score_one_wins_outright(
        self, notion: NotionWrapper, settings: SpecCheckSettings, transport: _SearchTransport
    ) -> None:
        # Even with a near-tie, a perfect 1.0 match wins outright — the
        # near-tie band only applies when the leader is < 1.0.
        transport.results_for["PROJ-1"] = [
            _page("perfect", "PROJ-1 exact match"),
            _page("close", "PROJ-1 also exact match"),
        ]
        result = resolve_spec(notion, _branch_meta(branch="feat/PROJ-1-x"), settings)
        # Ambiguous score-tie path doesn't trigger when both are 1.0; first wins.
        assert result.is_resolved
        assert result.resolution_method == "ticket_key"


class TestUnresolved:
    def test_no_ticket_no_match_returns_unresolved(
        self, notion: NotionWrapper, settings: SpecCheckSettings, transport: _SearchTransport
    ) -> None:
        transport.default_results = []
        result = resolve_spec(notion, _branch_meta(branch="feat/random-branch"), settings)
        assert not result.is_resolved
        assert result.resolution_method == "unresolved"
        assert "Pass --spec" in result.detail

    def test_search_failure_degrades_gracefully(
        self, notion: NotionWrapper, settings: SpecCheckSettings, transport: _SearchTransport
    ) -> None:
        # Patch the wrapper's search to raise — the resolver should swallow it
        # and return unresolved rather than propagating.
        def _boom(method: str, /, **_: Any) -> Any:
            raise RuntimeError("MCP down")

        transport.call = _boom  # type: ignore[method-assign]
        result = resolve_spec(notion, _branch_meta(branch="feat/PROJ-1-x"), settings)
        assert isinstance(result, SpecResolution)
        assert not result.is_resolved


class TestCustomTicketPattern:
    def test_repo_ticket_pattern_used(
        self, transport: _SearchTransport, notion: NotionWrapper
    ) -> None:
        # Override the regex to require a "USR-" prefix.
        s = SpecCheckSettings(resolver={"ticket_pattern": r"USR-\d+", "fuzzy_match_min_score": 0.6})
        transport.results_for["USR-9"] = [_page("p", "USR-9 thing")]
        result = resolve_spec(notion, _branch_meta(branch="feat/USR-9-thing"), s)
        assert result.is_resolved
        assert result.spec_id == "p"


class TestResolutionCandidate:
    def test_candidate_carries_matched_via_label(
        self, notion: NotionWrapper, settings: SpecCheckSettings, transport: _SearchTransport
    ) -> None:
        transport.results_for["PROJ-1"] = [_page("p", "PROJ-1 thing")]
        result = resolve_spec(notion, _branch_meta(branch="feat/PROJ-1-thing"), settings)
        assert result.candidates
        c = result.candidates[0]
        assert isinstance(c, ResolutionCandidate)
        assert c.matched_via == "ticket_key:PROJ-1"
