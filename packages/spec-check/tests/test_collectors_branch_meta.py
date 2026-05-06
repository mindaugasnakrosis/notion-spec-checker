"""Tests for spec_check.core.collectors.branch_meta."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from spec_check.core.collectors.branch_meta import (
    _parse_branch_creation_time,
    _parse_trailers,
    collect_branch_meta,
)


class TestParseTrailers:
    def test_refs_trailer_extracted(self) -> None:
        msg = "Subject line\n\nBody.\n\nRefs: PROJ-123\n"
        trailers, brackets = _parse_trailers(msg)
        assert trailers == ["PROJ-123"]
        assert brackets == []

    def test_ref_singular_also_works(self) -> None:
        msg = "Subject\n\nRef: APP-7\n"
        trailers, _ = _parse_trailers(msg)
        assert trailers == ["APP-7"]

    def test_bracketed_ticket_in_subject(self) -> None:
        msg = "[PROJ-123] Add login flow\n"
        trailers, brackets = _parse_trailers(msg)
        assert brackets == ["PROJ-123"]
        assert trailers == []

    def test_multiple_tickets_deduped(self) -> None:
        msg = "[PROJ-1] Subject\n\nRefs: PROJ-1\nRefs: PROJ-2\n"
        trailers, brackets = _parse_trailers(msg)
        assert trailers == ["PROJ-1", "PROJ-2"]
        assert brackets == ["PROJ-1"]

    def test_no_tickets(self) -> None:
        trailers, brackets = _parse_trailers("Just a refactor\n")
        assert trailers == []
        assert brackets == []


class TestParseBranchCreationTime:
    def test_extracts_iso_timestamp_from_bottom_line(self) -> None:
        reflog = (
            "abcdef0 HEAD@{2026-04-30T20:31:12+00:00}: commit: do thing\n"
            "1234567 HEAD@{2026-04-30T20:00:00+00:00}: branch: Created from main\n"
        )
        ts = _parse_branch_creation_time(reflog)
        assert ts is not None
        assert ts.year == 2026
        assert ts.minute == 0

    def test_empty_reflog(self) -> None:
        assert _parse_branch_creation_time("") is None

    def test_unparseable(self) -> None:
        assert _parse_branch_creation_time("garbage\n") is None


# ---------------------------------------------------------------------------
# End-to-end against a real throwaway repo
# ---------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git not installed")

    def _git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=tmp_path, check=True, capture_output=True, text=True
        ).stdout

    _git("init", "-q", "-b", "main")
    _git("config", "user.email", "test@example.com")
    _git("config", "user.name", "test")
    (tmp_path / "README.md").write_text("hi\n")
    _git("add", "README.md")
    _git("commit", "-q", "-m", "[PROJ-1] initial\n\nRefs: PROJ-1\nRefs: APP-2")
    _git("checkout", "-q", "-b", "feat/PROJ-1-login")
    return tmp_path


def test_collect_branch_meta_extracts_branch_and_trailers(repo: Path) -> None:
    out = collect_branch_meta(repo)
    assert out.status.state == "ok"
    assert out.data is not None
    assert out.data.branch == "feat/PROJ-1-login"
    assert out.data.head_sha
    # Last commit on this branch is the initial commit (no further commits made).
    assert out.data.last_commit_subject.startswith("[PROJ-1] initial")
    assert "PROJ-1" in out.data.bracketed_tickets
    assert sorted(out.data.ticket_trailers) == ["APP-2", "PROJ-1"]


def test_collect_branch_meta_falls_back_when_no_main_remote(repo: Path) -> None:
    # No origin/main; resolver should fall back to local main.
    out = collect_branch_meta(repo)
    assert out.data is not None
    assert out.data.base_ref in ("main", "HEAD~1")


def test_collect_branch_meta_failed_outside_repo(tmp_path: Path) -> None:
    out = collect_branch_meta(tmp_path)  # not a git repo
    assert out.status.state == "failed"
    assert "HEAD does not resolve" in (out.status.detail or "")
