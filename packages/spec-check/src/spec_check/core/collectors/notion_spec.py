"""Collect the raw Notion page + blocks for a resolved spec id.

This collector only fetches and persists; it does not parse the blocks
into a :class:`ParsedSpec`. The parser lives in
:mod:`spec_check.core.spec_parser` (step 9) and is called by the
orchestrator after this collector succeeds. Splitting fetch from parse
keeps "the network failed" and "the parser couldn't make sense of these
blocks" as distinct, separately-recoverable failure modes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from spec_check.core.notion import NotionTransportError, NotionWrapper, NotionWriteRefused
from spec_check.core.schema import CollectorStatus
from spec_check.core.snapshot import CheckPaths

from . import CollectorOutput

# Pagination guard — don't loop forever if a page somehow returns
# inconsistent cursors. 50 pages × default page_size 100 = 5,000 blocks max,
# more than enough for any spec page we care about.
_MAX_PAGES = 50


@dataclass(frozen=True, slots=True)
class RawSpecBundle:
    """Raw payload from Notion: the page object plus all of its top-level
    blocks. No further structure imposed here — the parser deals with it.
    """

    page: dict[str, Any]
    blocks: list[dict[str, Any]]


def collect_notion_spec(
    notion: NotionWrapper, spec_id: str, paths: CheckPaths
) -> CollectorOutput[RawSpecBundle]:
    """Fetch ``spec_id`` and its block tree, write to ``spec/raw_blocks.json``.

    The collector treats *any* problem from the Notion side as a soft
    failure: the rest of the run continues, and rules that depend on a
    parsed spec emit Info findings. The only thing that propagates is a
    firewall refusal — that's a bug and must surface loudly.
    """
    if not spec_id:
        return CollectorOutput(
            status=CollectorStatus(
                name="notion_spec", state="skipped", detail="no spec_id resolved"
            )
        )
    try:
        page = notion.fetch_page(spec_id)
    except NotionWriteRefused:
        raise
    except NotionTransportError as exc:
        return CollectorOutput(
            status=CollectorStatus(name="notion_spec", state="failed", detail=str(exc))
        )
    except Exception as exc:  # noqa: BLE001 — collector contract
        return CollectorOutput(
            status=CollectorStatus(
                name="notion_spec", state="failed", detail=f"fetch_page error: {exc}"
            )
        )

    blocks: list[dict[str, Any]] = []
    cursor: str | None = None
    pages_walked = 0
    try:
        while pages_walked < _MAX_PAGES:
            response = notion.fetch_block_children(spec_id, start_cursor=cursor)
            page_blocks = _extract_results(response)
            blocks.extend(page_blocks)
            cursor = _extract_next_cursor(response)
            pages_walked += 1
            if not cursor:
                break
    except NotionWriteRefused:
        raise
    except Exception as exc:  # noqa: BLE001
        return CollectorOutput(
            status=CollectorStatus(
                name="notion_spec",
                state="failed",
                detail=f"fetch_block_children error: {exc}",
            )
        )

    if pages_walked >= _MAX_PAGES and cursor:
        return CollectorOutput(
            status=CollectorStatus(
                name="notion_spec",
                state="failed",
                detail=f"block pagination exceeded {_MAX_PAGES} pages — refusing to keep walking",
            )
        )

    bundle = RawSpecBundle(page=_to_dict(page), blocks=blocks)
    paths.spec_raw_blocks.write_text(
        json.dumps({"page": bundle.page, "blocks": bundle.blocks}, indent=2)
    )
    return CollectorOutput(
        status=CollectorStatus(
            name="notion_spec",
            state="ok",
            artefact_path=str(paths.spec_raw_blocks.relative_to(paths.root)),
        ),
        data=bundle,
    )


def _to_dict(payload: Any) -> dict[str, Any]:
    """Notion MCP responses arrive as dict-shaped JSON. Be defensive — if a
    transport returns something else, coerce it to ``{"raw": ...}`` rather
    than crash, so the parser layer (step 9) can decide.
    """
    if isinstance(payload, dict):
        return payload
    return {"raw": payload}


def _extract_results(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, dict):
        results = response.get("results")
        if isinstance(results, list):
            return [r for r in results if isinstance(r, dict)]
    if isinstance(response, list):
        return [r for r in response if isinstance(r, dict)]
    return []


def _extract_next_cursor(response: Any) -> str | None:
    if not isinstance(response, dict):
        return None
    if not response.get("has_more"):
        return None
    cursor = response.get("next_cursor")
    return cursor if isinstance(cursor, str) and cursor else None
