---
name: spec-check Notion page conventions
canonical_url: null
canonical_author: spec-check
canonical_date: 2026-05-03
retrieval_date: 2026-05-03
content_sha256: null
cited_by:
  - missing_ac_section
  - missing_acceptance_criteria
  - multiple_specs_referenced
---

# Notion page conventions for spec-check

This is an *authored* knowledge doc — not a quote of an external source. It
records the page-shape conventions spec-check expects from a Notion spec.
The conventions are deliberate and small; if your team writes specs
differently, override the relevant rules in `.spec-check.yaml` rather than
quietly mis-flagging.

## Convention 1 — every spec has an explicit Acceptance Criteria section

A reviewable spec exposes its acceptance criteria under a clearly named
heading. spec-check looks for any of the following as a `heading_2` block,
case-insensitively:

- `Acceptance Criteria`
- `Acceptance Criterion`
- `Criteria`

This convention exists because **the criteria are the contract**. A spec
that mixes its criteria into prose is, for review purposes, a spec without
criteria — there is nothing the review can compare the diff against. That's
what `missing_ac_section` raises.

The rule does not care *where* in the page the section sits, *how many*
criteria are listed under it, or whether they are bullets, numbered, GWT,
or to-do checkboxes. Only that the section exists and is named.

## Convention 2 — criteria are the leaf items under that heading

Bulleted items, numbered items, to-do items, and (as a fallback) paragraphs
under the AC heading are treated as criteria. Sub-bullets and nested
content are not currently extracted; a reviewer who relies on nesting
should call that out in `.spec-check.yaml` so we can tighten the parser.

## Convention 3 — the page is one spec

spec-check resolves *one* page per branch. If your branch implements two
specs, link both via `Refs:` trailers in the merge commit and run
spec-check twice — `--spec <id-A>` then `--spec <id-B>`. Multi-spec
branches are flagged by `multiple_specs_referenced` (step 13).

## Why this is a convention, not a hard rule

The Notion API doesn't impose any structure on a page. We could parse
"anything that smells like a criterion" and be cleverer about it, but
clever parsing produces silent wrong answers, which is the *worst* outcome
for a pre-merge review. An explicit, named heading is unambiguous: either
the team adopted the convention, or they didn't.
