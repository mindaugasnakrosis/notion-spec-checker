# Contributing to spec-check

Thanks for considering a contribution. The repo is small and the discipline behind it is non-negotiable: every rule must cite a knowledge document, every recommendation must be phrased as a question, and the read-only contract on **both** surfaces (git and Notion) is enforced in code, not in docs.

This page covers the broader flow. The mechanics of authoring a new rule live in [`docs/contributing-a-rule.md`](docs/contributing-a-rule.md).

## Before opening a PR

1. **Discuss material changes in an issue first.** New rules, knowledge-corpus additions, schema changes, and CLI verb additions all benefit from a short prior thread. Trivial fixes (typos, doc nits, dependency bumps) can go straight to PR.
2. **Run the suite locally.** `uv sync --all-packages && uv run pytest` should pass. Lint + format must be clean: `uv run ruff check . && uv run ruff format --check .`.
3. **Don't bypass either firewall.** Any new git invocation must route through `spec_check.core.gitwrap.run_git`. Any new Notion call must route through `spec_check.core.notion.NotionWrapper`. Any new rule must declare `knowledge_refs` and cite a real `knowledge/*.md` document; the `Finding` validator refuses non-Info findings without one.

## Adding a rule

The full discipline is in [`docs/contributing-a-rule.md`](docs/contributing-a-rule.md). The short version:

1. **Author the knowledge document first.** A `.md` file under `packages/spec-check/src/spec_check/knowledge/`, with frontmatter (`name`, `canonical_url`, `canonical_author`, `canonical_date`, `retrieval_date`, `content_sha256`, `cited_by`). If the source is external, quote it verbatim and stamp the SHA-256. If the doc is project-internal, set `canonical_url: null` and document why this is an authored convention rather than a quote.
2. **Add the rule module** at `packages/spec-check/src/spec_check/rules/<rule_id>.py`. Set `rule_id`, `title`, `knowledge_refs`. Write `evaluate(self, ctx: RuleContext) -> list[Finding]`. Handle the missing-input branch (parsed_spec / parsed_diff / branch_meta `None`) by staying silent rather than emitting Info — Info should be reserved for runtime errors, not absent inputs that another rule already speaks for.
3. **End the module with `_: Rule = MyRule()`** so static checking catches Protocol drift at import time.
4. **Register it** in `packages/spec-check/src/spec_check/rules/__init__.py` and add it to the `RULES` tuple in `packages/spec-check/src/spec_check/core/analyse.py`. The tuple order is the tie-break order in the report — place spec-shape rules first, size/scope second, AC-quality third, drift last. There is no auto-discovery; explicit registration is part of the safety story.
5. **Write tests** at `packages/spec-check/tests/test_rule_<rule_id>.py`. Minimum surface: silent on each missing-input path, fires on the positive case, evidence shape, severity / confidence axes, recommendation ends with `?`, knowledge_refs include the grounding doc.
6. **Run the suite**, open the PR.

## Adding a collector

Adding a new data source to the snapshot:

1. **Create the module** at `packages/spec-check/src/spec_check/core/collectors/<name>.py`. Export a `collect(...)` entry point that returns a `CollectorOutput`. Route any git call through `spec_check.core.gitwrap.run_git`; route any Notion call through `NotionWrapper`. Both wrappers refuse writes — never call `subprocess.run` or the MCP transport directly.
2. **Wire it into the orchestrator** at `packages/spec-check/src/spec_check/core/orchestrator.py`. Failures must produce a `CollectorStatus(state="failed", detail=...)` entry on the manifest, not crash the run. The manifest is the contract that lets `analyse` know which rules can run.
3. **If a rule depends on the new collector, handle the absence path.** A rule should always treat `None` inputs as silence; absent data is an `analyse`-time concern, not a runtime crash.

## Updating the knowledge corpus

Knowledge files are committed text. Updates land via:

- A **maintainer-driven re-fetch** with `uv run python scripts/refresh_knowledge.py` (step 20). The script re-pulls each canonical source and surfaces a diff against the on-disk SHA-256. The verbatim quoted body is *not* auto-rewritten — a human reviews the diff before commit and updates `retrieval_date` + `content_sha256` together.
- An **opened issue** describing the upstream change (URL, what specifically changed, which rules are affected) is preferred over a silent edit. Use the *Knowledge corpus drift* template at `.github/ISSUE_TEMPLATE/knowledge_drift.yml`.
- Quotes are verbatim by contract; paraphrases hide changes that need calibration. If the source has substantively changed, replace the quote, recompute SHA-256, and review every rule listed in `cited_by`.

## PR review criteria

- Tests pass on Python 3.11 and 3.12 (CI enforces).
- `ruff check` clean and `ruff format --check` clean.
- For a new rule: knowledge document committed in the same PR as the rule + tests; `RULES` tuple in `core/analyse.py` updated.
- For a knowledge-corpus refresh: `retrieval_date` and `content_sha256` updated together; `cited_by` audited for any rule that needs recalibration.
- For a schema change to `Finding`, `ParsedSpec`, `ParsedDiff`, or the manifest: every existing rule and every existing test still passes (the schemas are load-bearing; subtle drift compounds).
- For a new git or Notion call site: routed through the existing wrapper, not direct.
- Commit messages follow the build-style of `git log --oneline` so the history reads as a build narrative, not a noise stream. See existing commits for shape.

## Code style

Ruff handles formatting (line length 100, double quotes, `py311` target). Imports sorted by isort rules (I001) and required at module top (PLC0415). Type hints required on public function signatures; tests can be looser. Docstrings on rule modules + collectors should state the authority (the `knowledge/*.md` they cite) and the severity / confidence rationale up front.

No emoji in code or docs unless the user requests it. No comments restating what the code does — only WHY when a hidden constraint or non-obvious workaround is involved.

## Reporting bugs

Open a GitHub issue using the bug-report template. Include:

- The exact `spec-check` version (`spec-check version`) and Python version.
- The relevant section of `manifest.yaml` (specifically `collectors:` for the failing collector).
- The CLI command you ran and the full stderr output.
- A minimal `--spec-payload` JSON, if relevant — sanitise any internal page titles, real Notion URLs, or branch names.
- Whether the issue reproduces with `--spec <id>` (bypassing the resolver) — that pins down whether the bug is in resolution or in evaluation.

## Reporting security issues

Don't open a public issue. See [`SECURITY.md`](SECURITY.md). The most serious bug class is a breach of the read-only contract on either surface — a write to git or a write to Notion that the wrappers should have refused.

## Code of conduct

Be specific, be direct, be constructive. The same standard the rules hold themselves to: cite, don't claim; question, don't instruct. We're aiming for the £1000/day senior-contractor calibre in the *content* and the persona — so review style follows.
