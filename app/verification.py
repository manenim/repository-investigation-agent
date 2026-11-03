from typing import Literal
from urllib.parse import quote

from app.ingestion import blob_hash
from app.models import (
    CitationCheck,
    Claim,
    Evidence,
    SemanticReview,
    Snapshot,
    VerifiedClaim,
    safe_path,
)


def check_citations(snapshot: Snapshot, evidence: list[Evidence]) -> list[CitationCheck]:
    checks = []
    seen = set()
    for e in evidence:
        file = snapshot.files.get(e.path)
        expected_url = (
            f"https://github.com/{snapshot.repository}/blob/{snapshot.sha}/"
            f"{quote(e.path, safe='/')}#L{e.start_line}-L{e.end_line}"
        )
        valid = (
            e.id not in seen
            and safe_path(e.path)
            and file is not None
            and e.repository == snapshot.repository
            and e.commit_sha == snapshot.sha
            and e.permalink == expected_url
        )
        seen.add(e.id)
        if valid and file:
            lines = file.text.splitlines()
            valid = (
                1 <= e.start_line <= e.end_line <= len(lines)
                and "\n".join(lines[e.start_line - 1 : e.end_line]) == e.excerpt
                and blob_hash(file.text.encode()) == file.blob_sha
            )
        checks.append(
            CitationCheck(
                evidence_id=e.id,
                valid=valid,
                reason="Pinned blob, path, lines and excerpt match"
                if valid
                else "Reference identity, range, excerpt or pinned blob is invalid",
            )
        )
    return checks


def reconcile(
    claims: list[Claim],
    checks: list[CitationCheck],
    review: SemanticReview,
    evidence: list[Evidence] | None = None,
) -> list[VerifiedClaim]:
    excerpts = {e.id: e.excerpt for e in (evidence or [])}
    refs = {c.evidence_id: c.valid for c in checks}
    counts = {c.id: sum(j.claim_id == c.id for j in review.judgments) for c in claims}
    judgments = {j.claim_id: j for j in review.judgments}
    output = []
    for c in claims:
        valid = bool(c.evidence_ids) and all(refs.get(e, False) for e in c.evidence_ids)
        judgment = judgments.get(c.id)
        verdict: Literal["supported", "plausible", "unsupported", "insufficient_evidence"] = (
            "insufficient_evidence"
        )
        reason = "Missing or duplicate independent support judgment"
        if judgment and counts[c.id] == 1:
            verdict, reason = judgment.verdict, judgment.reason
        if not valid:
            verdict, reason = (
                "unsupported",
                "Missing or invalid citation; semantic judgment overridden",
            )
        if verdict in ("supported", "plausible"):
            quote_text = judgment.supporting_quote if judgment else ""
            if len(quote_text.strip()) < 12 or not any(
                quote_text in excerpts.get(eid, "") for eid in c.evidence_ids
            ):
                verdict = "insufficient_evidence"
                reason = (
                    "Support judgment lacks an exact quotation from this claim's cited evidence"
                )
        # Hypotheses remain hypotheses even if the model overstates confidence.
        if c.kind == "hypothesis" and verdict == "supported":
            verdict = "plausible"
        output.append(
            VerifiedClaim(
                claim=c,
                reference_valid=valid,
                verdict=verdict,
                reason=reason,
                supporting_quote=judgment.supporting_quote if judgment else "",
                accepted_as_observation=valid and verdict == "supported" and c.kind != "hypothesis",
            )
        )
    return output
