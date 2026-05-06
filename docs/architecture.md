# Architecture

> _Placeholder — populated alongside step 4 (the read-only firewalls)._

One-page rationale will cover:

1. **Two read-only surfaces, enforced in three places.** `gitwrap.py` allowlist, `notion.py` allowlist, CLI verb naming. Each enforced by tests.
2. **MCP boundary.** spec-check sits on top of Notion's official Claude Code MCP plugin. We don't re-implement the connector.
3. **Knowledge-corpus-first rules.** A rule that cites a missing knowledge file refuses to run.
4. **Severity × confidence axes.** Independent. A finding can be Critical/Low or Low/High.
5. **Snapshot artefact layout.** `manifest.yaml` + `diff/` + `spec/` + `report.md` + `findings.yaml` per check.
