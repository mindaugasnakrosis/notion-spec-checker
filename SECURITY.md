# Security policy

## Supported versions

This project is on `0.1.0`. Security fixes will be applied to the latest commit on `main` and to the most recent tagged release. Older tags are not supported.

## The two read-only invariants

The skill's safety guarantee is that no invocation it makes can mutate state on either surface it reads from. This is enforced in code on both surfaces:

### Git

`spec_check.core.gitwrap.run_git` is the only sanctioned way to call git from this codebase. The wrapper:

- Holds an **allowlist of read-only verbs** (`status`, `log`, `diff`, `rev-parse`, `show`, `for-each-ref`, `reflog`, `branch --show-current`, `symbolic-ref`, …).
- Refuses every write verb at the subprocess boundary by raising `GitWriteRefused` *before* `git` is invoked. Forbidden verbs include but are not limited to: `commit`, `push`, `pull`, `fetch`, `checkout`, `reset`, `rebase`, `merge`, `cherry-pick`, `revert`, `add`, `rm`, `mv`, `tag`, `branch -D`, `stash`, `clean`, `config --set`, `config --add`, `config --unset`.
- Is covered by dedicated unit tests at `packages/spec-check/tests/test_gitwrap_refuses_writes.py`.

### Notion

`spec_check.core.notion.NotionWrapper` is the only sanctioned way to talk to the Notion MCP plugin from this codebase. The wrapper:

- Allows only the read MCP methods the resolver and collectors need (`fetch` / `search`).
- Refuses every mutating method (`update_page`, `append_block`, `create_page`, `delete`, `update_property`, comment posts, …).
- Is covered by dedicated unit tests at `packages/spec-check/tests/test_notion_refuses_writes.py`.

### Verb naming reinforces the invariants

The CLI uses only read verbs: `init` / `doctor` / `pull` / `analyse` / `report` / `check` / `checks ls` / `checks show` / `knowledge list` / `knowledge show` / `schema` / `version`. There is no `apply`, `commit`, `push`, `update`, `post`, `delete` verb anywhere in the CLI surface. The naming is part of the contract.

**A bypass of either invariant is the most serious class of security bug this project can have.** If you can construct an invocation that mutates state — on git or in Notion — and is not refused by the corresponding wrapper, please report it via the channel below before disclosing publicly.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security reports.

Instead, use one of:

- **GitHub Security Advisory** (preferred): https://github.com/mindaugasnakrosis/notion-spec-checker/security/advisories/new
- Email: [`mindaugasm@intelme.ai`](mailto:mindaugasm@intelme.ai) with subject line `[security] spec-check`.

Include in the report:

- The category (read-only bypass on git / read-only bypass on Notion / path traversal / dependency CVE / credential leak / other).
- A minimal reproduction (CLI invocation, or a unit test that demonstrates the issue against the wrapper).
- The Python version, OS, and `spec-check` version where the issue reproduces.
- Whether you've shared the finding elsewhere.

We will acknowledge within 72 hours.

## What constitutes a security issue here

In rough order of severity:

1. **Read-only bypass on git.** Any path through the codebase that lets a `git` invocation mutate the working tree, the index, the refs, or the config.
2. **Read-only bypass on Notion.** Any path that lets a Notion MCP method modify a page, block, comment, or property.
3. **Snapshot-root sandbox escape.** Snapshot writes go to a configured root and `snapshot.ensure_within_root` validates every computed path. If you can construct user-controlled input (a `check_id`, a `--repo` value, a `--spec-payload` path) that writes outside that root, that's a security bug.
4. **Knowledge-corpus tampering.** The corpus is committed text loaded via `importlib.resources`. If you can convince `core.knowledge` to load knowledge content from a non-corpus path at runtime — via path traversal in `knowledge show`, via packaging tricks, or otherwise — that's an integrity issue.
5. **Credential leak.** spec-check does not handle credentials directly (it relies on the Notion MCP plugin for authentication and on `git` for repo access), but report any code path that logs, persists, or transmits authentication material.
6. **Dependency vulnerabilities.** Reported via Dependabot in the normal flow; high-severity ones get fast-tracked.

## What's not a security issue here

- **Rule false-positives or false-negatives.** Calibration issues — open a regular bug report with the finding's `evidence` block.
- **Parser errors on weird Notion pages.** The parser is deliberately conservative; pages that don't match the documented conventions get fewer findings rather than wrong findings. Open a regular bug report.
- **Stale knowledge documents.** Sources change; verbatim quotes drift. The maintainer-only `scripts/refresh_knowledge.py` surfaces drift; humans review before commit. Stale text isn't a security issue — it's a calibration backlog.
- **A finding the analyser produced that turned out to be wrong on your repo.** Open a regular bug report.
- **The skill failing to resolve a Notion page.** That's a resolver tuning issue, not a security one. Pass `--spec <id>` to bypass.

## Disclosure timeline

- Acknowledgement within 5 business days of receipt (target: 72 hours).
- Triage and severity assessment within 14 days.
- A fix or mitigation in `main` within 30 days for critical and high-severity issues; longer for lower severities.
- Public disclosure (advisory + commit + release notes) only after a fix lands, with credit to the reporter unless declined.
