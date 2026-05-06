# Knowledge corpus

This directory ships inside the wheel. Each `*.md` file grounds one or more rules and follows the frontmatter format established in step 11:

```yaml
---
name: ...
canonical_url: ...
retrieval_date: YYYY-MM-DD
content_sha256: ...
cited_by:
  - rule_id_one
  - rule_id_two
---
```

Files arrive in steps 11–14:

- `invest-criteria.md`
- `user-stories.md`
- `given-when-then.md`
- `deep-backlog.md`
- `compound-story-decomposition.md`
- `observable-acceptance-criteria.md`
- `notion-page-conventions.md` _(authored, not quoted)_

`scripts/refresh_knowledge.py` re-pulls canonical sources for human review. We never auto-merge corpus drift.
