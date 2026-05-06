"""Tests for the skill-level CLI verbs: analyse, report, check, knowledge."""

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
    _git("checkout", "-q", "-b", "feat/PROJ-1-login")
    return repo


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    user_cfg_dir = tmp_path / "user-config"
    snap_root = tmp_path / "snapshots"
    user_cfg_dir.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(user_cfg_dir))
    monkeypatch.setenv("SPEC_CHECK_SNAPSHOT_ROOT", str(snap_root))
    return tmp_path


def _payload(tmp_path: Path) -> Path:
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


# ---------------------------------------------------------------------------
# analyse
# ---------------------------------------------------------------------------


def test_analyse_after_pull_writes_findings(
    runner: CliRunner, repo: Path, tmp_path: Path
) -> None:
    payload = _payload(tmp_path)
    pull_out = runner.invoke(
        app, ["pull", "--repo", str(repo), "--spec", "page-A", "--spec-payload", str(payload)]
    )
    assert pull_out.exit_code == 0, pull_out.stdout

    out = runner.invoke(app, ["analyse", "latest"])
    assert out.exit_code == 0, out.stdout
    assert "findings written to" in out.stdout

    snap_root = Path(tmp_path / "snapshots")
    findings_files = list(snap_root.rglob("findings.yaml"))
    assert len(findings_files) == 1
    parsed = yaml.safe_load(findings_files[0].read_text())
    assert parsed["check_id"]
    assert isinstance(parsed["findings"], list)


def test_analyse_with_no_checks_exits_one(runner: CliRunner) -> None:
    out = runner.invoke(app, ["analyse", "latest"])
    assert out.exit_code != 0


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def test_report_renders_after_analyse(runner: CliRunner, repo: Path, tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    runner.invoke(
        app, ["pull", "--repo", str(repo), "--spec", "page-A", "--spec-payload", str(payload)]
    )
    runner.invoke(app, ["analyse", "latest"])

    out = runner.invoke(app, ["report", "latest", "--stdout"])
    assert out.exit_code == 0, out.stdout
    assert "# spec-check report" in out.stdout
    assert "feat/PROJ-1-login" in out.stdout

    snap_root = Path(tmp_path / "snapshots")
    report_files = list(snap_root.rglob("report.md"))
    assert len(report_files) == 1
    body = report_files[0].read_text()
    assert body.startswith("# spec-check report")


def test_report_without_findings_exits_one(runner: CliRunner, repo: Path, tmp_path: Path) -> None:
    # pull only, no analyse → findings.yaml is missing
    payload = _payload(tmp_path)
    runner.invoke(
        app, ["pull", "--repo", str(repo), "--spec", "page-A", "--spec-payload", str(payload)]
    )
    out = runner.invoke(app, ["report", "latest"])
    assert out.exit_code == 1
    assert "findings.yaml missing" in out.stdout


# ---------------------------------------------------------------------------
# check (one-shot)
# ---------------------------------------------------------------------------


def test_check_does_pull_analyse_and_report(
    runner: CliRunner, repo: Path, tmp_path: Path
) -> None:
    payload = _payload(tmp_path)
    out = runner.invoke(
        app,
        ["check", "--repo", str(repo), "--spec", "page-A", "--spec-payload", str(payload)],
    )
    assert out.exit_code == 0, out.stdout
    assert "check " in out.stdout
    assert "report written to" in out.stdout

    snap_root = Path(tmp_path / "snapshots")
    assert list(snap_root.rglob("findings.yaml"))
    assert list(snap_root.rglob("report.md"))


def test_check_stdout_prints_report(runner: CliRunner, repo: Path, tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    out = runner.invoke(
        app,
        [
            "check",
            "--repo",
            str(repo),
            "--spec",
            "page-A",
            "--spec-payload",
            str(payload),
            "--stdout",
        ],
    )
    assert out.exit_code == 0
    assert "# spec-check report" in out.stdout


# ---------------------------------------------------------------------------
# knowledge list / show
# ---------------------------------------------------------------------------


def test_knowledge_list_includes_known_docs(runner: CliRunner) -> None:
    out = runner.invoke(app, ["knowledge", "list"])
    assert out.exit_code == 0, out.stdout
    assert "invest-criteria.md" in out.stdout
    assert "notion-page-conventions.md" in out.stdout
    assert "spec-drift.md" in out.stdout
    assert "ambiguity-in-acceptance-criteria.md" in out.stdout
    assert "observable-acceptance-criteria.md" in out.stdout


def test_knowledge_show_prints_frontmatter_and_body(runner: CliRunner) -> None:
    out = runner.invoke(app, ["knowledge", "show", "invest-criteria"])
    assert out.exit_code == 0
    assert "name: INVEST criteria for user stories" in out.stdout
    assert "Bill Wake" in out.stdout
    assert "S – Small" in out.stdout


def test_knowledge_show_supports_full_filename(runner: CliRunner) -> None:
    out = runner.invoke(app, ["knowledge", "show", "spec-drift.md"])
    assert out.exit_code == 0
    assert "Spec drift after branch creation" in out.stdout


def test_knowledge_show_unknown_exits_one(runner: CliRunner) -> None:
    out = runner.invoke(app, ["knowledge", "show", "no-such-doc"])
    assert out.exit_code == 1
    assert "not found" in out.stdout


def test_knowledge_show_rejects_path_traversal(runner: CliRunner) -> None:
    out = runner.invoke(app, ["knowledge", "show", "../../etc/passwd"])
    assert out.exit_code == 1
    assert "invalid knowledge filename" in out.stdout
