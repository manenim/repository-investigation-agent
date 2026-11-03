from app.models import Report


def markdown(report: Report) -> str:
    r = report
    lines = [
        "# Repository investigation",
        "",
        f"- Run: `{r.run_id}`",
        f"- Repository: {r.repository}",
        f"- Commit: `{r.commit_sha}`",
        f"- Created: {r.created_at}",
        f"- Mode: {r.mode}; model: {r.model}; prompt: {r.prompt_version}",
        "",
        "## Issue context",
        "",
        r.issue.title,
        "",
        r.issue.body,
        "",
        "## Outcome",
        "",
        "Insufficient evidence for a complete conclusion."
        if r.insufficient_evidence
        else "Evidence-backed draft ready for human review; model judgments are not guarantees.",
        "",
        "## Architecture and relevant code paths",
        "",
    ]
    for kind, heading in [
        ("architecture", None),
        ("observation", "Direct observations"),
        ("hypothesis", "Hypotheses (not established causes)"),
    ]:
        if heading:
            lines += ["", "## " + heading, ""]
        for c in r.claims:
            if c.claim.kind != kind:
                continue
            lines += [
                f"- **[{c.verdict}; confidence={c.claim.confidence}]** {c.claim.text}",
                f"  - Evidence: {', '.join(c.claim.evidence_ids) or 'none'}; reference valid: {c.reference_valid}",
                f"  - Verification: {c.reason}",
                f"  - Counter-evidence/limits: {c.claim.counter_evidence}",
            ]
    lines += ["", "## Proposed fix and validation plan (not executed)", ""]
    for p in r.investigation.proposals:
        lines += [
            f"- {p.action}",
            f"  - Affected files: {', '.join(p.affected_files)}",
            f"  - Compatibility: {p.compatibility}",
            f"  - Proposed checks: {p.validation}",
        ]
    lines += [
        "",
        "## Tests actually run by this investigation",
        "",
        "None. Target repository code is never executed.",
        "",
        "## Evidence and deterministic citation verification",
        "",
    ]
    lines += ["## Proposal path review", ""] + ["- " + f for f in r.proposal_findings] + [""]
    checks = {c.evidence_id: c for c in r.citation_checks}
    for e in r.evidence:
        lines += [
            f"### {e.id}: [{e.path}:{e.start_line}-{e.end_line}]({e.permalink})",
            "",
            f"Repository: {e.repository}; commit: `{e.commit_sha}`; valid: {checks[e.id].valid}",
            "",
            "~~~~text",
            e.excerpt,
            "~~~~",
            "",
        ]
    lines += ["## Unresolved questions", ""]
    lines += ["- " + q for q in r.investigation.unanswered_questions]
    lines += ["", "## Human review checklist", ""]
    lines += ["- [ ] " + q for q in r.human_checklist]
    lines += [
        "",
        "## Stage timings and usage",
        "",
        str(r.timings),
        "",
        str(r.usage),
        "",
        f"Skipped paths: {', '.join(r.snapshot.skipped) or 'none'}",
        "",
    ]
    return "\n".join(lines)
