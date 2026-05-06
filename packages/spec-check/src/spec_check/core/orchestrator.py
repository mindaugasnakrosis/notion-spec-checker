"""The ``pull`` orchestrator: one check from end to end (no rules yet).

Pipeline (each step's failure is a manifest entry, not a crash):

1. Collect branch metadata. If this fails the run cannot continue — without
   a branch + head sha + base ref there's nothing to diff against.
2. Resolve the Notion spec (override → ticket key → trailer → fuzzy slug).
3. Create the check directory under the snapshot root.
4. Run the git diff collector → write ``diff/*.json``.
5. Run the Notion spec collector → write ``spec/raw_blocks.json``.
6. Parse the raw blocks → write ``spec/parsed.yaml``.
7. Run the test_files collector over the staged diff.
8. Build and write the :class:`CheckManifest`.

The result is a :class:`PullResult` the CLI (and the higher-level skill
``check`` command in step 16) can render to the user.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from spec_check import __version__
from spec_check.core.collectors.branch_meta import collect_branch_meta
from spec_check.core.collectors.git_diff import collect_git_diff
from spec_check.core.collectors.notion_spec import collect_notion_spec
from spec_check.core.collectors.test_files import collect_test_files
from spec_check.core.config import SpecCheckSettings
from spec_check.core.notion import NotionWrapper
from spec_check.core.resolver import SpecResolution, resolve_spec
from spec_check.core.schema import (
    BranchMetaSnapshot,
    CheckManifest,
    CollectorStatus,
    ParsedSpec,
)
from spec_check.core.snapshot import CheckPaths, create_check_dir, write_manifest
from spec_check.core.spec_parser import parse_spec


class OrchestratorError(RuntimeError):
    """Raised when the orchestrator can't even begin (branch meta missing)."""


@dataclass(frozen=True, slots=True)
class PullResult:
    check_id: str
    paths: CheckPaths
    manifest: CheckManifest
    spec_resolution: SpecResolution
    parsed_spec: ParsedSpec | None  # None when notion_spec was skipped/failed
    test_files_touched: list[str]


def pull(
    *,
    repo_path: Path,
    settings: SpecCheckSettings,
    notion: NotionWrapper,
    spec_override: str | None = None,
    base_ref_override: str | None = None,
    snapshot_root_override: Path | None = None,
) -> PullResult:
    """Run one check, write its artefacts, return the bundle."""
    snapshot_root = (
        snapshot_root_override if snapshot_root_override is not None else settings.snapshot_root
    )

    # 1. Branch meta — load-bearing.
    branch_out = collect_branch_meta(repo_path, base_ref_override=base_ref_override)
    if branch_out.data is None:
        raise OrchestratorError(branch_out.status.detail or "branch_meta collector failed")
    branch_meta = branch_out.data

    # 2. Resolve the spec.
    resolution = resolve_spec(notion, branch_meta, settings, explicit_spec_id=spec_override)

    # 3. Lay down the check directory.
    paths = create_check_dir(snapshot_root)

    # 4. Diff collector.
    diff_out = collect_git_diff(
        repo_path,
        paths,
        base_ref=branch_meta.base_ref,
        branch=branch_meta.branch,
        head_sha=branch_meta.head_sha,
    )

    # 5. Notion spec collector.
    notion_out = collect_notion_spec(notion, resolution.spec_id or "", paths)

    # 6. Parse the raw blocks if we got any.
    parsed_spec: ParsedSpec | None = None
    parse_status: CollectorStatus | None = None
    if notion_out.data is not None:
        try:
            parsed_spec = parse_spec(notion_out.data, settings)
            paths.spec_parsed.write_text(
                yaml.safe_dump(parsed_spec.model_dump(mode="json"), sort_keys=False)
            )
            parse_status = CollectorStatus(
                name="spec_parser",
                state="ok",
                artefact_path=str(paths.spec_parsed.relative_to(paths.root)),
            )
        except Exception as exc:  # noqa: BLE001 — manifest entry instead of crash
            parse_status = CollectorStatus(
                name="spec_parser", state="failed", detail=f"parse error: {exc}"
            )
    else:
        parse_status = CollectorStatus(
            name="spec_parser",
            state="skipped",
            detail="no raw spec blocks to parse",
        )

    # 7. Test files (over the staged diff). Skipped if git_diff failed.
    if diff_out.data is not None:
        test_files_out = collect_test_files(diff_out.data.staged)
    else:
        test_files_out = type(diff_out)(  # CollectorOutput[list[str]]
            status=CollectorStatus(
                name="test_files",
                state="skipped",
                detail="git_diff failed; nothing to derive from",
            ),
            data=None,
        )

    # 7b. Persist a distilled branch meta snapshot — analyse needs
    # ``referenced_tickets`` and ``branch_created_at`` and the manifest
    # itself doesn't carry them.
    branch_meta_snapshot = BranchMetaSnapshot(
        branch=branch_meta.branch,
        head_sha=branch_meta.head_sha,
        base_ref=branch_meta.base_ref,
        last_commit_subject=branch_meta.last_commit_subject,
        last_commit_body=branch_meta.last_commit_body,
        referenced_tickets=sorted(
            {*branch_meta.ticket_trailers, *branch_meta.bracketed_tickets}
        ),
        branch_created_at=branch_meta.branch_created_at,
    )
    paths.branch_meta.write_text(
        yaml.safe_dump(branch_meta_snapshot.model_dump(mode="json"), sort_keys=False)
    )

    # 8. Manifest.
    resolved_url = resolution.candidates[0].url if resolution.candidates else None
    manifest = CheckManifest(
        check_id=paths.check_id,
        created_at=datetime.now(UTC),
        spec_check_version=__version__,
        branch=branch_meta.branch,
        base_ref=branch_meta.base_ref,
        head_sha=branch_meta.head_sha,
        resolved_spec_id=resolution.spec_id,
        resolved_spec_url=resolved_url,
        resolution_method=resolution.resolution_method,
        collectors=[
            branch_out.status,
            diff_out.status,
            notion_out.status,
            parse_status,
            test_files_out.status,
        ],
    )
    write_manifest(paths, manifest)

    return PullResult(
        check_id=paths.check_id,
        paths=paths,
        manifest=manifest,
        spec_resolution=resolution,
        parsed_spec=parsed_spec,
        test_files_touched=test_files_out.data or [],
    )
