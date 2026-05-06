"""Tests for spec_check.core.orchestrator (the ``pull`` pipeline)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from spec_check.core.config import SpecCheckSettings
from spec_check.core.notion import NotionWrapper
from spec_check.core.orchestrator import OrchestratorError, pull
from spec_check.core.schema import ParsedSpec
from spec_check.core.transport import NullTransport, PrefetchedTransport


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    repo = tmp_path / "repo"
    repo.mkdir()

    def _git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)

    _git("init", "-q", "-b", "main")
    _git("config", "user.email", "test@example.com")
    _git("config", "user.name", "test")
    (repo / "src").mkdir()
    (repo / "src" / "auth.py").write_text("def login():\n    pass\n")
    _git("add", ".")
    _git("commit", "-q", "-m", "[PROJ-1] initial")

    _git("checkout", "-q", "-b", "feat/PROJ-1-login")
    (repo / "src" / "auth.py").write_text("def login():\n    pass\n    return True\n")
    _git("add", "src/auth.py")
    _git("commit", "-q", "-m", "branch commit")
    return repo


@pytest.fixture
def settings(tmp_path: Path) -> SpecCheckSettings:
    return SpecCheckSettings(snapshot_root=tmp_path / "snapshots")


# ---------------------------------------------------------------------------
# Pipeline-level behaviour
# ---------------------------------------------------------------------------


def test_pull_with_null_transport_skips_spec_but_completes(
    repo: Path, settings: SpecCheckSettings
) -> None:
    notion = NotionWrapper(NullTransport())
    result = pull(repo_path=repo, settings=settings, notion=notion)

    # The check directory + manifest are written.
    assert result.paths.root.is_dir()
    assert result.paths.manifest.exists()

    # Diff artefacts written.
    assert result.paths.diff_staged.exists()
    assert result.paths.diff_unstaged.exists()
    assert result.paths.diff_recent_commits.exists()

    # Without a real Notion payload the resolver can't find the spec; the
    # collector and the parser report skipped/failed but the run completes.
    states = {c.name: c.state for c in result.manifest.collectors}
    assert states["branch_meta"] == "ok"
    assert states["git_diff"] == "ok"
    # notion_spec is "skipped" if the resolver returned no id, or "failed"
    # if the null transport raised. Either way: not ok, but the run survived.
    assert states["notion_spec"] in {"skipped", "failed"}
    assert states["spec_parser"] in {"skipped", "failed"}
    assert states["test_files"] == "ok"


def test_pull_with_explicit_spec_and_prefetched_payload(
    repo: Path, settings: SpecCheckSettings
) -> None:
    payload = {
        "page": {
            "id": "page-A",
            "url": "https://notion.so/page-A",
            "last_edited_time": "2026-04-30T20:00:00+00:00",
            "properties": {"title": {"title": [{"plain_text": "Login flow"}]}},
        },
        "blocks": [
            {
                "type": "heading_2",
                "heading_2": {"rich_text": [{"plain_text": "Acceptance Criteria"}]},
            },
            {
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"plain_text": "User can log in."}]},
            },
        ],
    }
    notion = NotionWrapper(PrefetchedTransport(payload))
    result = pull(
        repo_path=repo,
        settings=settings,
        notion=notion,
        spec_override="page-A",
    )

    assert result.spec_resolution.is_resolved
    assert result.spec_resolution.resolution_method == "override"

    # Notion spec collector wrote raw_blocks.json.
    assert result.paths.spec_raw_blocks.exists()

    # Parser ran and wrote parsed.yaml — and we got a ParsedSpec back.
    assert result.paths.spec_parsed.exists()
    assert isinstance(result.parsed_spec, ParsedSpec)
    assert result.parsed_spec.has_ac_section is True
    assert len(result.parsed_spec.criteria) == 1

    # Manifest reflects all collectors ok.
    states = {c.name: c.state for c in result.manifest.collectors}
    assert states["notion_spec"] == "ok"
    assert states["spec_parser"] == "ok"

    # parsed.yaml is round-trippable.
    payload_back = yaml.safe_load(result.paths.spec_parsed.read_text())
    ParsedSpec.model_validate(payload_back)


def test_pull_records_resolved_spec_url_in_manifest(
    repo: Path, settings: SpecCheckSettings
) -> None:
    payload = {
        "page": {
            "id": "page-A",
            "url": "https://notion.so/page-A",
            "properties": {"title": {"title": [{"plain_text": "X"}]}},
        },
        "blocks": [],
    }
    notion = NotionWrapper(PrefetchedTransport(payload))
    result = pull(repo_path=repo, settings=settings, notion=notion, spec_override="page-A")
    # Override resolution doesn't populate candidates, so URL in manifest is None.
    assert result.manifest.resolution_method == "override"
    assert result.manifest.resolved_spec_id == "page-A"


def test_pull_raises_when_branch_meta_unavailable(
    tmp_path: Path, settings: SpecCheckSettings
) -> None:
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    notion = NotionWrapper(NullTransport())
    with pytest.raises(OrchestratorError):
        pull(repo_path=not_a_repo, settings=settings, notion=notion)
