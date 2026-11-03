import re
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

REPOSITORY = "manenim/gateway-rate-limiter"
PINNED_SHA = "50eb89b722a068b2e63fa1dfe2a87d2605ae564a"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InvestigationInput(StrictModel):
    repository: str = REPOSITORY
    ref: str = Field(default="main", min_length=1, max_length=100)
    issue_url: str | None = Field(default=None, max_length=200)
    title: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=6000)

    @field_validator("repository")
    @classmethod
    def allowlist(cls, value: str) -> str:
        if value != REPOSITORY:
            raise ValueError("Only manenim/gateway-rate-limiter is supported")
        return value

    @field_validator("ref")
    @classmethod
    def validate_ref(cls, value: str) -> str:
        if (
            not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./-]*", value)
            or any(x in value for x in ["..", "//", "@{", ".lock"])
            or value.endswith(("/", "."))
        ):
            raise ValueError("Invalid branch, tag or commit ref")
        return value

    @field_validator("issue_url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if value and not re.fullmatch(
            r"https://github\.com/manenim/gateway-rate-limiter/issues/[1-9][0-9]{0,8}", value
        ):
            raise ValueError("Use an issue URL from the supported repository")
        return value

    @model_validator(mode="after")
    def issue_required(self):
        if not self.issue_url and not (self.title.strip() and self.body.strip()):
            raise ValueError("Provide a GitHub issue URL or a title and description")
        if self.issue_url and (self.title or self.body):
            raise ValueError("Choose an issue URL or pasted text, not both")
        return self


class ResolvedIssue(StrictModel):
    repository: str
    ref: str
    issue_url: str | None
    title: str
    body: str


def safe_path(path: str) -> bool:
    p = PurePosixPath(path)
    return (
        bool(path)
        and not p.is_absolute()
        and ".." not in p.parts
        and "\\" not in path
        and str(p) == path
        and len(path) < 250
        and not any(ord(c) < 32 for c in path)
    )


class SourceFile(StrictModel):
    text: str
    blob_sha: str
    size: int


class Snapshot(StrictModel):
    repository: str
    sha: str
    files: dict[str, SourceFile]
    skipped: list[str] = Field(default_factory=list)
    source: Literal["github", "pinned_fixture"] = "github"


class Evidence(StrictModel):
    id: str
    repository: str
    commit_sha: str
    path: str
    start_line: int
    end_line: int
    excerpt: str
    permalink: str


class Claim(StrictModel):
    id: str = Field(max_length=40)
    text: str = Field(min_length=1, max_length=1000)
    kind: Literal["architecture", "observation", "hypothesis"]
    evidence_ids: list[str] = Field(max_length=6)
    confidence: Literal["low", "medium", "high"]
    counter_evidence: str = Field(max_length=1000)


class Proposal(StrictModel):
    action: str = Field(max_length=1000)
    affected_files: list[str] = Field(max_length=8)
    compatibility: str = Field(max_length=1000)
    validation: str = Field(max_length=1000)


class Analysis(StrictModel):
    claims: list[Claim] = Field(max_length=16)
    proposals: list[Proposal] = Field(max_length=5)
    unanswered_questions: list[str] = Field(max_length=8)
    insufficient_evidence: bool

    @model_validator(mode="after")
    def unique_claims(self):
        ids = [c.id for c in self.claims]
        if len(ids) != len(set(ids)):
            raise ValueError("Claim IDs must be unique within a stage")
        return self


class Judgment(StrictModel):
    claim_id: str
    verdict: Literal["supported", "plausible", "unsupported", "insufficient_evidence"]
    reason: str = Field(max_length=1500)
    supporting_quote: str = Field(default="", max_length=1500)


class SemanticReview(StrictModel):
    judgments: list[Judgment] = Field(max_length=32)


class CitationCheck(StrictModel):
    evidence_id: str
    valid: bool
    reason: str


class VerifiedClaim(StrictModel):
    claim: Claim
    reference_valid: bool
    verdict: Literal["supported", "plausible", "unsupported", "insufficient_evidence"]
    reason: str
    supporting_quote: str = ""
    accepted_as_observation: bool


class Report(StrictModel):
    run_id: str
    repository: str
    commit_sha: str
    created_at: str
    issue: ResolvedIssue
    mode: str
    model: str
    prompt_version: str
    snapshot: Snapshot
    evidence: list[Evidence]
    documentation: Analysis
    investigation: Analysis
    citation_checks: list[CitationCheck]
    claims: list[VerifiedClaim]
    insufficient_evidence: bool
    timings: dict[str, float]
    usage: list[dict]
    proposal_findings: list[str] = Field(default_factory=list)
    tests_actually_run: list[str] = Field(default_factory=list)
    human_checklist: list[str] = Field(
        default_factory=lambda: [
            "Read cited source at the pinned commit.",
            "Review model support judgments; they are not a correctness guarantee.",
            "Validate hypotheses and proposed changes in a separate trusted development workflow.",
            "Run proposed correctness and performance checks before accepting a fix.",
        ]
    )
