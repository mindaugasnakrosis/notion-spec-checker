"""The ``spec-check`` CLI.

Step 10 ships the core verbs that the SKILL.md flow (step 17) will lean
on:

    spec-check init                          # write a default config
    spec-check doctor                        # verify prerequisites
    spec-check pull [--branch] [--spec ...]  # one check, no analysis
    spec-check checks ls
    spec-check checks show <id|latest>
    spec-check schema {finding,spec,diff,manifest}

Step 16 layers the skill-level verbs on top:

    spec-check check                         # pull + analyse in one shot
    spec-check analyse <id|latest>
    spec-check report  <id|latest>
    spec-check knowledge {list,show}

All verbs are read-only by name. There are no ``apply`` / ``fix`` /
``update`` / ``post`` verbs and there never will be — see SECURITY.md.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Annotated

import typer
import yaml

from spec_check import __version__
from spec_check.core.analyse import analyse as run_analyse
from spec_check.core.analyse import read_findings
from spec_check.core.config import (
    SpecCheckSettings,
    default_user_config_path,
    load_settings,
    write_user_config,
)
from spec_check.core.gitwrap import GitWrapperError, run_git
from spec_check.core.knowledge import (
    KnowledgeError,
    list_knowledge_docs,
    read_knowledge_doc,
)
from spec_check.core.notion import NotionWrapper
from spec_check.core.orchestrator import OrchestratorError
from spec_check.core.orchestrator import pull as run_pull
from spec_check.core.report import render_report, severity_summary, write_report
from spec_check.core.schema import CheckManifest, Finding, ParsedDiff, ParsedSpec
from spec_check.core.snapshot import (
    list_checks as list_checks_on_disk,
)
from spec_check.core.snapshot import (
    paths_for,
    read_manifest,
    resolve_check_id,
)
from spec_check.core.transport import NullTransport, PrefetchedTransport

app = typer.Typer(
    name="spec-check",
    help="Read-only pre-merge spec review (Notion + git). spec-check is read-only on git AND on Notion.",
    add_completion=False,
    no_args_is_help=True,
)
checks_app = typer.Typer(help="Inspect prior check runs.", no_args_is_help=True)
app.add_typer(checks_app, name="checks")
knowledge_app = typer.Typer(
    help="Inspect the bundled knowledge corpus that grounds the rules.",
    no_args_is_help=True,
)
app.add_typer(knowledge_app, name="knowledge")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_REPO_CONFIG_FILENAME = ".spec-check.yaml"


def _repo_config_path(repo: Path) -> Path | None:
    candidate = repo / _REPO_CONFIG_FILENAME
    return candidate if candidate.exists() else None


def _build_notion_wrapper(spec_payload: Path | None) -> NotionWrapper:
    """Pick the right transport.

    With a payload file → :class:`PrefetchedTransport`. Without → the
    :class:`NullTransport`, which is honest about the fact that the CLI
    has no live MCP connection.
    """
    if spec_payload is None:
        return NotionWrapper(NullTransport())
    return NotionWrapper(PrefetchedTransport.from_file(spec_payload))


def _ok(msg: str) -> None:
    typer.secho(f"✓ {msg}", fg=typer.colors.GREEN)


def _warn(msg: str) -> None:
    typer.secho(f"~ {msg}", fg=typer.colors.YELLOW)


def _fail(msg: str) -> None:
    typer.secho(f"✗ {msg}", fg=typer.colors.RED)


def _info(msg: str) -> None:
    typer.secho(f"ℹ {msg}", fg=typer.colors.BLUE)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def version() -> None:
    """Print the installed spec-check version."""
    typer.echo(__version__)


@app.command()
def init(
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing config.")] = False,
) -> None:
    """Write a default config to the user config path."""
    target = default_user_config_path()
    if target.exists() and not force:
        _warn(f"config already exists at {target}; pass --force to overwrite")
        raise typer.Exit(0)
    write_user_config(SpecCheckSettings(), target)
    _ok(f"wrote {target}")


@app.command()
def doctor(
    repo: Annotated[Path, typer.Option("--repo", help="Repository to probe.", exists=False)] = Path(
        "."
    ),
) -> None:
    """Check prerequisites: git, config, snapshot root, current repo."""
    ok = True

    if shutil.which("git") is None:
        _fail("git is not on PATH")
        ok = False
    else:
        _ok("git available")

    try:
        repo_cfg = _repo_config_path(repo.resolve())
        settings = load_settings(repo_config=repo_cfg)
        _ok(f"config loaded (snapshot_root={settings.snapshot_root})")
    except Exception as exc:  # noqa: BLE001 — diagnostics are user-facing
        _fail(f"config error: {exc}")
        raise typer.Exit(1) from exc

    try:
        settings.snapshot_root.mkdir(parents=True, exist_ok=True)
        _ok("snapshot root writable")
    except OSError as exc:
        _fail(f"snapshot root not writable: {exc}")
        ok = False

    repo = repo.resolve()
    try:
        run_git(["rev-parse", "--is-inside-work-tree"], cwd=repo, check=True)
        _ok(f"inside a git repo at {repo}")
    except GitWrapperError:
        _warn(f"not a git repo (cwd={repo}); ok if doctor is being run elsewhere")

    _info("Notion data is supplied at run time via --spec-payload <path>;")
    _info("run spec-check from inside Claude Code with an MCP-fetched payload,")
    _info("or pass --spec <page-id> when your branch already names the ticket.")

    if not ok:
        raise typer.Exit(1)


@app.command()
def pull(
    branch: Annotated[
        str | None,
        typer.Option("--branch", help="Branch override (defaults to current)."),
    ] = None,
    spec: Annotated[
        str | None,
        typer.Option("--spec", help="Notion page id; bypasses the resolver."),
    ] = None,
    spec_payload: Annotated[
        Path | None,
        typer.Option(
            "--spec-payload",
            help="JSON file with pre-fetched Notion page + blocks (Claude Code drops one here).",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    repo: Annotated[
        Path,
        typer.Option("--repo", help="Repository root.", exists=False),
    ] = Path("."),
) -> None:
    """Snapshot the working tree's diff and the resolved Notion spec."""
    repo = repo.resolve()
    repo_cfg = _repo_config_path(repo)
    settings = load_settings(repo_config=repo_cfg)
    notion = _build_notion_wrapper(spec_payload)

    try:
        result = run_pull(
            repo_path=repo,
            settings=settings,
            notion=notion,
            spec_override=spec,
            base_ref_override=None,
        )
    except OrchestratorError as exc:
        _fail(str(exc))
        raise typer.Exit(1) from exc

    _ok(f"check {result.check_id} written to {result.paths.root}")
    if result.spec_resolution.is_resolved:
        _ok(
            f"spec resolved via {result.spec_resolution.resolution_method}: "
            f"{result.spec_resolution.spec_id}"
        )
    elif result.spec_resolution.resolution_method == "ambiguous":
        _warn(result.spec_resolution.detail)
    else:
        _warn(
            "spec did not resolve. Pass --spec <page-id> or --spec-payload "
            "with a Claude-Code-fetched payload."
        )

    if branch:
        # We don't currently switch branches (we never check out anything —
        # read-only on git), so a --branch override only acts as a label
        # for human eyes. Surface it explicitly instead of silently ignoring.
        _info(f"--branch={branch} recorded for context only; spec-check never switches branches")


@checks_app.command("ls")
def checks_ls(
    repo: Annotated[
        Path, typer.Option("--repo", help="Repository whose .spec-check.yaml to honour.")
    ] = Path("."),
) -> None:
    """List check ids under the configured snapshot root, newest first."""
    settings = load_settings(repo_config=_repo_config_path(repo.resolve()))
    ids = list_checks_on_disk(settings.snapshot_root)
    if not ids:
        _info(f"no checks under {settings.snapshot_root}")
        return
    for cid in ids:
        typer.echo(cid)


@checks_app.command("show")
def checks_show(
    check_id: Annotated[str, typer.Argument(help='Check id, or "latest".')] = "latest",
    repo: Annotated[
        Path, typer.Option("--repo", help="Repository whose .spec-check.yaml to honour.")
    ] = Path("."),
) -> None:
    """Print a check's manifest as YAML."""
    settings = load_settings(repo_config=_repo_config_path(repo.resolve()))
    cid = resolve_check_id(settings.snapshot_root, check_id)
    paths = paths_for(settings.snapshot_root, cid)
    manifest = read_manifest(paths)
    typer.echo(yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False))


_SCHEMA_MODELS: dict[str, type] = {
    "finding": Finding,
    "spec": ParsedSpec,
    "diff": ParsedDiff,
    "manifest": CheckManifest,
}


@app.command()
def schema(
    name: Annotated[
        str,
        typer.Argument(help=f"One of: {', '.join(sorted(_SCHEMA_MODELS))}"),
    ],
) -> None:
    """Print a JSON Schema for one of spec-check's Pydantic models."""
    model = _SCHEMA_MODELS.get(name)
    if model is None:
        _fail(f"unknown schema {name!r}; choose from {sorted(_SCHEMA_MODELS)}")
        raise typer.Exit(2)
    typer.echo(json.dumps(model.model_json_schema(), indent=2))


# ---------------------------------------------------------------------------
# analyse / report / check
# ---------------------------------------------------------------------------


def _print_severity_summary(findings: list[Finding]) -> None:
    counts = severity_summary(findings)
    parts = [f"{counts[k]} {k}" for k in ("Critical", "High", "Medium", "Low", "Info") if counts[k]]
    if parts:
        _info("findings: " + ", ".join(parts))
    else:
        _ok("no findings")


@app.command()
def analyse(
    check_id: Annotated[str, typer.Argument(help='Check id, or "latest".')] = "latest",
    repo: Annotated[
        Path, typer.Option("--repo", help="Repository whose .spec-check.yaml to honour.")
    ] = Path("."),
) -> None:
    """Run every rule against a previously-pulled check; write findings.yaml."""
    settings = load_settings(repo_config=_repo_config_path(repo.resolve()))
    cid = resolve_check_id(settings.snapshot_root, check_id)
    paths = paths_for(settings.snapshot_root, cid)
    document = run_analyse(paths=paths, settings=settings)
    _ok(f"findings written to {paths.findings}")
    _print_severity_summary(document.findings)


@app.command()
def report(
    check_id: Annotated[str, typer.Argument(help='Check id, or "latest".')] = "latest",
    repo: Annotated[
        Path, typer.Option("--repo", help="Repository whose .spec-check.yaml to honour.")
    ] = Path("."),
    stdout: Annotated[
        bool,
        typer.Option("--stdout", help="Also print the report to stdout."),
    ] = False,
) -> None:
    """Render report.md from a check's findings.yaml."""
    settings = load_settings(repo_config=_repo_config_path(repo.resolve()))
    cid = resolve_check_id(settings.snapshot_root, check_id)
    paths = paths_for(settings.snapshot_root, cid)
    manifest = read_manifest(paths)
    try:
        document = read_findings(paths)
    except FileNotFoundError as exc:
        _fail(str(exc))
        _info("did you run `spec-check analyse` first?")
        raise typer.Exit(1) from exc
    body = render_report(manifest=manifest, document=document)
    write_report(paths, body)
    _ok(f"report written to {paths.report}")
    if stdout:
        typer.echo(body)


@app.command()
def check(
    spec: Annotated[
        str | None, typer.Option("--spec", help="Notion page id; bypasses the resolver.")
    ] = None,
    spec_payload: Annotated[
        Path | None,
        typer.Option(
            "--spec-payload",
            help="JSON file with pre-fetched Notion page + blocks.",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    repo: Annotated[
        Path, typer.Option("--repo", help="Repository root.", exists=False)
    ] = Path("."),
    stdout: Annotated[
        bool,
        typer.Option("--stdout", help="Also print the rendered report to stdout."),
    ] = False,
) -> None:
    """One-shot: pull, analyse, render report. The skill-level entry point."""
    repo = repo.resolve()
    settings = load_settings(repo_config=_repo_config_path(repo))
    notion = _build_notion_wrapper(spec_payload)

    try:
        pull_result = run_pull(
            repo_path=repo,
            settings=settings,
            notion=notion,
            spec_override=spec,
            base_ref_override=None,
        )
    except OrchestratorError as exc:
        _fail(str(exc))
        raise typer.Exit(1) from exc

    _ok(f"check {pull_result.check_id} written to {pull_result.paths.root}")

    document = run_analyse(paths=pull_result.paths, settings=settings)
    body = render_report(manifest=pull_result.manifest, document=document)
    write_report(pull_result.paths, body)
    _ok(f"report written to {pull_result.paths.report}")
    _print_severity_summary(document.findings)
    if stdout:
        typer.echo(body)


# ---------------------------------------------------------------------------
# knowledge list / show
# ---------------------------------------------------------------------------


@knowledge_app.command("list")
def knowledge_list() -> None:
    """List every knowledge doc in the bundled corpus."""
    docs = list_knowledge_docs()
    if not docs:
        _warn("knowledge corpus is empty")
        return
    for doc in docs:
        cited = ", ".join(doc.frontmatter.cited_by) or "(uncited)"
        url = doc.frontmatter.canonical_url or "(authored)"
        typer.echo(f"{doc.filename}\t{doc.frontmatter.name}\t{url}\t{cited}")


@knowledge_app.command("show")
def knowledge_show(
    name: Annotated[
        str,
        typer.Argument(help="Knowledge doc filename (with or without .md)."),
    ],
) -> None:
    """Print one knowledge doc verbatim (frontmatter + body)."""
    try:
        doc = read_knowledge_doc(name)
    except KnowledgeError as exc:
        _fail(str(exc))
        raise typer.Exit(1) from exc
    fm_dump = yaml.safe_dump(doc.frontmatter.model_dump(mode="json"), sort_keys=False).rstrip()
    typer.echo("---")
    typer.echo(fm_dump)
    typer.echo("---")
    typer.echo("")
    typer.echo(doc.body)


def main() -> None:  # pragma: no cover — entry point
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
