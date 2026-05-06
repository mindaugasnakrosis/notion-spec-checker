"""Tests for spec_check.core.collectors.git_diff."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from spec_check.core.collectors.git_diff import (
    GitDiffBundle,
    _looks_like_test_file,
    collect_git_diff,
    parse_unified_diff,
)
from spec_check.core.schema import ParsedDiff
from spec_check.core.snapshot import create_check_dir

# ---------------------------------------------------------------------------
# Test-file heuristic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_foo.py",
        "src/test/test_bar.py",
        "src/__tests__/foo.test.ts",
        "pkg/foo_test.go",
        "ui/components/button.test.tsx",
        "ui/components/button.spec.ts",
        "spec/widget_spec.rb",
    ],
)
def test_looks_like_test_file_recognises_common_layouts(path: str) -> None:
    assert _looks_like_test_file(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "src/main.py",
        "lib/foo.go",
        "ui/Button.tsx",
        "README.md",
    ],
)
def test_looks_like_test_file_rejects_non_test(path: str) -> None:
    assert _looks_like_test_file(path) is False


# ---------------------------------------------------------------------------
# Unified-diff parser
# ---------------------------------------------------------------------------


_SAMPLE_DIFF = """\
diff --git a/src/auth.py b/src/auth.py
index 0000001..0000002 100644
--- a/src/auth.py
+++ b/src/auth.py
@@ -10,3 +10,5 @@ def login():
     pass
+    new_line_one = 1
+    new_line_two = 2
diff --git a/tests/test_auth.py b/tests/test_auth.py
index 0000003..0000004 100644
--- a/tests/test_auth.py
+++ b/tests/test_auth.py
@@ -1,2 +1,3 @@
 import pytest
-from old import login
+from src.auth import login
+
"""


class TestParseUnifiedDiff:
    def test_files_changed_counts_unique_files(self) -> None:
        d = parse_unified_diff(_SAMPLE_DIFF, base_ref="main", head_sha="abcdef1", branch="feat/x")
        assert d.files_changed == 2

    def test_additions_and_deletions_match_lines(self) -> None:
        d = parse_unified_diff(_SAMPLE_DIFF, base_ref="main", head_sha="abcdef1", branch="feat/x")
        assert d.additions == 4
        assert d.deletions == 1

    def test_test_files_detected(self) -> None:
        d = parse_unified_diff(_SAMPLE_DIFF, base_ref="main", head_sha="abcdef1", branch="feat/x")
        assert d.test_files_touched == ["tests/test_auth.py"]

    def test_hunks_record_file_and_added_lines(self) -> None:
        d = parse_unified_diff(_SAMPLE_DIFF, base_ref="main", head_sha="abcdef1", branch="feat/x")
        files = {h.file for h in d.hunks}
        assert files == {"src/auth.py", "tests/test_auth.py"}
        auth_hunk = next(h for h in d.hunks if h.file == "src/auth.py")
        assert any("new_line_one = 1" in line for line in auth_hunk.added_lines)
        # is_test_file flag tracks the heuristic.
        assert auth_hunk.is_test_file is False
        test_hunk = next(h for h in d.hunks if h.file == "tests/test_auth.py")
        assert test_hunk.is_test_file is True

    def test_empty_diff_yields_empty_parsed_diff(self) -> None:
        d = parse_unified_diff("", base_ref="main", head_sha="abcdef1", branch="feat/x")
        assert d.files_changed == 0
        assert d.additions == 0
        assert d.deletions == 0
        assert d.hunks == []
        assert d.test_files_touched == []


# ---------------------------------------------------------------------------
# End-to-end collector against a real throwaway repo
# ---------------------------------------------------------------------------


@pytest.fixture
def repo_with_branch(tmp_path: Path) -> tuple[Path, str, str, str]:
    """Init a repo on ``main``, branch ``feat/x``, add staged + unstaged
    changes, return (repo_path, branch, base_ref, head_sha).
    """
    if shutil.which("git") is None:
        pytest.skip("git not installed")

    repo = tmp_path / "repo"
    repo.mkdir()

    def _git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True, text=True
        ).stdout

    _git("init", "-q", "-b", "main")
    _git("config", "user.email", "test@example.com")
    _git("config", "user.name", "test")
    (repo / "src").mkdir()
    (repo / "src" / "auth.py").write_text("def login():\n    pass\n")
    _git("add", ".")
    _git("commit", "-q", "-m", "initial")

    _git("checkout", "-q", "-b", "feat/x")
    # Committed change on the branch (will show up in recent_commits diff).
    (repo / "src" / "auth.py").write_text("def login():\n    pass\n    return True\n")
    _git("add", "src/auth.py")
    _git("commit", "-q", "-m", "branch commit")

    # Staged change — modify a tracked file and re-add.
    (repo / "src" / "auth.py").write_text(
        "def login():\n    pass\n    return True\n    # staged comment\n"
    )
    _git("add", "src/auth.py")

    # Unstaged change — edit again without re-adding.
    (repo / "src" / "auth.py").write_text(
        "def login():\n    pass\n    return True\n    # staged comment\n    # unstaged\n"
    )

    head_sha = _git("rev-parse", "HEAD").strip()
    return repo, "feat/x", "main", head_sha


def test_collect_git_diff_writes_three_artefacts_and_returns_bundle(
    repo_with_branch: tuple[Path, str, str, str], tmp_path: Path
) -> None:
    repo, branch, base_ref, head_sha = repo_with_branch
    paths = create_check_dir(tmp_path / "snapshots")

    out = collect_git_diff(repo, paths, base_ref=base_ref, branch=branch, head_sha=head_sha)

    assert out.status.state == "ok"
    assert out.status.name == "git_diff"
    assert out.data is not None
    assert isinstance(out.data, GitDiffBundle)

    # All three files written.
    assert paths.diff_staged.exists()
    assert paths.diff_unstaged.exists()
    assert paths.diff_recent_commits.exists()

    # Each is a valid serialised ParsedDiff.
    for p in (paths.diff_staged, paths.diff_unstaged, paths.diff_recent_commits):
        payload = json.loads(p.read_text())
        ParsedDiff.model_validate(payload)


def test_collect_git_diff_unstaged_captures_pending_edit(
    repo_with_branch: tuple[Path, str, str, str], tmp_path: Path
) -> None:
    repo, branch, base_ref, head_sha = repo_with_branch
    paths = create_check_dir(tmp_path / "snapshots")
    out = collect_git_diff(repo, paths, base_ref=base_ref, branch=branch, head_sha=head_sha)
    assert out.data is not None
    # The unstaged comment line is the only addition between staged and unstaged.
    unstaged_added = [line for h in out.data.unstaged.hunks for line in h.added_lines]
    assert any("unstaged" in line for line in unstaged_added)


def test_collect_git_diff_failure_when_path_is_not_a_repo(tmp_path: Path) -> None:
    # tmp_path itself is not a git repo. The collector returns a parsed diff
    # built from empty stdout (git emits nothing useful) — still status="ok"
    # with empty data, *not* a crash. That's the contract.
    paths = create_check_dir(tmp_path / "snapshots")
    out = collect_git_diff(tmp_path, paths, base_ref="main", branch="feat/x", head_sha="abcdef1")
    assert out.status.state == "ok"
    assert out.data is not None
    assert out.data.staged.files_changed == 0
