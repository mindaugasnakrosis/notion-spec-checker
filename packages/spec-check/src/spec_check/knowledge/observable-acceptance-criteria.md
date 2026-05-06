---
name: Observable acceptance criteria
canonical_url: null
canonical_author: spec-check
canonical_date: 2026-05-04
retrieval_date: 2026-05-04
content_sha256: null
cited_by:
  - untestable_criterion
---

# Observable acceptance criteria

This is an *authored* knowledge doc — not a quote of an external source. It
records what spec-check means by an *observable* criterion, why
observability matters more than testability-on-paper, and what the
`untestable_criterion` rule is asserting when it fires.

## Observable, not just testable

INVEST's *T — Testable* (see `invest-criteria.md`) sets a low bar: the
author claims they could write a test for the story. Observability is the
operational form of that promise:

> A criterion is **observable** when an outside-the-system actor can,
> without reading the source code, decide whether the criterion has been
> satisfied by inspecting the system's behaviour or output.

The "outside-the-system" framing is load-bearing. *"The cache is
invalidated"* is testable only if you have access to the cache; if the only
way to verify it is to read the implementation, the criterion has leaked
implementation into the contract. Rewrite as *"a stale page is not served
to a user after the underlying record changes"* and it becomes observable.

## What makes a criterion observable

A criterion is observable when it names, even implicitly:

1. **An actor** — who or what triggers the behaviour. ("the user", "the
   nightly job", "any HTTP client".)
2. **A trigger** — what happens to set the behaviour in motion. ("submits a
   login form", "receives a 401 response".)
3. **An outcome that's externally visible** — a UI state, an HTTP status, a
   log line, a row in a table the test can query, an emitted event.

The Given/When/Then form makes all three explicit by construction, which is
why spec-check's parser treats GWT-style criteria as observable by default.
For bullets and checklist items, the parser falls back to a heuristic: if
the criterion is free of ambiguity flags, treat it as observable; otherwise
mark it as untestable until clarified.

## What `untestable_criterion` asserts

The rule asserts: *"the parser believes this criterion lacks an observable
outcome."* It does **not** assert that the criterion is wrong, or that no
test could be written. It asserts that **as written**, two reviewers would
struggle to agree on what the test for it would be.

This is a Medium-severity, Medium-confidence finding because the parser's
observability heuristic is conservative — it will flag genuinely
ambiguous criteria, but also rare cases where the criterion is fine and the
ambiguity phrase is a domain term ("fast path", "user-friendly slug"). The
reviewer's job is to ask: *can we phrase this so the test is obvious?* If
yes, edit. If no, the criterion is implementation-coupled and a refactor
of the spec is owed before the next PR on this surface.

## Cross-reference

`ambiguous_criterion` is the sibling rule that fires when a phrase from the
ambiguity list is present. The two often co-fire for the same criterion;
that's intentional — they describe two distinct quality problems
(ambiguous *language* vs. unobservable *outcome*) that frequently appear
together.
