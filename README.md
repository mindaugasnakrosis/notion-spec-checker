# spec-check

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Built with uv](https://img.shields.io/badge/built%20with-uv-DE5FE9.svg)](https://docs.astral.sh/uv/)

**Read-only pre-merge spec review, delivered as a Claude Code skill.** Snapshots a feature branch's git diff and its Notion spec page (via the Notion MCP plugin), evaluates the pair against a hardcoded knowledge corpus (INVEST, AC quality, page conventions, spec-drift), and produces a written analysis (`report.md` + `findings.yaml`) suitable for forwarding to the reviewer.

> Built for the **15-minute "does this PR meet its spec?" review** that engineering managers and tech leads do dozens of times a sprint — every finding grounded in a citable authority, every recommendation phrased as a question rather than an instruction.

---

## Who this is for

- **Engineering managers and tech leads** running pre-merge reviews who want a structured starting point with citation-grounded thresholds rather than vibes.
- **Product / engineering org leaders** who want spec drift, scope creep, and missing acceptance criteria surfaced *before* a PR lands, not at the all-hands retro a sprint later.
- **Claude Code users** who want a real-world example of a skill with a proper persona, knowledge corpus, and an architectural firewall on *two* read-only surfaces (git and Notion).
- **Portfolio reviewers (PE operating partners, portco CTOs)** evaluating a target's engineering hygiene — the report is forward-able as-is.

If you need a remediation tool, this isn't it. The skill is **read-only by architectural guarantee** on both surfaces: the `gitwrap.py` allowlist refuses every git write verb at the subprocess boundary, and the `notion.py` MCP wrapper allows only `fetch` / `search`. It produces investigations, not actions.

---

## What it produces

A `report.md` headed by branch + spec + resolution method, then severity-grouped findings (Critical → High → Medium → Low → Info) with per-finding evidence, and a knowledge corpus citations footer. Plus a flat `findings.yaml` for any downstream consumer. See [`docs/example-report.md`](docs/example-report.md) for a sanitised sample.

```
# spec-check report — feat/PROJ-1-login

- Branch: feat/PROJ-1-login
- Spec: https://notion.so/Login-flow-abc123
- Resolution method: ticket_key
- Run at: 2026-05-04T13:06:56Z

**4 finding(s)**: 2 High, 2 Medium.

## High (2)

### Spec was modified after the branch was created
- Rule: spec_modified_after_branch · Severity: High · Confidence: High
- Knowledge: spec-drift.md

**Question:** The spec page was edited 14400s after this branch was created. Notion's API doesn't expose what changed — can the spec author confirm whether the edit was a typo or clarification, or did the criteria themselves move while the branch was open?
```

Every non-Info finding cites the `knowledge/*.md` document grounding it. Recommendations are *questions* for the human, not directives — the Pydantic validator on `Finding` rejects 17 imperative prefixes (`add `, `fix `, `rewrite `, …) at construction time. Severity (Critical → Info) and confidence (High / Medium / Low) are separate axes, both reported.

---

## Architectural guarantees

- **Read-only on git is absolute.** The `gitwrap.py` wrapper allows only a small list of read verbs (`status`, `log`, `diff`, `rev-parse`, `show`, `for-each-ref`, `reflog`, `branch --show-current`, `symbolic-ref`). Any other verb — `checkout`, `commit`, `push`, `rebase`, `apply`, `reset`, `restore`, … — raises `GitWriteRefused` at the subprocess boundary. Verified by dedicated unit tests.
- **Read-only on Notion is absolute.** The `notion.py` MCP wrapper allows only fetch / search; `update_page`, `append_block`, `create_page`, `delete` and friends are not callable. Verified by dedicated unit tests.
- **Knowledge corpus is hardcoded, versioned, citable.** Each `knowledge/*.md` ships with frontmatter (canonical URL, retrieval date, content SHA-256 for verbatim quotes, `cited_by` list) and either a verbatim quote of the canonical authority or an explicitly-authored convention. The `Finding` validator refuses to construct a non-Info finding with no `knowledge_refs` — *if you can't cite, you can't claim.*
- **No live web fetches at runtime.** The corpus is committed; refresh is a maintainer-only operation (`scripts/refresh_knowledge.py`, step 20) reviewed by a human before commit.
- **Severity ≠ confidence.** A High-severity High-confidence finding (no AC heading at all) and a High-severity Medium-confidence finding (large unresolved diff, ambiguous resolution) are reported with their full two-axis label so a reviewer knows where to push back.
- **One spec per check.** spec-check resolves exactly one Notion page per run; the `multiple_specs_referenced` rule fires when the head commit names two or more ticket keys, and the recommendation is to re-run with `--spec <id>`.

See [`docs/architecture.md`](docs/architecture.md) for the full rationale.

---

## Layout

```
packages/
  spec-check/                              # the skill
    src/spec_check/
      core/                                # gitwrap, notion, snapshot, collectors, parser, resolver, analyse, report, knowledge
      rules/                               # 9 rules; each in its own module
      knowledge/                           # 5 .md docs (1 canonical-quote, 4 authored)
      cli.py                               # the spec-check CLI (Typer)
    skill/SKILL.md                         # the Claude Code skill persona
    tests/                                 # 372 tests
scripts/
  install_skill.sh                         # symlinks SKILL.md into ~/.claude/skills/spec-check/
  refresh_knowledge.py                     # maintainer-only: re-fetch knowledge sources, surface drift
docs/
  architecture.md                          # one-page: why two read-only surfaces, why the MCP-payload pattern
  contributing-a-rule.md                   # how to author a new rule
  example-report.md                        # sanitised sample report.md output
  notion-page-conventions.md               # mirror of the in-corpus authored doc, for browseable docs
```

---

## Requirements

- **Python 3.11+** (3.12 also tested in CI).
- **[`uv`](https://docs.astral.sh/uv/)** for the Python toolchain. Install via `curl -LsSf https://astral.sh/uv/install.sh | sh` or your platform's package manager.
- **`git`** on `PATH`.
- **[Claude Code](https://claude.com/code)** if you want to use the skill experience and/or fetch Notion pages via MCP. The CLI works without it (you can hand-craft a `--spec-payload` JSON file), but the intended flow is Claude-Code-driven.
- **[Notion's official Claude Code MCP plugin](https://www.notion.so/help/claude)** in your Claude Code session, if you want spec-check to resolve pages it hasn't seen before.

### Required Notion permissions

The signed-in Notion identity (via the Claude Code MCP plugin) needs **read access** to whatever spec pages you want analysed. spec-check never writes to Notion — there is no "edit this page" verb in the wrapper — so the integration's *Read content* capability is sufficient. Page-level access controls are honoured by the MCP plugin; spec-check inherits them.

### Required git access

A normal local working tree. spec-check operates on the currently-checked-out branch (`HEAD`) and its base ref (`origin/HEAD` → `main` → `master`, in that order). It never switches branches and never fetches from a remote.

---

## Quickstart

```bash
git clone https://github.com/mindaugasnakrosis/notion-spec-checker.git
cd notion-spec-checker
uv sync --all-packages
bash scripts/install_skill.sh        # only needed if you want it as a Claude Code skill
```

Then, against your repo, with a Notion page id you want to review against:

```bash
cd /path/to/your/repo
uv run spec-check init               # writes ~/.config/spec-check/config.yaml
uv run spec-check doctor             # verifies environment + corpus
uv run spec-check check \
  --spec <notion-page-id> \
  --spec-payload <path-to-mcp-fetched-json> \
  --stdout
```

Outputs land next to the snapshot manifest:

| OS | Snapshot root |
|---|---|
| Linux | `~/.local/share/spec-check/checks/<id>/` |
| macOS | `~/Library/Application Support/spec-check/checks/<id>/` |
| Windows | `%LOCALAPPDATA%\spec-check\checks\<id>\` |

Per check:

```
manifest.yaml                 # CheckManifest — branch, head, base, resolved spec, collector statuses
branch_meta.yaml              # BranchMetaSnapshot — referenced tickets, branch creation timestamp
diff/recent_commits.json      # ParsedDiff (base_ref..HEAD) — what rules consume
diff/staged.json              # working tree diff (informational)
diff/unstaged.json            # working tree diff (informational)
spec/raw_blocks.json          # raw Notion blocks
spec/parsed.yaml              # ParsedSpec — what rules consume
findings.yaml                 # FindingsDocument — flat list of Findings
report.md                     # ← user-facing artefact
```

---

## Using as a Claude Code skill

After `bash scripts/install_skill.sh`, restart Claude Code (or run `/skills`). Then trigger the skill with a natural-language prompt — Claude reads `SKILL.md`, decides this skill matches, and drives the CLI for you.

Example prompts that should trigger:

- *"Review this branch against the Notion spec at https://notion.so/Login-flow-abc123."*
- *"Does this PR meet its acceptance criteria? The spec is the page I shared earlier."*
- *"Pre-merge review: surface scope creep, missing tests, and ambiguous criteria. The branch is `feat/PROJ-1-login`."*

The skill will (in order): check `spec-check doctor` → fetch the Notion page via the Notion MCP plugin → write the payload to a JSON file → run `spec-check check --spec-payload <path>` → narrate `report.md` to you, lifting verbatim recommendations from each finding and citing the `knowledge/*.md` grounding.

If you want to drive the engine directly without going through Claude Code, just use the CLI verbs above — the skill is optional.

---

## CLI surface

```bash
# setup + diagnostics
spec-check init                                 # write a default ~/.config/spec-check/config.yaml
spec-check doctor                               # verify git, snapshot root, repo, config

# one-shot review
spec-check check [--spec <id>] [--spec-payload <path>] [--stdout]

# staged form (for iteration)
spec-check pull   [--spec <id>] [--spec-payload <path>]
spec-check analyse <id|latest>
spec-check report  <id|latest> [--stdout]

# inspection
spec-check checks ls
spec-check checks show <id|latest>
spec-check schema {finding,spec,diff,manifest}

# knowledge corpus
spec-check knowledge list
spec-check knowledge show <filename>
```

No mutating verbs. No `apply`, `commit`, `push`, `update`, `delete`. The naming is part of the read-only contract.

---

## Authorities the skill grounds itself in

| Authority | Used by |
|---|---|
| [INVEST in Good Stories, and SMART Tasks (Bill Wake, 2003)](https://xp123.com/invest-in-good-stories-and-smart-tasks/) | `large_diff_without_spec` (S — Small), `criterion_without_test` (T — Testable), `scope_creep` (S + I) |
| Notion page conventions for spec-check *(authored)* | `missing_ac_section`, `missing_acceptance_criteria`, `multiple_specs_referenced` |
| Ambiguity in acceptance criteria *(authored)* | `ambiguous_criterion` |
| Observable acceptance criteria *(authored)* | `untestable_criterion` |
| Spec drift after branch creation *(authored)* | `spec_modified_after_branch` |

The full corpus is 5 in-repo `.md` files at `packages/spec-check/src/spec_check/knowledge/`. List with `spec-check knowledge list`; read individual docs with `spec-check knowledge show <filename>`. Authored docs are explicitly marked `canonical_url: null` in their frontmatter — they are project-internal conventions, not external authorities, and the `cited_by` field shows which rules depend on each.

---

## Rules implemented in v1

| Rule | Severity | Confidence | Authority |
|---|---|---|---|
| `missing_ac_section` | High | High | Notion page conventions |
| `missing_acceptance_criteria` | High | High | Notion page conventions |
| `large_diff_without_spec` | High | High *(unresolved)* / Medium *(ambiguous)* | INVEST — Small |
| `scope_creep` | Medium | Medium | INVEST — Small + Independent |
| `multiple_specs_referenced` | Medium | High | Notion page conventions |
| `criterion_without_test` | Medium | Medium | INVEST — Testable |
| `ambiguous_criterion` | Medium | Medium | Ambiguity in acceptance criteria |
| `untestable_criterion` | Medium | Medium | Observable acceptance criteria |
| `spec_modified_after_branch` | High | High *(gap > threshold)* / Medium *(gap ≤ threshold)* | Spec drift after branch creation |

Critical and Low severities are reserved for v2 — Critical is intended for a future "this spec contradicts another live spec" rule, Low for governance / process gaps without immediate review impact.

To add a tenth rule, see [`docs/contributing-a-rule.md`](docs/contributing-a-rule.md). The discipline is *knowledge document first, then code, then tests* — and the `Finding` validator refuses to construct a non-Info finding without at least one `knowledge_refs` entry.

---

## Configuration

`~/.config/spec-check/config.yaml` is created by `spec-check init`. A repo-level `.spec-check.yaml` overrides the user config (deep merge); env vars override both (prefix `SPEC_CHECK_`, nested via `__`).

Every rule threshold is configurable. The defaults:

```yaml
snapshot_root: ~/.local/share/spec-check/checks
large_diff_lines_threshold: 400              # large_diff_without_spec
scope_creep_lines_per_criterion: 200         # scope_creep
spec_drift_high_confidence_seconds: 3600     # spec_modified_after_branch
ambiguity_phrases:                           # ambiguous_criterion
  - fast
  - user-friendly
  - should
  - might
  - …  # ~25 defaults; see core/config.py
resolver:
  ticket_pattern: "(?P<ticket>[A-Z][A-Z0-9]+-\\d+)"
  fuzzy_match_min_score: 0.6
  notion_workspace_id: null
```

A team that wants stricter drift control might set `spec_drift_high_confidence_seconds: 60` to surface even small post-branch edits as High confidence; a team with a domain phrase like *"fast path"* can prune `fast` from `ambiguity_phrases`.

---

## Troubleshooting

**`doctor` warns "not a git repo".** spec-check is repo-scoped — run it from inside a working tree, or pass `--repo <path>`.

**`spec resolved via fuzzy: ...` is wrong.** The resolver picks the highest-scoring page that shares words with the branch slug. Pass `--spec <page-id>` to bypass it; the spec-check session will say `resolved via override` instead.

**`large_diff_without_spec` won't fire even though the diff is huge.** The rule stays silent when a spec *was* resolved (one of `override` / `ticket_key` / `trailer` / `fuzzy`). On a resolved spec, you want `scope_creep` instead — check whether the per-criterion budget is too generous (`scope_creep_lines_per_criterion`).

**`ambiguous_criterion` flags a domain phrase as ambiguous.** Add the phrase to `ambiguity_phrases` to *remove* it from the default list (the field replaces, not extends), or override per-repo via `.spec-check.yaml`. The corpus's *Ambiguity in acceptance criteria* doc is explicit that the list is conservative-by-design and meant to be tuned.

**`spec_modified_after_branch` won't fire on a branch you know was opened weeks ago.** Shallow clones and fresh CI checkouts have no reflog; without a reflog, `branch_created_at` is `None` and the rule stays silent rather than guessing. Run on a full clone.

**`bash scripts/install_skill.sh` reports `warning: ... exists and is not a symlink`.** A previous install left a real file at `~/.claude/skills/spec-check/SKILL.md`. The script backs it up with a timestamped suffix and then symlinks; the warning is informational, not an error.

---

## Tests

```bash
uv run pytest                                              # 372 passed (~5s)
uv run ruff check .
```

CI runs both on push and on PR against `main`, on Python 3.11 and 3.12.

---

## Roadmap

- **Per-criterion test mapping.** Today `criterion_without_test` is a coarse signal at the diff/spec level. A v2 rule could match each `AcceptanceCriterion.text` against test names / docstrings to fire per-criterion.
- **A Critical-severity rule for "spec contradicts another live spec".** Cross-spec analysis is reserved for v2.
- **Confluence and Google Docs adapters.** The `notion.py` wrapper is the only spec-source-specific code; a `confluence.py` sibling could expose the same shape.
- **Semantic similarity** between criteria and the diff (e.g. "this criterion mentions `password`, the diff doesn't"). Cautious roadmap item — embeddings introduce non-determinism the current "every claim cites a knowledge doc" discipline depends on.
- **Reservation namespace for `spec-architecture-investigator`** (a sibling skill that reviews architectural specs against a tenant's actual deployment). Same architectural firewall, different persona, shared core. Listed as future work, not a v1.

If you have an authority, a heuristic, or a rule you'd want grounded — open an issue. The pattern of "knowledge doc → citing rule → testable threshold" is reusable for anything with published thresholds.

---

## Skill family

This is the third skill in a small portfolio aimed at PE operating partners and portco CTOs. Each is single-purpose, read-only by architectural guarantee, and ships with a knowledge corpus:

1. [`md-to-jira`](https://github.com/mindaugasnakrosis/mdjira) — markdown product doc → structured Jira backlog.
2. [`azure-cost-investigator`](https://github.com/mindaugasnakrosis/azure-costs-analyzer) — read-only Azure FinOps audit.
3. **`spec-check`** — read-only pre-merge spec review. *(this repo)*

The skills don't import each other and don't share runtime code — but they share a discipline: every claim is grounded in a citable authority, every recommendation is reviewable, every write surface is closed at an architectural boundary, not by convention.

---

## Contributing

See [`docs/contributing-a-rule.md`](docs/contributing-a-rule.md) for adding a new rule. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the broader contribution flow (issues, PRs, code review).

If you find a security issue (especially anything that could let either of the read-only firewalls be bypassed), see [`SECURITY.md`](SECURITY.md) for responsible-disclosure instructions.

---

## License

MIT — see [`LICENSE`](LICENSE).
