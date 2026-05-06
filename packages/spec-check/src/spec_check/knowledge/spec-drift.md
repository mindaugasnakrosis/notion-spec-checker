---
name: Spec drift after branch creation
canonical_url: null
canonical_author: spec-check
canonical_date: 2026-05-04
retrieval_date: 2026-05-04
content_sha256: null
cited_by:
  - spec_modified_after_branch
---

# Spec drift after branch creation

This is an *authored* knowledge doc — not a quote of an external source. It
records why spec-check treats a Notion spec page edited after the branch
was created as a review-time signal, and what `spec_modified_after_branch`
is asserting when it fires.

## Why it matters

A pull-request review compares what was *built* against what was *asked
for*. When the spec changes after the branch starts, the question "does
this PR meet the spec?" becomes ambiguous — there are now two specs
(the one the engineer built against, and the one the reviewer is reading)
and they may disagree in ways neither party notices.

The risks split three ways:

1. **Silent goalpost move.** The author edits the criteria mid-flight,
   diff lands, both sides assume "the spec was always this." A subtle
   acceptance criterion ends up unimplemented because nobody noticed it
   was added late.
2. **Stale implementation.** The engineer built against last week's spec.
   Today's spec drops or rewords a criterion that the diff still implements
   the old way. The PR ships work that's no longer wanted.
3. **Lost review trail.** The spec page is the contract. If it mutates
   freely, the contract has no version, and "we agreed to ship X"
   collapses into "we agreed to ship whatever the page said when you read
   it."

These are not always *bugs*. Specs legitimately get tightened during
implementation — typos, clarifications, follow-up criteria the team agreed
to. The rule's job is not to forbid spec edits; it is to surface them so
the reviewer asks the question, not assume.

## What `spec_modified_after_branch` asserts

The rule asserts: *"the Notion page's `last_edited_time` is after the
branch's creation timestamp."* Confidence is **High** when the gap is
larger than `settings.spec_drift_high_confidence_seconds` (default 1
hour), and **Medium** when the gap is smaller — a one-minute edit is more
likely to be a typo fix than a goalpost move.

The rule does not, and cannot, tell the reviewer *what* changed. Notion's
API exposes `last_edited_time` but not a diff. The recommendation is
therefore a question, not an instruction: ask the spec author what they
edited, and decide whether the diff still satisfies the current criteria.

## Cross-reference

`spec-check` does not snapshot the spec at branch-creation time; the
canonical version is whatever Notion serves at `pull` time. A team that
wants stronger drift control should adopt a "spec freeze" convention
before opening the PR (e.g., paste the criteria into the PR description so
the review trail captures them) and override this rule's confidence
threshold downward to surface even small edits.
