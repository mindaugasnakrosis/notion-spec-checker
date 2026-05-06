"""User-level configuration for spec-check.

Loaded from ``~/.config/spec-check/config.yaml`` by default. Per-repo
overrides live in ``.spec-check.yaml`` at the repo root and are merged on
top of user config (repo wins).

Precedence (lowest → highest): defaults → user YAML → repo YAML → env vars.

Read-only on disk: this module reads YAML and reads env vars. It never
writes user config — ``spec-check init`` (step 10) is the only writer, and
it goes through the explicit :func:`write_user_config` helper here.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from platformdirs import user_config_path, user_data_path
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


def default_user_config_path() -> Path:
    """``~/.config/spec-check/config.yaml`` on Linux,
    ``~/Library/Application Support/spec-check/config.yaml`` on macOS,
    or wherever ``$XDG_CONFIG_HOME`` / platformdirs sends us.
    """
    return user_config_path("spec-check", appauthor=False) / "config.yaml"


def default_snapshot_root() -> Path:
    """Per-platform default snapshot root."""
    return user_data_path("spec-check", appauthor=False) / "checks"


_DEFAULT_AMBIGUITY_PHRASES: tuple[str, ...] = (
    # Vague qualifiers — ground in observable-acceptance-criteria.md.
    "fast",
    "slow",
    "user-friendly",
    "user friendly",
    "easy to use",
    "intuitive",
    "seamless",
    "robust",
    "scalable",
    "flexible",
    "performant",
    "responsive",
    "modern",
    "clean",
    "simple",
    # Hedging modal verbs — criterion-as-wish rather than criterion-as-signal.
    "should",
    "could",
    "may",
    "might",
    "ideally",
    "preferably",
    # Quantifier-without-threshold.
    "many",
    "few",
    "some",
    "several",
    "most",
    "minimal",
    "lots of",
)


_DEFAULT_TICKET_PATTERN = r"(?P<ticket>[A-Z][A-Z0-9]+-\d+)"


class ResolverConfig(BaseModel):
    """Branch → spec resolution. Order is fixed by `resolver.py`; this is the
    knob layer.
    """

    model_config = ConfigDict(extra="forbid")

    ticket_pattern: str = _DEFAULT_TICKET_PATTERN
    fuzzy_match_min_score: float = Field(default=0.6, ge=0.0, le=1.0)
    notion_workspace_id: str | None = None

    @field_validator("ticket_pattern")
    @classmethod
    def _pattern_compiles(cls, v: str) -> str:
        try:
            re.compile(v)
        except re.error as exc:
            raise ValueError(f"ticket_pattern is not a valid regex: {exc}") from exc
        return v


class _MergedYamlSource(PydanticBaseSettingsSource):
    """A settings source that reads a pre-merged YAML mapping.

    The mapping is built once by :func:`load_settings` (user YAML deep-merged
    with the optional repo YAML) and handed in here. Env vars sit above this
    in the source chain, so they override values declared in YAML.
    """

    def __init__(self, settings_cls: type[BaseSettings], data: dict[str, Any]) -> None:
        super().__init__(settings_cls)
        self._data = data

    def get_field_value(self, field, field_name):  # type: ignore[override]
        if field_name in self._data:
            return self._data[field_name], field_name, False
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        return dict(self._data)


def _make_settings_class(merged_yaml: dict[str, Any]) -> type[SpecCheckSettings]:
    """Build a SpecCheckSettings subclass that pulls YAML defaults from
    ``merged_yaml``. Env vars still override; explicit init kwargs still win.
    """

    class _S(SpecCheckSettings):
        @classmethod
        def settings_customise_sources(  # type: ignore[override]
            cls,
            settings_cls,
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        ):
            return (
                init_settings,
                env_settings,
                dotenv_settings,
                _MergedYamlSource(settings_cls, merged_yaml),
                file_secret_settings,
            )

    return _S


class SpecCheckSettings(BaseSettings):
    """Top-level config.

    Env vars use the prefix ``SPEC_CHECK_`` and override YAML values.
    Nested settings use ``__`` (e.g. ``SPEC_CHECK_RESOLVER__FUZZY_MATCH_MIN_SCORE``).
    """

    model_config = SettingsConfigDict(
        env_prefix="SPEC_CHECK_",
        env_nested_delimiter="__",
        extra="forbid",
    )

    snapshot_root: Path = Field(default_factory=default_snapshot_root)
    resolver: ResolverConfig = Field(default_factory=ResolverConfig)
    ambiguity_phrases: list[str] = Field(default_factory=lambda: list(_DEFAULT_AMBIGUITY_PHRASES))
    large_diff_lines_threshold: int = Field(default=400, ge=1)
    scope_creep_lines_per_criterion: int = Field(default=200, ge=1)
    spec_drift_high_confidence_seconds: int = Field(default=3600, ge=0)

    @field_validator("snapshot_root")
    @classmethod
    def _expand_user(cls, v: Path) -> Path:
        return Path(os.path.expanduser(str(v))).resolve()

    @field_validator("ambiguity_phrases")
    @classmethod
    def _normalise_phrases(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for raw in v:
            phrase = raw.strip().lower()
            if phrase and phrase not in seen:
                seen.add(phrase)
                out.append(phrase)
        return out


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open() as fh:
        loaded = yaml.safe_load(fh) or {}
    if not isinstance(loaded, dict):
        raise ValueError(
            f"{path} must contain a YAML mapping at the top level, got {type(loaded).__name__}"
        )
    return loaded


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in overlay.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_settings(
    user_config: Path | None = None,
    repo_config: Path | None = None,
) -> SpecCheckSettings:
    """Load config from user YAML, then deep-merge a repo-level
    ``.spec-check.yaml`` on top, then let env vars override.
    """
    user_path = user_config if user_config is not None else default_user_config_path()
    user_data = _read_yaml(user_path)

    repo_data: dict[str, Any] = {}
    if repo_config is not None:
        repo_data = _read_yaml(repo_config)

    merged = _deep_merge(user_data, repo_data)

    cls = _make_settings_class(merged)
    return cls()


def write_user_config(settings: SpecCheckSettings, path: Path | None = None) -> Path:
    """Write a SpecCheckSettings instance to user config YAML.

    The only configuration writer in spec-check; called exclusively by
    ``spec-check init`` (step 10). Read-only-on-two-surfaces does not
    cover this — config is local user state, not git or Notion.
    """
    target = path if path is not None else default_user_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = settings.model_dump(mode="json")
    with target.open("w") as fh:
        yaml.safe_dump(payload, fh, sort_keys=False)
    return target
