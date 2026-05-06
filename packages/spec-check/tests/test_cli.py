"""Tests for the spec-check CLI."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from spec_check.cli import app
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


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
    (repo / "README.md").write_text("hi\n")
    _git("add", "README.md")
    _git("commit", "-q", "-m", "initial")
    _git("checkout", "-q", "-b", "feat/x")
    return repo


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Sandbox the user config + snapshot root so CLI tests don't touch real
    user data. Two env vars point spec-check at scratch directories.
    """
    user_cfg_dir = tmp_path / "user-config"
    snap_root = tmp_path / "snapshots"
    user_cfg_dir.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(user_cfg_dir))
    monkeypatch.setenv("SPEC_CHECK_SNAPSHOT_ROOT", str(snap_root))
    return tmp_path


# ---------------------------------------------------------------------------
# version / init / doctor
# ---------------------------------------------------------------------------


def test_version_prints_a_version_string(runner: CliRunner) -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip()


def test_init_writes_config_then_refuses_overwrite(runner: CliRunner, isolated_paths: Path) -> None:
    out = runner.invoke(app, ["init"])
    assert out.exit_code == 0
    # Re-run without --force is a no-op (warning, exit 0).
    out2 = runner.invoke(app, ["init"])
    assert out2.exit_code == 0
    assert "already exists" in out2.stdout
    # With --force, succeeds again.
    out3 = runner.invoke(app, ["init", "--force"])
    assert out3.exit_code == 0


def test_doctor_runs_inside_a_repo(runner: CliRunner, repo: Path) -> None:
    result = runner.invoke(app, ["doctor", "--repo", str(repo)])
    assert result.exit_code == 0
    assert "git available" in result.stdout
    assert "snapshot root writable" in result.stdout
    assert "inside a git repo" in result.stdout


def test_doctor_outside_a_repo_warns_but_succeeds(runner: CliRunner, tmp_path: Path) -> None:
    elsewhere = tmp_path / "not-a-repo"
    elsewhere.mkdir()
    result = runner.invoke(app, ["doctor", "--repo", str(elsewhere)])
    assert result.exit_code == 0
    assert "not a git repo" in result.stdout


# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------


def test_schema_finding_is_valid_json(runner: CliRunner) -> None:
    result = runner.invoke(app, ["schema", "finding"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["title"] == "Finding"


def test_schema_unknown_name_exits_two(runner: CliRunner) -> None:
    result = runner.invoke(app, ["schema", "wibble"])
    assert result.exit_code == 2
    assert "unknown schema" in result.stdout


# ---------------------------------------------------------------------------
# pull / checks ls / checks show
# ---------------------------------------------------------------------------


def _write_payload(tmp_path: Path) -> Path:
    """A minimal Notion-shaped payload for --spec-payload."""
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
    path = tmp_path / "payload.json"
    path.write_text(json.dumps(payload))
    return path


def test_pull_with_payload_writes_check_and_resolves_spec(
    runner: CliRunner, repo: Path, tmp_path: Path
) -> None:
    payload_path = _write_payload(tmp_path)
    result = runner.invoke(
        app,
        [
            "pull",
            "--repo",
            str(repo),
            "--spec",
            "page-A",
            "--spec-payload",
            str(payload_path),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "check" in result.stdout
    assert "spec resolved via override" in result.stdout


def test_checks_ls_lists_run_we_just_did(runner: CliRunner, repo: Path, tmp_path: Path) -> None:
    payload_path = _write_payload(tmp_path)
    runner.invoke(
        app,
        [
            "pull",
            "--repo",
            str(repo),
            "--spec",
            "page-A",
            "--spec-payload",
            str(payload_path),
        ],
    )
    out = runner.invoke(app, ["checks", "ls"])
    assert out.exit_code == 0
    assert out.stdout.strip(), "expected at least one check id in output"


def test_checks_show_latest_prints_manifest_yaml(
    runner: CliRunner, repo: Path, tmp_path: Path
) -> None:
    payload_path = _write_payload(tmp_path)
    runner.invoke(
        app,
        [
            "pull",
            "--repo",
            str(repo),
            "--spec",
            "page-A",
            "--spec-payload",
            str(payload_path),
        ],
    )
    out = runner.invoke(app, ["checks", "show", "latest"])
    assert out.exit_code == 0
    parsed = yaml.safe_load(out.stdout)
    assert parsed["resolved_spec_id"] == "page-A"
    assert parsed["resolution_method"] == "override"


def test_pull_outside_repo_exits_one(runner: CliRunner, tmp_path: Path) -> None:
    elsewhere = tmp_path / "not-a-repo"
    elsewhere.mkdir()
    result = runner.invoke(app, ["pull", "--repo", str(elsewhere)])
    assert result.exit_code == 1
