"""Collect branch-level metadata: name, base ref, head sha, last commit
message, ticket-key trailers, branch creation timestamp.

The result feeds two downstream consumers: the manifest (so ``analyse``
knows what was on disk) and the resolver (so it can match a branch name
or commit trailer to a Notion page).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from spec_check.core.gitwrap import GitWrapperError, GitWriteRefused, run_git
from spec_check.core.schema import CollectorStatus

from . import CollectorOutput

# ``Refs: PROJ-123``, ``Ref: PROJ-123``, ``Refs PROJ-123``, plus inline
# ``[PROJ-123]`` brackets in the subject. Captured as full ticket strings.
_TRAILER_RE = re.compile(r"^\s*Refs?:?\s*(?P<ticket>[A-Z][A-Z0-9]+-\d+)", re.MULTILINE)
_BRACKET_RE = re.compile(r"\[(?P<ticket>[A-Z][A-Z0-9]+-\d+)\]")


@dataclass(frozen=True, slots=True)
class BranchMeta:
    branch: str
    head_sha: str
    base_ref: str
    last_commit_subject: str
    last_commit_body: str
    ticket_trailers: list[str] = field(default_factory=list)
    bracketed_tickets: list[str] = field(default_factory=list)
    branch_created_at: datetime | None = None


def _git(args: list[str], cwd: Path) -> str:
    try:
        return run_git(args, cwd=cwd, check=False).stdout
    except (GitWrapperError, GitWriteRefused):
        return ""


def _resolve_default_base_ref(cwd: Path) -> str:
    """Pick a base ref. Order:

    1. ``origin/HEAD`` symbolic ref → ``origin/main`` or ``origin/master``.
    2. Local ``main`` if it exists.
    3. Local ``master`` if it exists.
    4. Empty string — the caller will need to fall back to ``HEAD~1``.
    """
    sym = _git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd).strip()
    if sym:
        return sym
    for candidate in ("origin/main", "origin/master", "main", "master"):
        if _git(["rev-parse", "--verify", candidate], cwd).strip():
            return candidate
    return ""


def _parse_trailers(message: str) -> tuple[list[str], list[str]]:
    trailers = sorted({m.group("ticket") for m in _TRAILER_RE.finditer(message)})
    brackets = sorted({m.group("ticket") for m in _BRACKET_RE.finditer(message)})
    return trailers, brackets


def _parse_branch_creation_time(reflog_output: str) -> datetime | None:
    """Walk ``git reflog show --date=iso-strict <branch>`` from the bottom
    (oldest entry) and pull the timestamp.

    Each line looks like::

        abcdef0 HEAD@{2026-04-30T20:31:12+00:00}: branch: Created from main

    We want the bottom-most entry's timestamp. Returns None if the reflog
    is missing or unparseable.
    """
    if not reflog_output.strip():
        return None
    bottom_line = reflog_output.strip().splitlines()[-1]
    m = re.search(r"\{(?P<ts>[^}]+)\}", bottom_line)
    if not m:
        return None
    try:
        return datetime.fromisoformat(m.group("ts"))
    except ValueError:
        return None


def collect_branch_meta(
    repo_path: Path, *, base_ref_override: str | None = None
) -> CollectorOutput[BranchMeta]:
    """Build a :class:`BranchMeta` from the repository at ``repo_path``."""
    try:
        branch = _git(["branch", "--show-current"], repo_path).strip()
        head_sha = _git(["rev-parse", "HEAD"], repo_path).strip()
        if not head_sha:
            return CollectorOutput(
                status=CollectorStatus(
                    name="branch_meta", state="failed", detail="HEAD does not resolve"
                )
            )
        base_ref = base_ref_override or _resolve_default_base_ref(repo_path) or "HEAD~1"
        subject = _git(["log", "-1", "--pretty=%s"], repo_path).strip()
        body = _git(["log", "-1", "--pretty=%B"], repo_path).strip()
        trailers, brackets = _parse_trailers(body)
        reflog_out = (
            _git(["reflog", "show", "--date=iso-strict", branch], repo_path) if branch else ""
        )
        created_at = _parse_branch_creation_time(reflog_out)
    except GitWriteRefused as exc:
        return CollectorOutput(
            status=CollectorStatus(
                name="branch_meta", state="failed", detail=f"git firewall refusal: {exc}"
            )
        )
    except Exception as exc:  # noqa: BLE001 — collector contract
        return CollectorOutput(
            status=CollectorStatus(name="branch_meta", state="failed", detail=str(exc))
        )

    meta = BranchMeta(
        branch=branch or "(detached)",
        head_sha=head_sha,
        base_ref=base_ref,
        last_commit_subject=subject,
        last_commit_body=body,
        ticket_trailers=trailers,
        bracketed_tickets=brackets,
        branch_created_at=created_at,
    )
    return CollectorOutput(
        status=CollectorStatus(name="branch_meta", state="ok"),
        data=meta,
    )
