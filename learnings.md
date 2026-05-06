# spec-check — what's actually built (v0.1.0)

A read-only CLI + Claude Code skill that ingests a feature branch's git diff and a Notion spec page, runs nine deterministic rules against the pair, and writes a markdown review.

## Pipeline

```
spec-check check  ──►  pull  ──►  collectors  ──►  parse  ──►  analyse  ──►  report
                       │                                       │             │
                       └─► snapshot dir                        └─► findings  └─► report.md
```

`check` is a one-shot wrapper around `pull → analyse → report`. The three are also exposed as separate verbs so you can iterate on rules without re-fetching.

## Modules

**`core/gitwrap.py`** — thin subprocess wrapper around `git`. Verb allowlist refuses every write verb (`commit`, `push`, `checkout`, `reset`, `add`, `rm`, `tag`, `stash`, `clean`, `config --set`, …) at the boundary; raises `GitWriteRefused` *before* `git` is invoked. Dedicated unit tests assert each refused verb.

**`core/notion.py`** — wrapper around the Notion MCP plugin. Allows only `fetch` and `search`. `update_page`, `append_block`, `create_page`, `delete`, comment posts, property edits — all refused. Pluggable transport (`PrefetchedTransport` for hand-supplied JSON payloads, `NullTransport` as the honest no-op fallback when the MCP isn't connected).

**`core/snapshot.py`** — on-disk layout manager. Each run gets a directory under `snapshot_root`:
```
<check_id>/
  manifest.yaml             # CheckManifest
  branch_meta.yaml          # BranchMetaSnapshot
  diff/{staged,unstaged,recent_commits}.json   # ParsedDiff x3
  spec/raw_blocks.json      # raw Notion API payload
  spec/parsed.yaml          # ParsedSpec
  findings.yaml             # FindingsDocument
  report.md
```
`ensure_within_root` validates every computed path; `check_id` regex blocks traversal via the directory name itself.

**`core/collectors/`** — four collectors:
- `branch_meta` — `git branch --show-current`, `rev-parse HEAD`, `log -1 --pretty=%B`, `reflog` for branch creation timestamp; regex-extracts `Refs: PROJ-123` trailers and `[PROJ-123]` brackets from the commit body.
- `git_diff` — runs `git diff --cached`, `git diff`, and `git diff base_ref..HEAD`; parses unified diff into `ParsedDiff` with per-hunk added/removed lines and a test-file heuristic.
- `notion_spec` — fetches page + child blocks via the MCP wrapper.
- `test_files` — derives test-file list from staged diff (substring + filename pattern match).

Each returns a `CollectorOutput` so failures become `CollectorStatus(state="failed", detail=...)` entries on the manifest rather than crashing the pipeline.

**`core/resolver.py`** — branch → Notion page resolution. Strategy chain: explicit `--spec` (`override`) → ticket-key match against page titles (`ticket_key`) → `Refs:` trailer matching (`trailer`) → fuzzy slug match against page titles (`fuzzy`) → `ambiguous` (multiple candidates above the score threshold) → `unresolved`. The chosen method is recorded on the manifest and threaded into rule contexts.

**`core/spec_parser.py`** — Notion blocks → `ParsedSpec`. Recognises a named "Acceptance Criteria" heading (case-insensitive); collects bulleted/numbered/to-do/GWT-paragraph children as `AcceptanceCriterion` instances. Tags each criterion with `style` (bullet/checklist/given_when_then), `ambiguity_flags` (word-boundary regex against the configured phrase list), and `observable` (True for GWT, otherwise `not flags`).

**`core/orchestrator.py`** — wires collectors → parser → manifest writer for `pull`. Distills branch_meta into a `BranchMetaSnapshot` (`referenced_tickets` = sorted union of trailers + brackets; `branch_created_at` from reflog) so analyse can rebuild the full RuleContext from disk alone.

**`core/analyse.py`** — rule registry + dispatcher.
- `RULES: tuple[Rule, ...]` — explicit, ordered list (no auto-discovery; that would let a typo silently disable a rule).
- `build_rule_context` — loads parsed_spec, parsed_diff, branch_meta from disk into a `RuleContext` dataclass.
- `run_rules` — runs every rule; a raising rule becomes one Info `rule_runtime_error` finding, not a crash.
- `sort_findings` — stable sort: severity → confidence → registry index → rule_id.
- Writes `findings.yaml` (Pydantic `FindingsDocument`).

**`core/report.py`** — pure markdown renderer. Header bullets → severity summary line → `## Severity (N)` sections (Critical → Info) → per-finding blocks (rule/severity/confidence one-liner, knowledge refs, `**Question:**` line, `<details>` evidence as YAML) → knowledge-corpus citations footer → read-only footer.

**`core/knowledge.py`** — corpus access via `importlib.resources.files("spec_check.knowledge")`; `KnowledgeFrontmatter` Pydantic schema validates every doc; `read_knowledge_doc` refuses `/`, `\`, `..` in filename input.

## Schemas (Pydantic v2, `extra="forbid"`)

- **`Finding`** — severity (Critical/High/Medium/Low/Info) × confidence (High/Medium/Low) as **independent** axes. Two field validators are load-bearing: non-Info findings must carry ≥1 `knowledge_refs` ("if you can't cite, you can't claim"); `recommended_investigation` is rejected if it starts with one of 17 imperative prefixes (`add `, `fix `, `rewrite `, `update `, …) — recommendations are *questions* by enforcement.
- **`ParsedSpec`** — page id, title, URL, last_edited_time, has_ac_section, criteria list, other_blocks bag.
- **`AcceptanceCriterion`** — id, text, style, observable bool, ambiguity_flags list, source line.
- **`AmbiguityFlag`** — phrase + reason.
- **`ParsedDiff`** — base_ref, head_sha (hex-validated), branch, files_changed, additions, deletions, hunks, test_files_touched.
- **`ChangedHunk`** — file, start/end line (ordered-validated), added/removed lines verbatim, is_test_file.
- **`CheckManifest`** — schema_version, check_id, created_at, spec_check_version, branch metadata, resolved spec, resolution_method, per-collector statuses.
- **`BranchMetaSnapshot`** — distilled branch_meta for on-disk persistence.
- **`FindingsDocument`** — wrapper over the findings list with check_id + version metadata.

## Rules (9)

| Rule | Severity × Confidence | Trigger |
|---|---|---|
| `missing_ac_section` | High × High | `has_ac_section is False` |
| `missing_acceptance_criteria` | High × High | `has_ac_section is True and len(criteria) == 0` |
| `large_diff_without_spec` | High × High *(unresolved)* / High × Medium *(ambiguous)* | `additions+deletions ≥ large_diff_lines_threshold` AND resolution ∉ {override, ticket_key, trailer, fuzzy} |
| `scope_creep` | Medium × Medium | resolution ∈ resolved set AND `additions+deletions > criteria_count × scope_creep_lines_per_criterion` |
| `multiple_specs_referenced` | Medium × High | ≥2 distinct ticket keys in head commit message |
| `criterion_without_test` | Medium × Medium | spec has criteria + non-empty diff + `test_files_touched == []` |
| `ambiguous_criterion` | Medium × Medium | per-criterion: `ambiguity_flags` non-empty |
| `untestable_criterion` | Medium × Medium | per-criterion: `observable is False` |
| `spec_modified_after_branch` | High × High *(gap > 1h)* / High × Medium *(gap ≤ 1h)* | `last_edited_time > branch_created_at` |

Each rule is a small class implementing the `Rule` Protocol (class-level `rule_id`, `title`, `knowledge_refs`; `evaluate(ctx) -> list[Finding]`). Each module ends with `_: Rule = MyRule()` for import-time Protocol conformance checking. Rules are pure functions of their `RuleContext` — they cannot mutate inputs.

## Knowledge corpus (5 docs)

Each ships with frontmatter (`name`, `canonical_url`, `canonical_author`, `canonical_date`, `retrieval_date`, `content_sha256`, `cited_by`):

- `invest-criteria.md` — verbatim Bill Wake 2003 with SHA-256 stamped. Grounds `large_diff_without_spec` (S), `criterion_without_test` (T), `scope_creep` (S+I).
- `notion-page-conventions.md` — authored. Grounds `missing_ac_section`, `missing_acceptance_criteria`, `multiple_specs_referenced`.
- `ambiguity-in-acceptance-criteria.md` — authored. Grounds `ambiguous_criterion`.
- `observable-acceptance-criteria.md` — authored. Grounds `untestable_criterion`.
- `spec-drift.md` — authored. Grounds `spec_modified_after_branch`.

Loaded lazily via `importlib.resources`; `cited_by` is the bidirectional reference between corpus and rules.

## Configuration (`SpecCheckSettings`, Pydantic Settings)

Precedence: defaults < user `~/.config/spec-check/config.yaml` < repo `.spec-check.yaml` (deep-merged) < env vars (`SPEC_CHECK_*`, nested via `__`). Every rule threshold is a knob:
- `large_diff_lines_threshold: 400`
- `scope_creep_lines_per_criterion: 200`
- `spec_drift_high_confidence_seconds: 3600`
- `ambiguity_phrases: [~25 defaults]`
- `resolver.ticket_pattern`, `resolver.fuzzy_match_min_score`, `resolver.notion_workspace_id`

## CLI (Typer)

```
init, doctor                                       — setup + diagnostics
pull [--spec ID] [--spec-payload PATH]             — snapshot only
analyse <id|latest>                                — run rules → findings.yaml
report  <id|latest> [--stdout]                     — render report.md
check  [--spec] [--spec-payload] [--stdout]        — pull + analyse + report
checks ls / checks show <id|latest>                — inspect prior runs
knowledge list / knowledge show <name>             — corpus access
schema {finding,spec,diff,manifest}                — JSON Schema dump
version
```

No mutating verbs anywhere. The naming is part of the read-only contract.

## Test surface (372 tests)

Per-module unit tests for every rule (silent paths + positive cases + evidence shape + severity/confidence axes + question-phrasing assertion + knowledge_ref assertion); wrapper-refusal tests for gitwrap and notion; collector tests; resolver tests; spec_parser tests; snapshot path-sandbox tests; orchestrator end-to-end test; analyse registry/dispatcher/sort tests; report renderer tests; CLI tests using `typer.testing.CliRunner` with sandboxed `XDG_CONFIG_HOME` and `SPEC_CHECK_SNAPSHOT_ROOT`. Runs in ~5s on Python 3.11; CI matrix covers 3.11 + 3.12.

## What it doesn't do

No git writes. No Notion writes. No live web fetches at evaluation time (knowledge corpus is committed; `scripts/refresh_knowledge.py` is a maintainer-only drift detector). No multi-spec resolution in one run. No Confluence/Jira/Docs adapters. No semantic NLP between criteria and code. No post-merge audit mode (always `base_ref..HEAD` on a live branch).
