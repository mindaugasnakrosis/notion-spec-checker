---
name: Ambiguity in acceptance criteria
canonical_url: null
canonical_author: spec-check
canonical_date: 2026-05-04
retrieval_date: 2026-05-04
content_sha256: null
cited_by:
  - ambiguous_criterion
---

# Ambiguity in acceptance criteria

This is an *authored* knowledge doc — not a quote of an external source. It
records why spec-check treats certain phrases as ambiguity signals, and what
the `ambiguous_criterion` rule is asserting when it fires.

## What we mean by "ambiguous"

A criterion is *ambiguous* when two competent readers — reviewer and author,
or two engineers on different teams — could read the same sentence and walk
away with materially different ideas of what passing looks like. Ambiguity
isn't a stylistic complaint; it's a cost. Each ambiguous criterion forces a
later conversation, and that conversation often happens *after* the code is
written, when changing direction is expensive.

The classic offenders fall into a few buckets:

- **Subjective qualifiers** — *fast*, *slow*, *user-friendly*, *intuitive*,
  *robust*. They describe a feeling, not a measurable outcome.
- **Hedges** — *probably*, *should*, *might*, *as needed*, *if appropriate*.
  They turn a contract into a wish.
- **Indefinite quantifiers** — *some*, *many*, *several*, *most*, *a few*.
  They invite disagreement on what counts as "enough".
- **Vague references** — *the user*, *the system*, *appropriate behaviour*,
  *handle this case*. They leave the actor or the action under-specified.

## How spec-check detects ambiguity

spec-check ships a default phrase list in `SpecCheckSettings.ambiguity_phrases`
(see `core/config.py`) and matches each phrase against criterion text with
word-boundary regexes for single words and substring search for multi-word
phrases. Each match becomes an `AmbiguityFlag(phrase, reason)` attached to
the parsed criterion.

The list is **deliberately conservative**. False positives erode trust in
the review faster than missed signals; teams should override the list in
`.spec-check.yaml` to extend it for their domain rather than fight the
defaults.

## What `ambiguous_criterion` asserts

The rule asserts: *"this criterion contains a phrase from the configured
ambiguity list."* That is all. It does **not** assert that the criterion is
unsalvageable, that the author was sloppy, or that the PR should be blocked.
Some technical phrases ("user-friendly URL slug", "fast path") are
intentionally fuzzy — that's why the recommended_investigation is a
question, and why the rule's confidence is Medium, not High.

The reviewer's job, with this finding in hand, is to ask: *can we make this
more precise without losing the spec author's intent?* If yes, edit the
spec. If no, accept the finding as known and move on.

## Cross-reference

`untestable_criterion` is the sibling rule that fires when the parser
believes the criterion has no observable outcome. The two rules can both
fire on the same criterion — they are not redundant; they describe two
distinct quality problems that frequently co-occur.
