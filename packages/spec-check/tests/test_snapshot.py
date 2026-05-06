"""Tests for spec_check.core.snapshot."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from spec_check.core.schema import CheckManifest, CollectorStatus
from spec_check.core.snapshot import (
    LATEST_ALIAS,
    CheckPaths,
    SnapshotPathError,
    create_check_dir,
    ensure_within_root,
    generate_check_id,
    is_well_formed_check_id,
    list_checks,
    paths_for,
    read_manifest,
    resolve_check_id,
    write_manifest,
)

# ---------------------------------------------------------------------------
# check_id generation + well-formedness
# ---------------------------------------------------------------------------


class TestCheckId:
    def test_generated_id_is_well_formed(self) -> None:
        cid = generate_check_id()
        assert is_well_formed_check_id(cid)

    def test_generated_id_uses_supplied_clock(self) -> None:
        when = datetime(2026, 4, 30, 20, 31, 12, tzinfo=UTC)
        cid = generate_check_id(now=when)
        assert cid.startswith("2026-04-30T20-31-12Z-")

    def test_two_generations_produce_distinct_ids(self) -> None:
        when = datetime(2026, 4, 30, 20, 31, 12, tzinfo=UTC)
        a = generate_check_id(now=when)
        b = generate_check_id(now=when)
        # Same timestamp, but the random suffix avoids collision.
        assert a != b

    @pytest.mark.parametrize(
        "candidate",
        [
            "",
            "latest",
            "2026-04-30",
            "abc",
            "2026-04-30T20-31-12Z",  # missing suffix
            "2026-04-30T20-31-12Z-",  # empty suffix
            "2026-04-30T20-31-12Z-zz",  # non-hex suffix
        ],
    )
    def test_invalid_ids_rejected_by_predicate(self, candidate: str) -> None:
        assert is_well_formed_check_id(candidate) is False


# ---------------------------------------------------------------------------
# Sandbox: ensure_within_root + paths_for
# ---------------------------------------------------------------------------


class TestSandbox:
    def test_path_within_root_accepted(self, tmp_path: Path) -> None:
        candidate = tmp_path / "checks" / "abc"
        out = ensure_within_root(candidate, tmp_path)
        assert out == candidate.resolve()

    def test_root_itself_refused(self, tmp_path: Path) -> None:
        with pytest.raises(SnapshotPathError, match="resolves to the snapshot root"):
            ensure_within_root(tmp_path, tmp_path)

    def test_parent_traversal_refused(self, tmp_path: Path) -> None:
        # ``../`` should not let us escape, even though the syntactic path looks
        # like it's nested under tmp_path.
        with pytest.raises(SnapshotPathError, match="outside snapshot root"):
            ensure_within_root(tmp_path / ".." / "elsewhere", tmp_path)

    def test_absolute_override_refused(self, tmp_path: Path) -> None:
        # /etc/passwd is unambiguously outside any sane test snapshot root.
        with pytest.raises(SnapshotPathError, match="outside snapshot root"):
            ensure_within_root(Path("/etc"), tmp_path)

    @pytest.mark.parametrize(
        "bad_id",
        [
            "../escape",
            "../../etc",
            "..",
            ".",
            "with/slash",
            "with\\backslash",
            "",
            "latest",  # the alias is reserved
        ],
    )
    def test_paths_for_rejects_dangerous_ids(self, tmp_path: Path, bad_id: str) -> None:
        with pytest.raises(SnapshotPathError):
            paths_for(tmp_path, bad_id)

    def test_paths_for_returns_well_typed_paths(self, tmp_path: Path) -> None:
        cid = generate_check_id()
        p = paths_for(tmp_path, cid)
        assert isinstance(p, CheckPaths)
        assert p.check_id == cid
        assert p.manifest.name == "manifest.yaml"
        assert p.diff_staged.parent.name == "diff"
        assert p.spec_parsed.parent.name == "spec"
        assert p.report.name == "report.md"
        assert p.findings.name == "findings.yaml"


# ---------------------------------------------------------------------------
# create_check_dir lays down the on-disk shape
# ---------------------------------------------------------------------------


class TestCreateCheckDir:
    def test_creates_root_diff_and_spec_subdirs(self, tmp_path: Path) -> None:
        paths = create_check_dir(tmp_path)
        assert paths.root.is_dir()
        assert paths.diff_dir.is_dir()
        assert paths.spec_dir.is_dir()
        # manifest is not yet written; just the empty shell.
        assert not paths.manifest.exists()

    def test_collision_refused(self, tmp_path: Path) -> None:
        cid = generate_check_id()
        create_check_dir(tmp_path, check_id=cid)
        with pytest.raises(FileExistsError):
            create_check_dir(tmp_path, check_id=cid)

    def test_creates_snapshot_root_if_missing(self, tmp_path: Path) -> None:
        deeper = tmp_path / "does" / "not" / "yet" / "exist"
        paths = create_check_dir(deeper)
        assert paths.root.is_dir()
        assert deeper.is_dir()


# ---------------------------------------------------------------------------
# write_manifest / read_manifest round-trip
# ---------------------------------------------------------------------------


class TestManifestRoundTrip:
    def _sample_manifest(self, cid: str) -> CheckManifest:
        return CheckManifest(
            check_id=cid,
            created_at=datetime.now(UTC),
            spec_check_version="0.1.0",
            branch="feat/PROJ-1",
            base_ref="origin/main",
            head_sha="abcdef1",
            resolved_spec_id="page-abc",
            resolved_spec_url="https://notion.so/page-abc",
            resolution_method="ticket_key",
            collectors=[
                CollectorStatus(name="git_diff", state="ok", artefact_path="diff/staged.json"),
                CollectorStatus(name="notion_spec", state="failed", detail="MCP unreachable"),
            ],
        )

    def test_round_trip(self, tmp_path: Path) -> None:
        paths = create_check_dir(tmp_path)
        manifest = self._sample_manifest(paths.check_id)
        written = write_manifest(paths, manifest)
        assert written == paths.manifest
        assert paths.manifest.exists()

        out = read_manifest(paths)
        assert out.check_id == manifest.check_id
        assert out.collectors[0].state == "ok"
        assert out.collectors[1].state == "failed"
        assert out.resolved_spec_url == "https://notion.so/page-abc"

    def test_mismatched_check_id_refused(self, tmp_path: Path) -> None:
        paths = create_check_dir(tmp_path)
        manifest = self._sample_manifest("2026-04-30T20-31-12Z-zzzzzz")  # unrelated id
        with pytest.raises(SnapshotPathError, match="does not match"):
            write_manifest(paths, manifest)

    def test_read_manifest_missing_file(self, tmp_path: Path) -> None:
        paths = create_check_dir(tmp_path)
        with pytest.raises(SnapshotPathError, match="manifest missing"):
            read_manifest(paths)


# ---------------------------------------------------------------------------
# list_checks + resolve_check_id
# ---------------------------------------------------------------------------


class TestListAndResolve:
    def test_list_checks_empty(self, tmp_path: Path) -> None:
        assert list_checks(tmp_path) == []

    def test_list_checks_returns_newest_first(self, tmp_path: Path) -> None:
        old = generate_check_id(now=datetime(2026, 1, 1, tzinfo=UTC))
        mid = generate_check_id(now=datetime(2026, 4, 1, tzinfo=UTC))
        new = generate_check_id(now=datetime(2026, 4, 30, tzinfo=UTC))
        for cid in (old, mid, new):
            create_check_dir(tmp_path, check_id=cid)

        result = list_checks(tmp_path)
        assert result == [new, mid, old]

    def test_list_checks_skips_unrelated_entries(self, tmp_path: Path) -> None:
        cid = generate_check_id()
        create_check_dir(tmp_path, check_id=cid)
        (tmp_path / "README.txt").write_text("hi")
        (tmp_path / "not-a-check").mkdir()
        assert list_checks(tmp_path) == [cid]

    def test_list_checks_missing_root(self, tmp_path: Path) -> None:
        assert list_checks(tmp_path / "nope") == []

    def test_resolve_latest(self, tmp_path: Path) -> None:
        new = generate_check_id(now=datetime(2026, 4, 30, tzinfo=UTC))
        old = generate_check_id(now=datetime(2026, 1, 1, tzinfo=UTC))
        create_check_dir(tmp_path, check_id=old)
        create_check_dir(tmp_path, check_id=new)
        assert resolve_check_id(tmp_path, LATEST_ALIAS) == new

    def test_resolve_latest_no_checks(self, tmp_path: Path) -> None:
        with pytest.raises(SnapshotPathError, match="no checks"):
            resolve_check_id(tmp_path, LATEST_ALIAS)

    def test_resolve_explicit_id(self, tmp_path: Path) -> None:
        cid = generate_check_id()
        # Doesn't have to exist on disk — resolve_check_id just validates shape.
        assert resolve_check_id(tmp_path, cid) == cid

    def test_resolve_malformed_id(self, tmp_path: Path) -> None:
        with pytest.raises(SnapshotPathError, match="not well-formed"):
            resolve_check_id(tmp_path, "../escape")
