"""Tests for spec_check.core.config."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from spec_check.core.config import (
    SpecCheckSettings,
    default_snapshot_root,
    default_user_config_path,
    load_settings,
    write_user_config,
)


class TestDefaults:
    def test_default_paths_are_under_home(self) -> None:
        assert str(default_user_config_path()).startswith(str(Path.home()))
        assert str(default_snapshot_root()).startswith(str(Path.home()))

    def test_default_settings_have_sensible_values(self) -> None:
        # Empty env, no YAML on disk → all defaults.
        s = SpecCheckSettings()
        assert s.large_diff_lines_threshold == 400
        assert "fast" in s.ambiguity_phrases
        assert "should" in s.ambiguity_phrases
        assert s.resolver.fuzzy_match_min_score == 0.6
        assert s.resolver.ticket_pattern.startswith("(?P<ticket>")


class TestAmbiguityPhrases:
    def test_normalised_lowercased_and_deduped(self) -> None:
        s = SpecCheckSettings(ambiguity_phrases=["Fast", "fast", " Should ", "scalable"])
        assert s.ambiguity_phrases == ["fast", "should", "scalable"]


class TestResolverConfig:
    def test_invalid_regex_rejected(self) -> None:
        with pytest.raises(ValidationError, match="not a valid regex"):
            SpecCheckSettings(resolver={"ticket_pattern": "[unterminated"})

    def test_fuzzy_score_range(self) -> None:
        with pytest.raises(ValidationError):
            SpecCheckSettings(resolver={"fuzzy_match_min_score": 1.5})


class TestLoadSettings:
    def test_user_yaml_overrides_defaults(self, tmp_path: Path) -> None:
        user = tmp_path / "user.yaml"
        user.write_text(
            yaml.safe_dump(
                {
                    "large_diff_lines_threshold": 100,
                    "ambiguity_phrases": ["wibble"],
                }
            )
        )
        s = load_settings(user_config=user)
        assert s.large_diff_lines_threshold == 100
        assert s.ambiguity_phrases == ["wibble"]

    def test_repo_yaml_overrides_user(self, tmp_path: Path) -> None:
        user = tmp_path / "user.yaml"
        user.write_text(yaml.safe_dump({"large_diff_lines_threshold": 100}))
        repo = tmp_path / ".spec-check.yaml"
        repo.write_text(yaml.safe_dump({"large_diff_lines_threshold": 50}))
        s = load_settings(user_config=user, repo_config=repo)
        assert s.large_diff_lines_threshold == 50

    def test_repo_yaml_deep_merges_into_user(self, tmp_path: Path) -> None:
        user = tmp_path / "user.yaml"
        user.write_text(
            yaml.safe_dump(
                {
                    "resolver": {
                        "ticket_pattern": "(?P<ticket>USER-\\d+)",
                        "fuzzy_match_min_score": 0.4,
                    }
                }
            )
        )
        repo = tmp_path / ".spec-check.yaml"
        repo.write_text(yaml.safe_dump({"resolver": {"fuzzy_match_min_score": 0.9}}))
        s = load_settings(user_config=user, repo_config=repo)
        # Repo overrides only the score; user-supplied pattern survives.
        assert s.resolver.fuzzy_match_min_score == 0.9
        assert s.resolver.ticket_pattern == "(?P<ticket>USER-\\d+)"

    def test_env_overrides_yaml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        user = tmp_path / "user.yaml"
        user.write_text(yaml.safe_dump({"large_diff_lines_threshold": 100}))
        monkeypatch.setenv("SPEC_CHECK_LARGE_DIFF_LINES_THRESHOLD", "999")
        s = load_settings(user_config=user)
        assert s.large_diff_lines_threshold == 999

    def test_env_nested_delimiter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SPEC_CHECK_RESOLVER__FUZZY_MATCH_MIN_SCORE", "0.85")
        s = load_settings(user_config=Path("/nonexistent/no.yaml"))
        assert s.resolver.fuzzy_match_min_score == 0.85

    def test_missing_user_yaml_is_fine(self) -> None:
        s = load_settings(user_config=Path("/nonexistent/spec-check/no.yaml"))
        assert s.large_diff_lines_threshold == 400

    def test_non_mapping_yaml_rejected(self, tmp_path: Path) -> None:
        bad = tmp_path / "user.yaml"
        bad.write_text("- just\n- a\n- list\n")
        with pytest.raises(ValueError, match="YAML mapping"):
            load_settings(user_config=bad)

    def test_extra_keys_rejected(self, tmp_path: Path) -> None:
        bad = tmp_path / "user.yaml"
        bad.write_text(yaml.safe_dump({"unknown_key": 1}))
        with pytest.raises(ValidationError):
            load_settings(user_config=bad)


class TestWriteUserConfig:
    def test_round_trip(self, tmp_path: Path) -> None:
        target = tmp_path / "spec-check" / "config.yaml"
        s_in = SpecCheckSettings(large_diff_lines_threshold=42)
        path = write_user_config(s_in, path=target)
        assert path == target
        assert target.exists()

        s_out = load_settings(user_config=target)
        assert s_out.large_diff_lines_threshold == 42
