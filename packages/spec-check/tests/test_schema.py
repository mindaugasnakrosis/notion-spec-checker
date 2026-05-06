"""Tests for spec_check.core.schema."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from spec_check.core.schema import (
    AcceptanceCriterion,
    AmbiguityFlag,
    ChangedHunk,
    CheckManifest,
    CollectorStatus,
    Confidence,
    Finding,
    ParsedDiff,
    ParsedSpec,
    Severity,
)


class TestFinding:
    def test_minimal_valid_finding(self) -> None:
        f = Finding(
            rule_id="missing_ac_section",
            title="No Acceptance Criteria heading found",
            severity=Severity.HIGH,
            confidence=Confidence.HIGH,
            knowledge_refs=["notion-page-conventions.md"],
            recommended_investigation="Should this page have an Acceptance Criteria section?",
        )
        assert f.severity == Severity.HIGH
        assert f.confidence == Confidence.HIGH

    def test_severity_and_confidence_are_independent(self) -> None:
        # Critical severity / Low confidence is a valid combination — the PRD
        # explicitly calls this out.
        f = Finding(
            rule_id="scope_creep",
            title="Possible scope creep",
            severity=Severity.CRITICAL,
            confidence=Confidence.LOW,
            knowledge_refs=["invest-criteria.md"],
            recommended_investigation="Is this hunk part of the agreed scope?",
        )
        assert f.severity == Severity.CRITICAL
        assert f.confidence == Confidence.LOW

    def test_rule_id_must_be_snake_case(self) -> None:
        with pytest.raises(ValidationError, match="snake_case"):
            Finding(
                rule_id="MissingAcSection",
                title="x",
                severity=Severity.LOW,
                confidence=Confidence.LOW,
                knowledge_refs=["k.md"],
                recommended_investigation="Why?",
            )

    @pytest.mark.parametrize(
        "phrase",
        [
            "Add a test for AC-3",
            "Remove the unused field",
            "Fix the parser",
            "Rewrite this hunk",
            "Update the spec",
            "Implement the missing branch",
            "Refactor the resolver",
        ],
    )
    def test_recommended_investigation_rejects_instructions(self, phrase: str) -> None:
        with pytest.raises(ValidationError, match="phrased as a question"):
            Finding(
                rule_id="missing_ac_section",
                title="x",
                severity=Severity.LOW,
                confidence=Confidence.LOW,
                knowledge_refs=["k.md"],
                recommended_investigation=phrase,
            )

    @pytest.mark.parametrize(
        "phrase",
        [
            "Should this page have an Acceptance Criteria section?",
            "Is hunk in foo.py within the agreed scope?",
            "Which AC, if any, does this change satisfy?",
            "Does AC-3 have an observable signal?",
        ],
    )
    def test_recommended_investigation_accepts_questions(self, phrase: str) -> None:
        f = Finding(
            rule_id="r",
            title="t",
            severity=Severity.LOW,
            confidence=Confidence.LOW,
            knowledge_refs=["k.md"],
            recommended_investigation=phrase,
        )
        assert f.recommended_investigation == phrase

    def test_non_info_findings_must_cite_knowledge(self) -> None:
        with pytest.raises(ValidationError, match="must cite at least one knowledge_ref"):
            Finding(
                rule_id="missing_ac_section",
                title="x",
                severity=Severity.HIGH,
                confidence=Confidence.HIGH,
                knowledge_refs=[],
                recommended_investigation="Why?",
            )

    def test_info_findings_may_skip_citation(self) -> None:
        # Info findings are the "couldn't evaluate" tail and don't make claims,
        # so they're allowed without a knowledge_ref.
        f = Finding(
            rule_id="criterion_without_test",
            title="Skipped: no diff data",
            severity=Severity.INFO,
            confidence=Confidence.LOW,
            knowledge_refs=[],
            recommended_investigation="Why was the diff collector unavailable?",
        )
        assert f.knowledge_refs == []


class TestSpec:
    def test_minimal_valid_spec(self) -> None:
        s = ParsedSpec(
            notion_page_id="abc-123",
            title="Login feature",
            url="https://notion.so/abc-123",
            last_edited_time=datetime.now(UTC),
            has_ac_section=True,
            criteria=[
                AcceptanceCriterion(
                    id="AC-1",
                    text="Given a registered user, when they sign in, then they see the dashboard.",
                    style="given_when_then",
                    observable=True,
                )
            ],
        )
        assert s.criteria[0].id == "AC-1"

    def test_criterion_id_rejects_spaces(self) -> None:
        with pytest.raises(ValidationError, match="may not contain spaces"):
            AcceptanceCriterion(
                id="AC 1",
                text="x",
                style="bullet",
                observable=True,
            )

    def test_ambiguity_flag_attaches(self) -> None:
        c = AcceptanceCriterion(
            id="AC-2",
            text="The page should load fast.",
            style="bullet",
            observable=False,
            ambiguity_flags=[AmbiguityFlag(phrase="fast", reason="no measurable threshold")],
        )
        assert c.ambiguity_flags[0].phrase == "fast"


class TestDiff:
    def test_hunk_line_ordering(self) -> None:
        with pytest.raises(ValidationError, match="end_line"):
            ChangedHunk(file="a.py", start_line=10, end_line=5)

    def test_parsed_diff_sha_normalised_to_lower_hex(self) -> None:
        d = ParsedDiff(
            base_ref="main",
            head_sha="ABCDEF1",
            branch="feat/PROJ-1",
            files_changed=1,
            additions=3,
            deletions=0,
            hunks=[ChangedHunk(file="a.py", start_line=1, end_line=3)],
        )
        assert d.head_sha == "abcdef1"

    def test_parsed_diff_rejects_non_hex_sha(self) -> None:
        with pytest.raises(ValidationError, match="hex"):
            ParsedDiff(
                base_ref="main",
                head_sha="zzzzzzz",
                branch="feat/PROJ-1",
                files_changed=0,
                additions=0,
                deletions=0,
            )

    def test_parsed_diff_rejects_short_sha(self) -> None:
        with pytest.raises(ValidationError, match="at least 7"):
            ParsedDiff(
                base_ref="main",
                head_sha="abc",
                branch="feat/PROJ-1",
                files_changed=0,
                additions=0,
                deletions=0,
            )


class TestManifest:
    def test_round_trip(self) -> None:
        m = CheckManifest(
            check_id="2026-04-30T20-00-00Z-abc123",
            created_at=datetime.now(UTC),
            spec_check_version="0.1.0",
            branch="feat/PROJ-1",
            base_ref="origin/main",
            head_sha="abcdef1",
            resolved_spec_id="page-abc",
            resolution_method="ticket_key",
            collectors=[
                CollectorStatus(name="git_diff", state="ok", artefact_path="diff/staged.json"),
                CollectorStatus(name="notion_spec", state="failed", detail="MCP unreachable"),
            ],
        )
        round_tripped = CheckManifest.model_validate(m.model_dump())
        assert round_tripped.collectors[1].state == "failed"
