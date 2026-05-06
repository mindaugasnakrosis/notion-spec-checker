"""Branch → Notion spec id.

Resolution order:

1. **Explicit override.** ``--spec <page-id>`` on the CLI, or ``spec_id:`` in
   a repo-level ``.spec-check.yaml``. Always wins.
2. **Ticket key in branch name.** Apply ``settings.resolver.ticket_pattern``
   to the branch (default ``[A-Z][A-Z0-9]+-\\d+``). Search Notion for any
   page whose title or body mentions that key.
3. **Commit trailer / bracketed ticket.** ``Refs: PROJ-123`` or ``[PROJ-123]``
   parsed by :mod:`spec_check.core.collectors.branch_meta`. Same Notion
   search.
4. **Branch-slug fuzzy match.** Derive a slug from the branch (drop common
   prefixes and the ticket key), search Notion, score each result against
   the slug with :func:`difflib.SequenceMatcher.ratio`.

When multiple branches/trailers reference different tickets, or when two
candidates have nearly equal fuzzy scores, the resolver returns a
``"ambiguous"`` result. Callers (the orchestrator and the
``multiple_specs_referenced`` rule) emit Info findings rather than picking
a winner — that's the human's job.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from spec_check.core.collectors.branch_meta import BranchMeta
from spec_check.core.config import SpecCheckSettings
from spec_check.core.notion import NotionWrapper

DEFAULT_NOTION_SEARCH_PAGE_SIZE = 10
_RUNNER_UP_BAND = 0.05  # candidates within this score of the leader are "near-ties"


@dataclass(frozen=True, slots=True)
class ResolutionCandidate:
    spec_id: str
    title: str
    url: str
    score: float
    matched_via: str  # "ticket_key:PROJ-123" / "trailer:APP-7" / "fuzzy:login-flow"


@dataclass(frozen=True, slots=True)
class SpecResolution:
    """The output of :func:`resolve_spec`.

    ``spec_id`` is the resolved page id when a single confident match is
    found. ``resolution_method`` records *how* the resolver arrived at it,
    feeding directly into the manifest. When unresolved or ambiguous,
    ``candidates`` may contain partial information for the human / for an
    Info finding.
    """

    spec_id: str | None
    resolution_method: (
        str  # "override" / "ticket_key" / "trailer" / "fuzzy" / "ambiguous" / "unresolved"
    )
    candidates: list[ResolutionCandidate] = field(default_factory=list)
    detail: str = ""

    @property
    def is_resolved(self) -> bool:
        return self.spec_id is not None


def resolve_spec(
    notion: NotionWrapper,
    branch_meta: BranchMeta,
    settings: SpecCheckSettings,
    *,
    explicit_spec_id: str | None = None,
) -> SpecResolution:
    """Run the resolution ladder and return one :class:`SpecResolution`."""
    if explicit_spec_id:
        return SpecResolution(
            spec_id=explicit_spec_id,
            resolution_method="override",
            detail="explicit --spec override",
        )

    pattern = re.compile(settings.resolver.ticket_pattern)
    branch_tickets = _extract_tickets(branch_meta.branch, pattern)
    trailer_tickets = _dedupe_preserve_order(
        [*branch_meta.ticket_trailers, *branch_meta.bracketed_tickets]
    )
    all_tickets = _dedupe_preserve_order([*branch_tickets, *trailer_tickets])

    if len({t for t in all_tickets}) > 1:
        return SpecResolution(
            spec_id=None,
            resolution_method="ambiguous",
            candidates=[],
            detail=(
                f"branch + commit reference more than one ticket: {sorted(set(all_tickets))}. "
                f"Pass --spec <page-id> to disambiguate."
            ),
        )

    candidates: list[ResolutionCandidate] = []

    # 2. Branch-name ticket key.
    for ticket in branch_tickets:
        candidates.extend(_search_pages_for_ticket(notion, ticket, source="ticket_key"))

    # 3. Commit trailer / bracketed ticket — only if the branch ticket didn't
    #    already locate the page (avoid double-counting the same key).
    if not candidates:
        for ticket in trailer_tickets:
            candidates.extend(_search_pages_for_ticket(notion, ticket, source="trailer"))

    # 4. Fuzzy slug match.
    if not candidates:
        slug = _branch_slug(branch_meta.branch, pattern)
        if slug:
            candidates.extend(
                _search_pages_for_slug(notion, slug, settings.resolver.fuzzy_match_min_score)
            )

    if not candidates:
        return SpecResolution(
            spec_id=None,
            resolution_method="unresolved",
            detail=(
                "no Notion page matched the branch name, commit trailers, or "
                "branch-slug fuzzy search. Pass --spec <page-id> to point at a page."
            ),
        )

    candidates.sort(key=lambda c: c.score, reverse=True)
    top = candidates[0]
    near_ties = [c for c in candidates[1:] if top.score - c.score < _RUNNER_UP_BAND]

    if near_ties and top.score < 1.0:
        return SpecResolution(
            spec_id=None,
            resolution_method="ambiguous",
            candidates=candidates[:5],
            detail=(
                f"multiple candidate pages with similar match score "
                f"({top.score:.2f} vs {near_ties[0].score:.2f}). "
                f"Pass --spec <page-id> to pick one."
            ),
        )

    method = top.matched_via.split(":", 1)[0]
    return SpecResolution(
        spec_id=top.spec_id,
        resolution_method=method,
        candidates=[top],
        detail=f"resolved via {top.matched_via}",
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_tickets(branch: str, pattern: re.Pattern[str]) -> list[str]:
    return _dedupe_preserve_order(m.group(0) for m in pattern.finditer(branch))


def _branch_slug(branch: str, ticket_pattern: re.Pattern[str]) -> str:
    """Derive a search slug from a branch name.

    ``feat/PROJ-123-add-login-flow`` → ``add login flow``. We drop the
    common prefix segment (``feat/``, ``feature/``, ``fix/``, ``chore/``,
    ``bugfix/``, ``hotfix/``, ``release/``), the ticket key, and join the
    remaining slug components with spaces so Notion full-text search has
    something to chew on.
    """
    head = branch.rsplit("/", 1)[-1]  # "PROJ-123-add-login-flow"
    head = ticket_pattern.sub("", head).strip("-_/ ")
    head = head.replace("_", "-")
    parts = [p for p in head.split("-") if p]
    return " ".join(parts).strip()


def _search_pages_for_ticket(
    notion: NotionWrapper, ticket: str, *, source: str
) -> list[ResolutionCandidate]:
    """Search Notion for the ticket key and turn results into candidates.

    A page whose title contains the ticket scores 1.0 (deterministic match);
    a page that merely mentions it elsewhere scores 0.6.
    """
    response = _safe_search(notion, ticket)
    candidates: list[ResolutionCandidate] = []
    for page in _extract_search_pages(response):
        title = page["title"]
        title_has_ticket = ticket.lower() in title.lower()
        score = 1.0 if title_has_ticket else 0.6
        candidates.append(
            ResolutionCandidate(
                spec_id=page["id"],
                title=title,
                url=page["url"],
                score=score,
                matched_via=f"{source}:{ticket}",
            )
        )
    return candidates


def _search_pages_for_slug(
    notion: NotionWrapper, slug: str, min_score: float
) -> list[ResolutionCandidate]:
    response = _safe_search(notion, slug, page_size=DEFAULT_NOTION_SEARCH_PAGE_SIZE)
    norm_slug = _normalise(slug)
    candidates: list[ResolutionCandidate] = []
    for page in _extract_search_pages(response):
        score = SequenceMatcher(None, norm_slug, _normalise(page["title"])).ratio()
        if score >= min_score:
            candidates.append(
                ResolutionCandidate(
                    spec_id=page["id"],
                    title=page["title"],
                    url=page["url"],
                    score=score,
                    matched_via=f"fuzzy:{slug}",
                )
            )
    return candidates


def _safe_search(notion: NotionWrapper, query: str, *, page_size: int | None = None) -> Any:
    """Wrap a Notion search so a transport error doesn't kill resolution.

    The wrapper's firewall errors must propagate (they're bugs in spec-check
    itself). Anything else is a soft failure: the resolver simply gets no
    results from this avenue and tries the next one.
    """
    try:
        return notion.search(query, page_size=page_size)
    except Exception:  # noqa: BLE001 — collector-style: degrade gracefully
        return None


def _extract_search_pages(response: Any) -> list[dict[str, str]]:
    """Coerce a Notion-shaped search response into a flat list of
    ``{id, title, url}`` dicts. Resilient to several common shapes the
    Notion MCP might return.
    """
    if response is None:
        return []
    raw_results: list[Any]
    if isinstance(response, dict) and isinstance(response.get("results"), list):
        raw_results = response["results"]
    elif isinstance(response, list):
        raw_results = response
    else:
        return []

    out: list[dict[str, str]] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        page_id = item.get("id")
        if not isinstance(page_id, str) or not page_id:
            continue
        title = _extract_title(item)
        url = item.get("url") or ""
        if not isinstance(url, str):
            url = ""
        out.append({"id": page_id, "title": title, "url": url})
    return out


def _extract_title(page: dict[str, Any]) -> str:
    """Pull a title out of a Notion-shaped page object. Try the explicit
    forms first, fall back to a generic plain-text scan, then to the page
    id as a last resort.
    """
    # Shape A: ``page.properties.title.title[0].plain_text`` (database row)
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

    # Shape B: ``page.title`` is a list of rich-text fragments (workspace page)
    title = page.get("title")
    if isinstance(title, list):
        texts = [t.get("plain_text") for t in title if isinstance(t, dict) and t.get("plain_text")]
        if texts:
            return "".join(texts)
    if isinstance(title, str) and title:
        return title

    # Shape C: ``page.plain_text`` directly (the MCP sometimes flattens)
    flat = page.get("plain_text")
    if isinstance(flat, str) and flat:
        return flat

    return page.get("id", "(untitled)")


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _dedupe_preserve_order(items: Any) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out
