# I built an AI code reviewer that refuses to write anything

*A Claude Code skill that reviews a feature branch against its Notion spec — grounded in citable authorities, read-only by architectural firewall, shipping at v0.1.*

---

Most "AI for code review" tools have the same problem. They're confident, ungrounded, and one bad prompt away from running `git push --force` on the wrong branch. I wanted something narrower and more honest, so I built **`spec-check`** — a Claude Code skill that does exactly one thing: read a feature branch and the Notion page that specs it, and produce a pre-merge review report grounded in a hardcoded knowledge corpus.

It's a v0.1. It works end-to-end. It's also unfinished in ways I'll name at the end. The point of writing this up now is to put the design decisions on record before they become folklore — and to invite people to break it.

## The job-to-be-done

There's a 15-minute review every engineering manager and tech lead does dozens of times a sprint. *"Does this PR actually meet the spec it was opened against?"* You skim the diff, you flip to the Notion page, you check whether the acceptance criteria are vaguely covered, you flag the suspicious bits, you approve or push back.

It's a high-leverage review and an annoying one. You're not looking for bugs — there are linters and tests for that — you're looking for **scope creep, ambiguous criteria, missing test coverage, and silent goalpost moves on the spec page**. Those four things are what `spec-check` was built to surface.

Not catch. *Surface.* That distinction matters and I'll come back to it.

## The shape of the thing

The skill is invoked from Claude Code with a natural-language prompt:

> *Review this branch against the Notion spec at https://notion.so/Login-flow-abc123.*

Claude recognises the trigger, runs `spec-check doctor` to confirm the environment, fetches the Notion page via the official Notion MCP plugin, writes the payload to a temp JSON file, runs the `spec-check` CLI against it, and narrates the resulting `report.md` back to the reviewer. The report is severity-grouped (Critical → High → Medium → Low → Info), every finding is grounded in a knowledge document, and every recommendation is phrased as a question for the human, not an instruction.

A real run, against a deliberately mediocre spec, produces something like this:

```
# spec-check report — feat/PROJ-1-login

- Branch: feat/PROJ-1-login
- Spec: PROJ-1: Login flow
- Resolution method: ticket_key

4 finding(s): 1 High, 3 Medium.

## High (1)

### Spec was modified after the branch was created
- Rule: spec_modified_after_branch · Severity: High · Confidence: Medium
- Knowledge: spec-drift.md

Question: The spec page was edited 2965s after this branch was created.
Notion's API doesn't expose what changed — can the spec author confirm
whether the edit was a typo or clarification, or did the criteria
themselves move while the branch was open?

## Medium (3)

### Ambiguous language in AC-2
- Rule: ambiguous_criterion · Severity: Medium · Confidence: Medium
- Knowledge: ambiguity-in-acceptance-criteria.md

Question: Criterion AC-2 contains the imprecise phrases 'fast',
'user-friendly', and 'should'. Could the criterion be re-phrased so a
reviewer would not have to guess what passing looks like — or is the
phrase a domain term that the team has agreed to accept?
```

The output is a forward-able artefact. You can paste it into a PR comment and the conversation that follows is anchored to specific criteria and specific authorities, not vibes.

## The two design decisions worth defending

### 1. Two read-only firewalls

Most LLM-driven dev tools are read-only **by convention** — the prompt says "don't edit anything" and you hope. `spec-check` is read-only by **architecture**, on both surfaces it touches.

- **Git**: every shell-out goes through `gitwrap.py`, which has an explicit allowlist of read verbs (`status`, `log`, `diff`, `rev-parse`, `show`, `for-each-ref`, `reflog`, `branch --show-current`, `symbolic-ref`). Any other verb — `checkout`, `commit`, `push`, `rebase`, `apply`, `reset`, `restore`, anything that mutates state — raises `GitWriteRefused` *before* `git` is invoked. Verified by dedicated unit tests, one per refused verb.
- **Notion**: the `notion.py` wrapper allows only `notion-fetch` and the explicit search verbs the resolver needs. `update_page`, `append_block`, `create_page`, `delete`, comment posts, property edits — all refused at the wrapper boundary. Same test discipline.

That sounds paranoid for a skill that *intends* to be read-only. The point is exactly that: the skill's intent is irrelevant. The architecture is what a reviewer can audit, and the architecture is what survives a prompt injection or a hallucinated tool call. If the LLM hallucinates a `git checkout` mid-review, the wrapper refuses; the skill can't bypass it because the skill doesn't have a code path that reaches `git` outside the allowlist.

### 2. Every claim cites an authority

Each rule fires against a specific document in a hardcoded `knowledge/*.md` corpus that ships with the skill. There are five today: an INVEST verbatim quote (Bill Wake, 2003), and four authored project conventions covering Notion page conventions, ambiguity in acceptance criteria, observable acceptance criteria, and spec drift.

Each knowledge document carries frontmatter with its canonical URL, retrieval date, and a content SHA-256 for verbatim quotes. Authored documents are explicitly marked `canonical_url: null` so they can't be confused with external authorities.

The Pydantic validator on `Finding` refuses to construct a non-Info finding without at least one `knowledge_refs` entry. *If you can't cite, you can't claim.* That constraint forced an interesting discipline during development: every time I wanted a rule to flag something, I had to write the document first. Several rules I thought I wanted got cut at that step, because I couldn't ground them in anything I'd defend in front of a reviewer.

The corpus is committed. There are no live web fetches at runtime. Refresh is a maintainer-only operation reviewed by a human before commit.

## Surface, don't catch

`spec-check` produces questions, not directives. The `Finding` validator rejects 17 imperative prefixes (`Add`, `Fix`, `Rewrite`, `Update`, `Implement`, `Replace`, …). Every `recommended_investigation` field has to end with a `?`. The skill's persona instructions reinforce the same constraint: *"Has the spec author confirmed AC-3 was intentionally omitted?"* — never *"the author should add AC-3."*

This isn't a stylistic choice. It's the difference between an LLM tool that **decides** and an LLM tool that **prepares a human to decide**. The former is, today, mostly broken in subtle ways the user can't audit. The latter is just a really good staff engineer pre-reading a PR for you.

A High-severity, Medium-confidence finding is fundamentally different from a High-severity, High-confidence finding. The first means *"the signal is strong but the inference depends on a heuristic you can override."* The second means *"the signal is in the data, not in a heuristic."* Both axes are reported, always. Severity rubric and confidence rubric are independent and explicit.

## What v0.1 actually does

Nine rules, grounded in five knowledge documents:

| Rule | Severity | Confidence |
|---|---|---|
| `missing_ac_section` | High | High |
| `missing_acceptance_criteria` | High | High |
| `large_diff_without_spec` | High | High / Medium |
| `multiple_specs_referenced` | Medium | High |
| `scope_creep` | Medium | Medium |
| `criterion_without_test` | Medium | Medium |
| `ambiguous_criterion` | Medium | Medium |
| `untestable_criterion` | Medium | Medium |
| `spec_modified_after_branch` | High | High / Medium |

372 tests, ~5s on my laptop. Repo conventions enforced at import-time, not at evaluate-time, so missing knowledge docs fail fast. CI on Python 3.11 and 3.12.

## What v0.1 doesn't do, and why I'm shipping anyway

The report header has a known display bug when the spec is resolved via `--spec` override but fetched via `--spec-payload`: the spec slot says `(unresolved)` even though the rules ran against the right page. The findings are correct. The header is misleading. Filing for v0.2.

There's no per-criterion test mapping. `criterion_without_test` is a coarse signal at the diff/spec level — it doesn't yet match each criterion's text against test names. That's the most-asked-for v0.2 feature and the most likely place I'll regret cutting corners.

There's no Confluence or Google Docs adapter. The `notion.py` wrapper is the only spec-source-specific code; a sibling adapter is mechanically straightforward. I haven't built it because I don't need it yet.

There's no semantic similarity between criteria and code. That's a deliberate cut — embeddings introduce non-determinism the "every claim cites a knowledge doc" discipline depends on, and I'd rather be auditable than clever.

I'm shipping v0.1 because the alternative is to keep iterating in private until the v2 features above are perfect, by which point the design decisions in v0.1 will have congealed into folklore I can't push back on. Better to put the read-only-firewall and citation-or-it-doesn't-claim disciplines in front of people while they're still fresh enough to argue about.

## Try it

[github.com/mindaugasnakrosis/notion-spec-checker](https://github.com/mindaugasnakrosis/notion-spec-checker)

```bash
git clone https://github.com/mindaugasnakrosis/notion-spec-checker
cd notion-spec-checker
uv sync --all-packages
bash scripts/install_skill.sh
```

Then in Claude Code, against any repo where you've connected Notion's MCP plugin:

> *Review this branch against the Notion spec at &lt;url&gt;.*

Open issues for rules I should have written, knowledge documents I should have cited, and authorities I missed. The pattern of *knowledge document → citing rule → testable threshold* is reusable for anything with published thresholds — INVEST is just the first one I cared about.

If you find a way to get either firewall to write something, that's a security report, not an issue. `SECURITY.md` in the repo.

---

*This is the third skill in a small portfolio aimed at PE operating partners and portco CTOs evaluating engineering hygiene. Each is single-purpose, read-only by architectural guarantee, and ships with a citable knowledge corpus. The other two are [`md-to-jira`](https://github.com/mindaugasnakrosis/mdjira) (markdown product doc → structured Jira backlog) and [`azure-cost-investigator`](https://github.com/mindaugasnakrosis/azure-costs-analyzer) (read-only Azure FinOps audit).*
