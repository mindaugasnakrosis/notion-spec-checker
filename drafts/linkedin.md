Shipping v0.1 of spec-check today.

It's a Claude Code skill that does one thing: read a feature branch and the Notion page that specs it, and produce a pre-merge review report. The kind of 15-minute "does this PR meet its spec?" review every tech lead does dozens of times a sprint.

What's different about it:

→ It's read-only by architectural firewall, not by convention. Two wrappers (one for git, one for Notion's MCP plugin) refuse every write verb at the subprocess boundary. If the LLM hallucinates a `git push` mid-review, the wrapper raises before git is invoked. Verified by dedicated unit tests, one per refused verb.

→ Every non-Info finding has to cite a knowledge/*.md document. The Pydantic validator refuses to construct a finding without at least one citation. If you can't cite, you can't claim. The corpus is hardcoded and committed; no live web fetches at runtime.

→ Recommendations are questions, not instructions. The validator rejects 17 imperative prefixes (Add, Fix, Rewrite, Update, …). Every recommendation ends in a "?". Difference between "the author should add AC-3" and "has the spec author confirmed AC-3 was intentionally omitted?" is the difference between a tool that decides and a tool that prepares a human to decide.

→ Severity and confidence are independent axes, both always reported. A High-severity Medium-confidence finding is fundamentally different from High/High, and the reviewer needs both numbers to know where to push back.

A typical run flags scope creep, ambiguous criteria, missing test coverage, and silent goalpost moves on the spec page. Output is a forward-able report.md you can paste straight into a PR comment.

v0.1 is genuinely shipping — 9 rules, 5 knowledge docs (INVEST + 4 authored), 372 tests. There's a known display bug in the report header and no Confluence adapter yet. Filing v0.2 issues openly rather than waiting for perfect.

If you find a way to get either firewall to write something — that's a security report, not an issue.

Repo + writeup in the comments.

---

#ClaudeCode #DeveloperTools #CodeReview #Notion #PreMergeReview #EngineeringLeadership
