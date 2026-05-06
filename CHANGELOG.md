# Changelog

All notable changes to spec-check are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

Nothing yet.

## [0.1.0] — 2026-05-04

First public release. Single-package skill with two read-only firewalls (git + Notion), 9 rules, a 5-document knowledge corpus, and the full `spec-check` CLI surface.

### Added

- **Workspace scaffolding** — `uv` workspace, single `spec-check` package with a `spec_check.core` submodule, ruff config (line length 100, py311 target), GitHub Actions CI on Python 3.11 + 3.12, MIT license, issue + PR templates, `.gitignore`.
- **`spec_check.core.schema`** — Pydantic v2 models for `Finding` (severity × confidence axes; non-Info findings must cite at least one knowledge ref; `recommended_investigation` validator rejects 17 imperative prefixes), `ParsedSpec` + `AcceptanceCriterion` + `AmbiguityFlag`, `ParsedDiff` + `ChangedHunk`, `CheckManifest` + `CollectorStatus`, `BranchMetaSnapshot`, `FindingsDocument`. Every model uses `extra="forbid"`.
- **`spec_check.core.config`** — Pydantic Settings with deep-merged user / repo / env precedence; default ambiguity phrase list; `large_diff_lines_threshold`, `scope_creep_lines_per_criterion`, `spec_drift_high_confidence_seconds`, resolver knobs (`ticket_pattern`, `fuzzy_match_min_score`, `notion_workspace_id`).
- **`spec_check.core.gitwrap`** — read-only git wrapper with explicit verb allowlist; `GitWriteRefused` raised at the subprocess boundary before `git` is invoked.
- **`spec_check.core.notion`** — read-only MCP wrapper that allows only `fetch` / `search`; refuses every mutating MCP method.
- **`spec_check.core.snapshot`** — on-disk layout (`manifest.yaml`, `branch_meta.yaml`, `diff/{staged,unstaged,recent_commits}.json`, `spec/raw_blocks.json`, `spec/parsed.yaml`, `findings.yaml`, `report.md`); `ensure_within_root` sandbox enforced on every computed path; well-formed `check_id` regex; `latest` alias.
- **`spec_check.core.collectors`** — `branch_meta` (branch name, head sha, base ref via `origin/HEAD`, commit subject + body, `Refs:` trailers, `[PROJ-123]` brackets, reflog-derived branch creation timestamp), `git_diff` (staged / unstaged / `base_ref..HEAD`), `notion_spec` (raw page + blocks via the MCP wrapper), `test_files` (test-file detection over a parsed diff). Every collector returns a `CollectorOutput` so per-collector failures don't kill the run.
- **`spec_check.core.resolver`** — branch → spec resolution: explicit `--spec` override → ticket-key match → `Refs:` trailer → fuzzy slug; resolution method recorded on the manifest as `override` / `ticket_key` / `trailer` / `fuzzy` / `ambiguous` / `unresolved`.
- **`spec_check.core.spec_parser`** — Notion blocks → `ParsedSpec`; case-insensitive named AC heading; criteria as `bulleted_list_item` / `numbered_list_item` / `to_do` / GWT-style paragraph; ambiguity-phrase detection with word-boundary regexes; observability heuristic.
- **`spec_check.core.orchestrator`** — `pull`: branch_meta → spec resolution → check directory → diffs → Notion fetch → parse → test_files → branch_meta snapshot → manifest. Per-collector failure tolerance; one bad collector never aborts the run.
- **`spec_check.core.analyse`** — rule registry (9 rules in deliberate priority order: spec-shape → size/scope → AC-quality → drift); dispatcher with exception isolation (a raising rule becomes an Info `rule_runtime_error` finding, not a crashed run); stable sort `severity → confidence → registry index → rule_id`; `findings.yaml` round-trip helpers.
- **`spec_check.core.report`** — markdown renderer (header → severity summary → severity-grouped findings with rule_id / severity / confidence one-liner, `**Question:**` line, collapsible `<details>` evidence, knowledge-corpus citations footer, read-only footer); `severity_summary` for machine-readable counts.
- **`spec_check.core.knowledge`** — corpus access via `importlib.resources.files("spec_check.knowledge")`; `KnowledgeFrontmatter` Pydantic schema; path-traversal refused on filename inputs.
- **9 rules**:
  - `missing_ac_section` (High × High) — no recognised AC heading on the page.
  - `missing_acceptance_criteria` (High × High) — heading present, zero criteria underneath.
  - `large_diff_without_spec` (High × High when unresolved, × Medium when ambiguous) — large diff with no resolved spec.
  - `scope_creep` (Medium × Medium) — diff exceeds `criteria_count × scope_creep_lines_per_criterion`, only when a spec is resolved.
  - `multiple_specs_referenced` (Medium × High) — head commit names ≥ 2 distinct ticket keys.
  - `criterion_without_test` (Medium × Medium) — spec has criteria, diff is non-empty, no test files touched.
  - `ambiguous_criterion` (Medium × Medium) — per-criterion finding for any criterion with `ambiguity_flags`.
  - `untestable_criterion` (Medium × Medium) — per-criterion finding for any criterion with `observable=False`.
  - `spec_modified_after_branch` (High × High when gap > threshold, × Medium when gap ≤ threshold) — spec edited after branch creation.
- **5-document knowledge corpus**:
  - `invest-criteria.md` — verbatim quote of Bill Wake, *INVEST in Good Stories, and SMART Tasks*, 2003-08-17, with retrieval date and content SHA-256. Cited by `large_diff_without_spec`, `criterion_without_test`, `scope_creep`.
  - `notion-page-conventions.md` — authored. Three conventions: named AC heading, criteria as leaf items under it, one spec per branch. Cited by `missing_ac_section`, `missing_acceptance_criteria`, `multiple_specs_referenced`.
  - `ambiguity-in-acceptance-criteria.md` — authored. Four ambiguity buckets (subjective qualifiers, hedges, indefinite quantifiers, vague references). Cited by `ambiguous_criterion`.
  - `observable-acceptance-criteria.md` — authored. "Outside-the-system actor" definition; actor / trigger / outcome triple. Cited by `untestable_criterion`.
  - `spec-drift.md` — authored. Three failure modes (silent goalpost move, stale implementation, lost review trail). Cited by `spec_modified_after_branch`.
- **CLI** (Typer): `init`, `doctor`, `pull`, `analyse`, `report`, `check` (one-shot), `checks ls`, `checks show`, `knowledge list`, `knowledge show`, `schema`, `version`. No mutating verbs.
- **`SKILL.md`** (full version) — senior-tech-lead persona; TRIGGER / SKIP frontmatter; six hard rules; flow (init → doctor → check → narrate); severity + confidence rubrics; ten-item anti-patterns checklist; ten-item v1 scope guardrails.
- **README** — full version with badges, who-this-is-for, what-it-produces, six architectural guarantees, layout, requirements, quickstart, Claude Code skill usage, CLI surface, authorities table, rules table, configuration, troubleshooting, roadmap, skill family.
- **CONTRIBUTING / SECURITY / CHANGELOG** — full versions with knowledge-corpus discipline, two-firewall reporting, severity classes.
- **Repo polish** — issue templates (bug report, knowledge corpus drift, new rule proposal), PR template, CI workflow on Python 3.11 + 3.12.

### Architectural guarantees in 0.1.0

- Read-only on git is absolute (verb allowlist enforced at the subprocess boundary, with dedicated tests).
- Read-only on Notion is absolute (MCP method allowlist enforced in the wrapper, with dedicated tests).
- Every non-Info finding must cite at least one `knowledge/*.md` document; the `Finding` validator refuses construction otherwise.
- Every `recommended_investigation` is phrased as a question; the validator rejects 17 imperative prefixes.
- Severity (Critical → Info) and confidence (High / Medium / Low) reported as separate axes.
- One spec per check; multi-spec branches surface `multiple_specs_referenced` and instructions to re-run with `--spec`.
- Snapshot-root sandbox enforced on every computed path; `check_id` shape regex prevents traversal via the directory name.
- 372 tests passing on Python 3.11 + 3.12.

### Known follow-ups (deferred to v0.2)

- **Per-criterion test mapping** — today `criterion_without_test` is a coarse signal at the diff/spec level; a future rule could match each `AcceptanceCriterion.text` against test names / docstrings to fire per-criterion.
- **Critical-severity cross-spec rule** — "this spec contradicts another live spec". Reserved for v2.
- **Confluence and Google Docs adapters** — the `notion.py` wrapper is the only spec-source-specific code; siblings could expose the same shape.
- **Semantic similarity between criteria and code** — cautious roadmap item; embeddings would introduce non-determinism that the citation discipline depends on.
- **`spec-architecture-investigator` sibling skill** — same architectural firewall, different persona, shared core. Listed as future work.

[Unreleased]: https://github.com/mindaugasnakrosis/notion-spec-checker/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/mindaugasnakrosis/notion-spec-checker/releases/tag/v0.1.0
