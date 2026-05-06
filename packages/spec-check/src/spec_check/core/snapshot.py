"""On-disk layout for one ``spec-check`` run.

A "check" is a single invocation of ``spec-check pull`` (or its one-shot form
``spec-check check``). Each check writes to a timestamped directory under the
configured snapshot root::

    <snapshot_root>/<check_id>/
        manifest.yaml         # CheckManifest — read by `analyse`
        branch_meta.yaml      # BranchMetaSnapshot — read by `analyse`
        diff/
            staged.json
            unstaged.json
            recent_commits.json
        spec/
            raw_blocks.json   # raw Notion blocks from the MCP
            parsed.yaml       # ParsedSpec
        report.md
        findings.yaml

Two responsibilities live here:

1. **On-disk layout**: build a fresh check directory, find an existing one,
   list checks, write/read the manifest. The artefact files inside (``diff/``,
   ``spec/``, ``report.md``, ``findings.yaml``) are written by their own
   layers — this module just publishes the paths and creates the parents.

2. **Snapshot-root sandbox**: every path computed by this module is verified
   to live underneath the configured snapshot root. A ``check_id`` like
   ``../../etc`` cannot escape. ``ensure_within_root`` is the gate.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from spec_check.core.schema import CheckManifest

LATEST_ALIAS = "latest"

# Layout subpaths, named once here so the rest of the project can import them
# rather than re-spelling string literals.
MANIFEST_FILENAME = "manifest.yaml"
BRANCH_META_FILENAME = "branch_meta.yaml"
DIFF_DIR = "diff"
DIFF_STAGED = "staged.json"
DIFF_UNSTAGED = "unstaged.json"
DIFF_RECENT_COMMITS = "recent_commits.json"
SPEC_DIR = "spec"
SPEC_RAW_BLOCKS = "raw_blocks.json"
SPEC_PARSED = "parsed.yaml"
REPORT_FILENAME = "report.md"
FINDINGS_FILENAME = "findings.yaml"

# Generated check_id shape: ``2026-04-30T20-31-12Z-abc123``. ISO-ish so the
# directory listing is naturally sorted by time; suffix to disambiguate two
# checks created in the same second.
_CHECK_ID_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z-[a-f0-9]{6,}$")


class SnapshotPathError(RuntimeError):
    """Raised when a path computation would escape the snapshot root or when a
    check directory's structure is invalid.
    """


@dataclass(frozen=True, slots=True)
class CheckPaths:
    """All artefact paths inside one check directory. Pure data — owning the
    files is up to the layer that writes them.
    """

    root: Path
    check_id: str

    @property
    def manifest(self) -> Path:
        return self.root / MANIFEST_FILENAME

    @property
    def branch_meta(self) -> Path:
        return self.root / BRANCH_META_FILENAME

    @property
    def diff_dir(self) -> Path:
        return self.root / DIFF_DIR

    @property
    def diff_staged(self) -> Path:
        return self.diff_dir / DIFF_STAGED

    @property
    def diff_unstaged(self) -> Path:
        return self.diff_dir / DIFF_UNSTAGED

    @property
    def diff_recent_commits(self) -> Path:
        return self.diff_dir / DIFF_RECENT_COMMITS

    @property
    def spec_dir(self) -> Path:
        return self.root / SPEC_DIR

    @property
    def spec_raw_blocks(self) -> Path:
        return self.spec_dir / SPEC_RAW_BLOCKS

    @property
    def spec_parsed(self) -> Path:
        return self.spec_dir / SPEC_PARSED

    @property
    def report(self) -> Path:
        return self.root / REPORT_FILENAME

    @property
    def findings(self) -> Path:
        return self.root / FINDINGS_FILENAME


def generate_check_id(now: datetime | None = None) -> str:
    """Build a fresh ``YYYY-MM-DDTHH-MM-SSZ-<hex>`` check id.

    Colons are replaced with hyphens because POSIX paths technically allow
    them but Windows does not — this id may end up shared between platforms.
    """
    when = (now or datetime.now(UTC)).astimezone(UTC)
    timestamp = when.strftime("%Y-%m-%dT%H-%M-%SZ")
    suffix = secrets.token_hex(3)
    return f"{timestamp}-{suffix}"


def is_well_formed_check_id(check_id: str) -> bool:
    return bool(_CHECK_ID_PATTERN.match(check_id))


def ensure_within_root(candidate: Path, root: Path) -> Path:
    """Resolve ``candidate`` and refuse if it isn't strictly underneath
    ``root``.

    Both paths are resolved without requiring them to exist on disk
    (``strict=False``) — we want this to work for paths that ``pull`` is
    about to create. The check uses :meth:`Path.is_relative_to`, which
    handles ``..`` traversal and absolute-path overrides cleanly.
    """
    root_resolved = Path(root).expanduser().resolve(strict=False)
    candidate_resolved = Path(candidate).expanduser().resolve(strict=False)
    if candidate_resolved == root_resolved:
        raise SnapshotPathError(
            f"path {candidate!r} resolves to the snapshot root itself; refusing"
        )
    if not candidate_resolved.is_relative_to(root_resolved):
        raise SnapshotPathError(
            f"path {candidate!r} resolves outside snapshot root {root_resolved!r}; refusing"
        )
    return candidate_resolved


def paths_for(snapshot_root: Path, check_id: str) -> CheckPaths:
    """Compute the path layout for one check, with sandbox enforcement.

    The check id is rejected if it contains path separators or parent-dir
    references, *and* the resolved directory is verified to live under the
    snapshot root. Two layers of the same check, by design.
    """
    if not check_id or check_id == LATEST_ALIAS:
        raise SnapshotPathError(f"invalid check_id {check_id!r}")
    if "/" in check_id or "\\" in check_id or check_id in {".", ".."}:
        raise SnapshotPathError(f"check_id {check_id!r} contains a path separator")
    if ".." in Path(check_id).parts:
        raise SnapshotPathError(f"check_id {check_id!r} contains a parent reference")

    candidate = Path(snapshot_root) / check_id
    resolved_root = ensure_within_root(candidate, snapshot_root)
    return CheckPaths(root=resolved_root, check_id=check_id)


def create_check_dir(
    snapshot_root: Path,
    *,
    check_id: str | None = None,
    now: datetime | None = None,
) -> CheckPaths:
    """Build a fresh check directory under ``snapshot_root``.

    The snapshot root itself is created if missing. The check directory and
    its ``diff/`` and ``spec/`` subdirectories are created exclusively —
    if the check id collides with an existing directory the call fails so
    we never silently overwrite a previous run.
    """
    snapshot_root = Path(snapshot_root).expanduser().resolve(strict=False)
    snapshot_root.mkdir(parents=True, exist_ok=True)

    cid = check_id if check_id is not None else generate_check_id(now=now)
    paths = paths_for(snapshot_root, cid)

    paths.root.mkdir(parents=True, exist_ok=False)
    paths.diff_dir.mkdir()
    paths.spec_dir.mkdir()
    return paths


def write_manifest(paths: CheckPaths, manifest: CheckManifest) -> Path:
    """Serialise a :class:`CheckManifest` to ``manifest.yaml``.

    ``manifest.check_id`` must match ``paths.check_id`` — a mismatch is a
    bug in the caller, not a user error.
    """
    if manifest.check_id != paths.check_id:
        raise SnapshotPathError(
            f"manifest.check_id={manifest.check_id!r} does not match "
            f"paths.check_id={paths.check_id!r}"
        )
    payload = manifest.model_dump(mode="json")
    with paths.manifest.open("w") as fh:
        yaml.safe_dump(payload, fh, sort_keys=False)
    return paths.manifest


def read_manifest(paths: CheckPaths) -> CheckManifest:
    if not paths.manifest.exists():
        raise SnapshotPathError(f"manifest missing at {paths.manifest}")
    with paths.manifest.open() as fh:
        data = yaml.safe_load(fh) or {}
    return CheckManifest.model_validate(data)


def list_checks(snapshot_root: Path) -> list[str]:
    """List well-formed check ids under ``snapshot_root``, newest first.

    Anything that doesn't match :data:`_CHECK_ID_PATTERN` is silently skipped:
    the directory is user data and may legitimately contain unrelated entries.
    """
    snapshot_root = Path(snapshot_root).expanduser().resolve(strict=False)
    if not snapshot_root.exists():
        return []
    entries = [
        entry.name
        for entry in snapshot_root.iterdir()
        if entry.is_dir() and is_well_formed_check_id(entry.name)
    ]
    # The id format is naturally lexicographically sortable in chronological
    # order, so reverse-sort gives newest-first.
    return sorted(entries, reverse=True)


def resolve_check_id(snapshot_root: Path, check_id_or_latest: str) -> str:
    """Resolve ``"latest"`` to the most recent check id; pass other ids through
    after well-formedness check.
    """
    if check_id_or_latest == LATEST_ALIAS:
        checks = list_checks(snapshot_root)
        if not checks:
            raise SnapshotPathError(f"no checks under {snapshot_root}")
        return checks[0]
    if not is_well_formed_check_id(check_id_or_latest):
        raise SnapshotPathError(
            f"check_id {check_id_or_latest!r} is not well-formed and is not 'latest'"
        )
    return check_id_or_latest
