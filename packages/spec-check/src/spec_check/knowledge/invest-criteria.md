---
name: INVEST criteria for user stories
canonical_url: https://xp123.com/invest-in-good-stories-and-smart-tasks/
canonical_author: Bill Wake
canonical_date: 2003-08-17
retrieval_date: 2026-05-03
content_sha256: 09c8580b3117e534752b0f23e6573444df3919527e21c2f58508e71b5e0ecb0a
cited_by:
  - large_diff_without_spec
  - criterion_without_test
  - scope_creep
---

# INVEST criteria for user stories

Bill Wake's 2003 INVEST checklist for what makes a *good* user story.
spec-check leans on two of the six letters in particular:

- **S — Small**: a story that takes weeks rather than days is hard to keep
  in scope. A diff that grows past `large_diff_lines_threshold` without a
  resolved spec is almost certainly two or three stories crammed together.
- **T — Testable**: a story you can't test isn't done. A criterion the diff
  doesn't exercise is a story without its test.

## Verbatim quotes (canonical source)

> **I – Independent.** Stories are easiest to work with if they are independent. That is, we'd like them to not overlap in concept, and we'd like to be able to schedule and implement them in any order.

> **N – Negotiable.** A good story is negotiable. It is not an explicit contract for features; rather, details will be co-created by the customer and programmer during development.

> **V – Valuable.** A story needs to be valuable. We don't care about value to just anybody; it needs to be valuable to the customer.

> **E – Estimable.** A good story can be estimated. We don't need an exact estimate, but just enough to help the customer rank and schedule the story's implementation.

> **S – Small.** Good stories tend to be small. Stories typically represent at most a few person-weeks worth of work.

> **T – Testable.** A good story is testable. Writing a story card carries an implicit promise: "I understand what I want well enough that I could write a test for it."

— Bill Wake, *INVEST in Good Stories, and SMART Tasks*, 17 August 2003.
Retrieved 2026-05-03 from <https://xp123.com/invest-in-good-stories-and-smart-tasks/>.

## How spec-check applies this

| Rule | Letter | What it asserts |
| --- | --- | --- |
| `large_diff_without_spec` | **S** | A diff above the configured size threshold without a resolved spec violates *Small* — there is almost certainly more than one story landing in this PR, and the team has lost the ability to negotiate or estimate the parts. |
| `criterion_without_test` | **T** | A criterion that the diff does not exercise is a *Testable* claim with no test. The implicit promise — "I could write a test for it" — has not been kept. |
| `scope_creep` | **S**, **I** | A diff much larger than the spec's criteria justify has either grown past *Small* or absorbed work that belonged to a different, *Independent* story. The spec exists; the question is whether the diff has stayed within it. |

These are *signals*, not verdicts. A reviewer may accept a large unspecified
diff for documented reasons (a one-shot script, a vendored upgrade); a
criterion may be genuinely covered by tests that the diff did not modify.
spec-check raises the question — the reviewer answers it.
