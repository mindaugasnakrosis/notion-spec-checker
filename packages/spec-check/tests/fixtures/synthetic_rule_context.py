"""Compose a :class:`RuleContext` from synthetic spec/diff/manifest pieces."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from spec_check.core.config import SpecCheckSettings
from spec_check.core.schema import CheckManifest, ParsedDiff, ParsedSpec
from spec_check.rules.base import RuleContext

from tests.fixtures.synthetic_manifest import make_manifest


def make_context(
    *,
    parsed_spec: ParsedSpec | None = None,
    parsed_diff: ParsedDiff | None = None,
    manifest: CheckManifest | None = None,
    settings: SpecCheckSettings | None = None,
    spec_resolution_method: str = "override",
    test_files_touched: list[str] | None = None,
    referenced_tickets: tuple[str, ...] = (),
    branch_created_at: datetime | None = None,
    snapshot_root: Path | None = None,
) -> RuleContext:
    if settings is None:
        # Avoid touching real user data dirs in tests.
        settings = SpecCheckSettings(
            snapshot_root=snapshot_root or Path("/tmp/spec-check-test-snapshots"),
        )
    if manifest is None:
        manifest = make_manifest(resolution_method=spec_resolution_method)
    return RuleContext(
        parsed_spec=parsed_spec,
        parsed_diff=parsed_diff,
        manifest=manifest,
        settings=settings,
        spec_resolution_method=spec_resolution_method,
        test_files_touched=test_files_touched if test_files_touched is not None else [],
        referenced_tickets=referenced_tickets,
        branch_created_at=branch_created_at,
    )
