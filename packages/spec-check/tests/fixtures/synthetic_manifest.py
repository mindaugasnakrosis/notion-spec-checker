"""Tiny :class:`CheckManifest` factory for rule tests."""

from __future__ import annotations

from datetime import UTC, datetime

from spec_check.core.schema import CheckManifest, CollectorStatus


def make_manifest(
    *,
    check_id: str = "2026-05-03T12-00-00Z-abcdef",
    branch: str = "feat/PROJ-1-login",
    base_ref: str = "origin/main",
    head_sha: str = "deadbeef",
    resolved_spec_id: str | None = "page-A",
    resolved_spec_url: str | None = "https://notion.so/page-A",
    resolution_method: str = "override",
    collectors: list[CollectorStatus] | None = None,
) -> CheckManifest:
    return CheckManifest(
        check_id=check_id,
        created_at=datetime(2026, 5, 3, 12, 0, 0, tzinfo=UTC),
        spec_check_version="0.0.0",
        branch=branch,
        base_ref=base_ref,
        head_sha=head_sha,
        resolved_spec_id=resolved_spec_id,
        resolved_spec_url=resolved_spec_url,
        resolution_method=resolution_method,
        collectors=collectors
        or [CollectorStatus(name="branch_meta", state="ok")],
    )
