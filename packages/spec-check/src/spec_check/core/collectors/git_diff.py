"""Collect the working tree's diff against its base ref.

Three artefacts:

- ``diff/staged.json``   — what ``git diff --cached`` shows
- ``diff/unstaged.json`` — what ``git diff`` shows
- ``diff/recent_commits.json`` — the diff of the last N commits on the branch
  (``base_ref..HEAD``), so the rules can see commits that have already
  landed on the branch as well as work-in-progress.

Each artefact is the JSON-serialised :class:`ParsedDiff` for that surface.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from spec_check.core.gitwrap import GitWrapperError, GitWriteRefused, run_git
from spec_check.core.schema import ChangedHunk, CollectorStatus, ParsedDiff
from spec_check.core.snapshot import CheckPaths

from . import CollectorOutput

# ``diff --git a/foo b/foo`` marks a per-file header in unified diff output.
_FILE_HEADER_RE = re.compile(r"^diff --git a/(?P<a>.+?) b/(?P<b>.+)$")
# ``@@ -<a>,<b> +<c>,<d> @@`` marks a hunk; we capture just the +c (new start).
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@")


@dataclass(frozen=True, slots=True)
class GitDiffBundle:
    """All three diff surfaces collected in one run."""

    staged: ParsedDiff
    unstaged: ParsedDiff
    recent_commits: ParsedDiff


def parse_unified_diff(text: str, *, base_ref: str, head_sha: str, branch: str) -> ParsedDiff:
    """Turn ``git diff --no-color`` output into a :class:`ParsedDiff`.

    A small, deliberately-naive unified-diff parser. We only extract what
    rules actually need: per-file hunks, with added and removed lines kept
    verbatim. Binary diffs and rename indicators are handled by tagging the
    hunk's added/removed lists empty rather than failing.
    """
    hunks: list[ChangedHunk] = []
    files: set[str] = set()
    additions = 0
    deletions = 0

    current_file: str | None = None
    current_hunk: dict | None = None

    def _flush_hunk() -> None:
        nonlocal current_hunk
        if current_hunk is None or current_file is None:
            current_hunk = None
            return
        added = current_hunk["added"]
        removed = current_hunk["removed"]
        start = current_hunk["start"]
        end = max(start + max(len(added), 1) - 1, start)
        hunks.append(
            ChangedHunk(
                file=current_file,
                start_line=start,
                end_line=end,
                added_lines=added,
                removed_lines=removed,
                is_test_file=_looks_like_test_file(current_file),
            )
        )
        current_hunk = None

    for raw_line in text.splitlines():
        m_file = _FILE_HEADER_RE.match(raw_line)
        if m_file:
            _flush_hunk()
            # Prefer the b-side (post-change path); falls back to a-side.
            current_file = m_file.group("b") or m_file.group("a")
            files.add(current_file)
            continue

        if raw_line.startswith(("--- ", "+++ ", "index ", "new file mode", "deleted file mode")):
            continue

        m_hunk = _HUNK_RE.match(raw_line)
        if m_hunk:
            _flush_hunk()
            current_hunk = {
                "start": int(m_hunk.group("start")),
                "added": [],
                "removed": [],
            }
            continue

        if current_hunk is None:
            continue

        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            current_hunk["added"].append(raw_line[1:])
            additions += 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            current_hunk["removed"].append(raw_line[1:])
            deletions += 1
        # Context lines (' ' prefix) and '\\ No newline at end of file' are ignored.

    _flush_hunk()

    test_files_touched = sorted({f for f in files if _looks_like_test_file(f)})

    return ParsedDiff(
        base_ref=base_ref,
        head_sha=head_sha,
        branch=branch,
        files_changed=len(files),
        additions=additions,
        deletions=deletions,
        hunks=hunks,
        test_files_touched=test_files_touched,
    )


# Patterns matched against any path component or basename. The cost of being a
# little permissive (a non-test file that happens to be under a ``tests/``
# directory) is tiny — the rules using this only ask "is there *any* test
# touched", not "what does this test cover". Refined later if a rule needs it.
_TEST_PATH_SUBSTRINGS: tuple[str, ...] = (
    "/tests/",
    "/test/",
    "/__tests__/",
    "/spec/",
)
_TEST_FILENAME_PATTERNS: tuple[str, ...] = (
    "test_",  # test_foo.py
    "_test.",  # foo_test.go, foo_test.py
    ".test.",  # foo.test.ts
    ".spec.",  # foo.spec.ts, foo.spec.js
)


def _looks_like_test_file(path: str) -> bool:
    p = path.lower()
    if any(sub in f"/{p}" for sub in _TEST_PATH_SUBSTRINGS):
        return True
    name = p.rsplit("/", 1)[-1]
    return any(pat in name for pat in _TEST_FILENAME_PATTERNS)


def _safe_run(args: list[str], cwd: Path) -> str:
    """Run a read-only git command and return stdout, or empty string on a
    failure that's not the firewall (the firewall's refusals must propagate).
    """
    try:
        result = run_git(args, cwd=cwd, check=False)
    except GitWriteRefused:
        raise
    except GitWrapperError:
        return ""
    return result.stdout


def collect_git_diff(
    repo_path: Path,
    paths: CheckPaths,
    *,
    base_ref: str,
    branch: str,
    head_sha: str,
    recent_commits_n: int = 5,
) -> CollectorOutput[GitDiffBundle]:
    """Collect staged, unstaged, and last-N-commit diffs.

    Returns ``status="ok"`` even if one of the three diffs is empty — that's
    a normal state for a clean working tree. Returns ``status="failed"`` only
    if git itself is unreachable or a firewall refusal escapes (which would
    be a bug).
    """
    try:
        staged_text = _safe_run(["diff", "--cached", "--no-color", "--unified=3"], repo_path)
        unstaged_text = _safe_run(["diff", "--no-color", "--unified=3"], repo_path)
        recent_text = _safe_run(
            ["diff", "--no-color", "--unified=3", f"{base_ref}..HEAD"], repo_path
        )
    except GitWriteRefused as exc:  # firewall escaped — bug, surface loudly
        return CollectorOutput(
            status=CollectorStatus(
                name="git_diff", state="failed", detail=f"git firewall refusal: {exc}"
            )
        )
    except Exception as exc:  # noqa: BLE001 — collector contract: never propagate
        return CollectorOutput(
            status=CollectorStatus(name="git_diff", state="failed", detail=str(exc))
        )

    try:
        staged = parse_unified_diff(
            staged_text, base_ref=base_ref, head_sha=head_sha, branch=branch
        )
        unstaged = parse_unified_diff(
            unstaged_text, base_ref=base_ref, head_sha=head_sha, branch=branch
        )
        recent = parse_unified_diff(
            recent_text, base_ref=base_ref, head_sha=head_sha, branch=branch
        )
    except Exception as exc:  # noqa: BLE001 — parser bug shouldn't kill the run
        return CollectorOutput(
            status=CollectorStatus(name="git_diff", state="failed", detail=f"parse error: {exc}")
        )

    paths.diff_staged.write_text(json.dumps(staged.model_dump(mode="json"), indent=2))
    paths.diff_unstaged.write_text(json.dumps(unstaged.model_dump(mode="json"), indent=2))
    paths.diff_recent_commits.write_text(json.dumps(recent.model_dump(mode="json"), indent=2))
    _ = recent_commits_n  # currently uses base_ref..HEAD; reserved for future paging

    return CollectorOutput(
        status=CollectorStatus(
            name="git_diff", state="ok", artefact_path=str(paths.diff_dir.relative_to(paths.root))
        ),
        data=GitDiffBundle(staged=staged, unstaged=unstaged, recent_commits=recent),
    )
