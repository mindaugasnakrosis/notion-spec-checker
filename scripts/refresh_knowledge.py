#!/usr/bin/env python3
"""Maintainer-only: re-fetch each canonical knowledge source and surface
drift for human review.

This script does NOT rewrite the verbatim quoted body — that decision must
stay with a human, because canonical sources sometimes restructure the
underlying page (renames a section, swaps verbiage). The flow is:

  1. Read each ``knowledge/*.md``'s frontmatter.
  2. Skip authored docs (``canonical_url: null``) — they have no upstream.
  3. Fetch the canonical URL listed in frontmatter.
  4. Compute the SHA-256 of the *fetched* page body.
  5. Compare against the stored ``content_sha256``.
  6. Print a per-file status. ``retrieval_date`` and an internal
     ``upstream_sha256`` (added on first run) are auto-updated; the
     ``content_sha256`` over the verbatim quote in the body is left alone
     so a reviewer can see drift in git diff.

Run from the repo root:

  uv run python scripts/refresh_knowledge.py

Status legend:
  • UNCHANGED — upstream still matches the previously-recorded hash.
  • UPDATED   — first-time upstream hash recorded; quoted body unchanged.
  • DRIFTED   — upstream changed; the verbatim quote may need a manual edit.
                Frontmatter is left as-is so the diff is visible in git.
  • SKIP      — authored doc with no canonical_url.
  • FAILED    — fetch errored; rerun later.
"""

from __future__ import annotations

import hashlib
import sys
from datetime import date
from pathlib import Path

import httpx
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_ROOT = (
    REPO_ROOT / "packages" / "spec-check" / "src" / "spec_check" / "knowledge"
)


def split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm = yaml.safe_load(parts[1]) or {}
    return fm, parts[2]


def write_with_frontmatter(path: Path, fm: dict, body: str) -> None:
    fm_text = yaml.safe_dump(fm, sort_keys=False).strip()
    path.write_text(f"---\n{fm_text}\n---{body}", encoding="utf-8")


def fetch(url: str) -> str:
    resp = httpx.get(url, follow_redirects=True, timeout=30.0)
    resp.raise_for_status()
    return resp.text


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def refresh_one(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)
    url = fm.get("canonical_url")
    if not url:
        # Authored doc — no upstream to refresh.
        return f"SKIP      {path.name} (authored)"

    try:
        page = fetch(url)
    except Exception as exc:  # noqa: BLE001 — surface every failure mode
        return f"FAILED    {path.name}: {type(exc).__name__}: {exc}"

    new_hash = sha256(page)
    upstream_old = fm.get("upstream_sha256")
    fm["retrieval_date"] = date.today().isoformat()
    fm["upstream_sha256"] = new_hash

    if upstream_old == new_hash:
        write_with_frontmatter(path, fm, body)
        return f"UNCHANGED {path.name}"
    if upstream_old is None:
        write_with_frontmatter(path, fm, body)
        return f"UPDATED   {path.name}: first-time upstream hash recorded"
    write_with_frontmatter(path, fm, body)
    return (
        f"DRIFTED   {path.name}: upstream changed "
        f"({upstream_old[:8]} → {new_hash[:8]}); review the verbatim quote and "
        f"recompute content_sha256 if you update the body"
    )


def main(argv: list[str]) -> int:
    targets = sorted(KNOWLEDGE_ROOT.glob("*.md"))
    targets = [p for p in targets if p.name.lower() != "readme.md"]
    if not targets:
        print(f"No knowledge files under {KNOWLEDGE_ROOT}", file=sys.stderr)
        return 2
    for path in targets:
        print(refresh_one(path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
