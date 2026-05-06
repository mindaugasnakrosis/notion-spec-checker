<!--
This is a sanitised sample of the markdown that `spec-check check` writes to
report.md. Real branch names, real Notion URLs, and real ticket keys have
been replaced with synthetic ones (PROJ-1, page-A, deadbeef…). Format is
byte-for-byte the same as a real run; only the data is fictional.
-->

# spec-check report — feat/PROJ-1-login

- **Branch**: `feat/PROJ-1-login`
- **Base ref**: `origin/main`
- **Head SHA**: `deadbeef1234567`
- **Spec**: https://notion.so/Login-flow-page-A-abc123
- **Resolution method**: `ticket_key`
- **Check id**: `2026-05-04T13-06-56Z-91f3a2`
- **Run at**: `2026-05-04T13:06:56+00:00`
- **spec-check version**: `0.1.0`

**3 finding(s)**: 1 High, 2 Medium.

## High (1)

### Spec was modified after the branch was created

- **Rule**: `spec_modified_after_branch` &nbsp;·&nbsp; **Severity**: High &nbsp;·&nbsp; **Confidence**: High
- **Knowledge**: `spec-drift.md`

**Question:** The spec page was edited 14400s after this branch was created. Notion's API doesn't expose what changed — can the spec author confirm whether the edit was a typo or clarification, or did the criteria themselves move while the branch was open?

<details><summary>Evidence</summary>

```yaml
branch: feat/PROJ-1-login
branch_created_at: '2026-05-01T12:00:00+00:00'
delta_seconds: 14400
head_sha: deadbeef1234567
high_confidence_threshold_seconds: 3600
notion_page_id: page-A-abc123
spec_last_edited_time: '2026-05-01T16:00:00+00:00'
spec_url: https://notion.so/Login-flow-page-A-abc123
```

</details>

## Medium (2)

### Spec has criteria but the diff has no test changes

- **Rule**: `criterion_without_test` &nbsp;·&nbsp; **Severity**: Medium &nbsp;·&nbsp; **Confidence**: Medium
- **Knowledge**: `invest-criteria.md`

**Question:** The spec lists 3 acceptance criteria but the diff modifies no test file. Are the criteria covered by existing tests this PR didn't need to touch, or is there test work missing from this PR?

<details><summary>Evidence</summary>

```yaml
branch: feat/PROJ-1-login
criteria_count: 3
files_changed: 4
notion_page_id: page-A-abc123
spec_url: https://notion.so/Login-flow-page-A-abc123
test_files_touched: []
```

</details>

### Ambiguous language in AC-2

- **Rule**: `ambiguous_criterion` &nbsp;·&nbsp; **Severity**: Medium &nbsp;·&nbsp; **Confidence**: Medium
- **Knowledge**: `ambiguity-in-acceptance-criteria.md`

**Question:** Criterion AC-2 contains the imprecise phrases 'fast' and 'user-friendly'. Could the criterion be re-phrased so a reviewer would not have to guess what passing looks like — or is the phrase a domain term that the team has agreed to accept?

<details><summary>Evidence</summary>

```yaml
ambiguous_phrases:
- fast
- user-friendly
criterion_id: AC-2
criterion_style: bullet
criterion_text: Login should be fast and user-friendly.
flag_reasons:
- contains imprecise word 'fast'
- contains imprecise phrase 'user-friendly'
notion_page_id: page-A-abc123
spec_url: https://notion.so/Login-flow-page-A-abc123
```

</details>

## Knowledge corpus citations

- `spec-drift.md`
- `invest-criteria.md`
- `ambiguity-in-acceptance-criteria.md`

---
_spec-check is read-only on git AND on Notion. It surfaces questions for the human; it does not block merges._
