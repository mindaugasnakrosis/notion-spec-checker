"""Read access to the bundled knowledge corpus.

Knowledge documents live next to the package as
``src/spec_check/knowledge/*.md`` and are force-included in the wheel by
``hatchling``. This module enumerates them and parses their YAML
frontmatter so the CLI's ``knowledge list`` and ``knowledge show`` verbs
have a single, schema-validated entry point.

The corpus is *read-only*: nothing in this codebase writes to it, and the
refresh path (step 20's ``refresh_knowledge.py``) is a separate
maintainer script that re-fetches canonical sources and updates SHA-256
checksums on disk before commit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from importlib.resources import files
from importlib.resources.abc import Traversable

import yaml
from pydantic import BaseModel, ConfigDict, Field

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


class KnowledgeFrontmatter(BaseModel):
    """Schema for the YAML frontmatter at the top of a knowledge doc."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    canonical_url: str | None = None
    canonical_author: str = Field(min_length=1)
    canonical_date: date | None = None
    retrieval_date: date | None = None
    content_sha256: str | None = None
    cited_by: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class KnowledgeDoc:
    """A parsed knowledge document: filename, frontmatter, body markdown."""

    filename: str
    frontmatter: KnowledgeFrontmatter
    body: str


class KnowledgeError(RuntimeError):
    """Raised when a knowledge file is missing or malformed."""


def _knowledge_root() -> Traversable:
    return files("spec_check.knowledge")


def _parse_doc(filename: str, raw: str) -> KnowledgeDoc:
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        raise KnowledgeError(f"{filename!r} has no YAML frontmatter block")
    fm_yaml, body = match.group(1), match.group(2)
    fm_data = yaml.safe_load(fm_yaml) or {}
    if not isinstance(fm_data, dict):
        raise KnowledgeError(f"{filename!r} frontmatter is not a mapping")
    return KnowledgeDoc(
        filename=filename,
        frontmatter=KnowledgeFrontmatter.model_validate(fm_data),
        body=body.strip(),
    )


def list_knowledge_docs() -> list[KnowledgeDoc]:
    """Enumerate every ``*.md`` doc in the corpus, sorted by filename.

    The README inside the knowledge dir is skipped — it documents the
    corpus itself rather than carrying a citation, and parsing it as a
    knowledge doc would clutter the list.
    """
    out: list[KnowledgeDoc] = []
    for entry in sorted(_knowledge_root().iterdir(), key=lambda p: p.name):
        name = entry.name
        if not name.endswith(".md") or name.lower() == "readme.md":
            continue
        out.append(_parse_doc(name, entry.read_text(encoding="utf-8")))
    return out


def read_knowledge_doc(filename: str) -> KnowledgeDoc:
    """Load a single knowledge doc by filename. Filename collisions and
    path-escape attempts are refused — only flat ``*.md`` files inside
    the corpus directory are addressable.
    """
    if "/" in filename or "\\" in filename or ".." in filename:
        raise KnowledgeError(f"invalid knowledge filename {filename!r}")
    if not filename.endswith(".md"):
        filename = f"{filename}.md"

    target = _knowledge_root() / filename
    if not target.is_file():
        raise KnowledgeError(f"knowledge doc {filename!r} not found")
    return _parse_doc(filename, target.read_text(encoding="utf-8"))
