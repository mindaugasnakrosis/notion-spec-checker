"""On-disk shape of ``findings.yaml`` and ``branch_meta.yaml``.

Two small documents that the orchestrator + analyse layer need to round-trip
through disk so that ``analyse`` can run from a snapshot directory alone,
without re-fetching git or Notion.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from spec_check.core.schema.finding import Finding


class FindingsDocument(BaseModel):
    """The ``findings.yaml`` artefact: every Finding produced by analyse,
    plus enough run metadata to make the file self-describing.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    check_id: str = Field(min_length=1)
    spec_check_version: str = Field(min_length=1)
    findings: list[Finding] = Field(default_factory=list)


class BranchMetaSnapshot(BaseModel):
    """The ``branch_meta.yaml`` artefact.

    Distilled from :class:`spec_check.core.collectors.branch_meta.BranchMeta`
    at ``pull`` time. Persisted because rules need ``referenced_tickets`` and
    ``branch_created_at`` and the manifest doesn't carry them.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    branch: str = Field(min_length=1)
    head_sha: str = Field(min_length=1)
    base_ref: str = Field(min_length=1)
    last_commit_subject: str = ""
    last_commit_body: str = ""
    referenced_tickets: list[str] = Field(default_factory=list)
    branch_created_at: datetime | None = None
