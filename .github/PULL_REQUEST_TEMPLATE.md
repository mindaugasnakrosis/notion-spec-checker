<!-- Thanks for contributing to spec-check. -->

## What this PR changes

<!-- One paragraph: what behaviour, rule, or knowledge doc changed and why. -->

## Read-only contract

- [ ] No new code path writes to git (no commit / push / fetch / checkout / reset / rebase / merge / cherry-pick / revert / add / rm / mv / tag / stash / clean / config --set).
- [ ] No new code path writes to Notion (no page edits, comments, property changes, or block appends).
- [ ] If this PR adds a subprocess call or MCP method, it is in the corresponding allowlist and tested.

## Knowledge corpus

- [ ] If this PR adds or modifies a rule, every cited `knowledge/*.md` exists and the rule's `KNOWLEDGE_REFS` lists them.
- [ ] If this PR refreshes a knowledge doc, retrieval date and content SHA-256 are updated and `cited_by` is correct.

## Findings discipline

- [ ] Every new finding's `recommended_investigation` is phrased as a question for the human, never an instruction to take an action.
- [ ] Severity and confidence are set independently and justified by the rule's evidence.

## Tests

- [ ] `uv run pytest -v` passes.
- [ ] `uv run ruff check .` and `uv run ruff format --check .` pass.

## Anything reviewers should look at first

<!-- Pointer to the most load-bearing diff. -->
