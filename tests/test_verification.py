import pytest

from app.models import Claim, Judgment, SemanticReview
from app.retrieval import retrieve
from app.verification import check_citations, reconcile


def claim(evidence_ids=None, kind="observation"):
    return Claim(
        id="c1",
        text="All production errors have been fixed",
        kind=kind,
        evidence_ids=evidence_ids or ["E1"],
        confidence="high",
        counter_evidence="None",
    )


@pytest.mark.parametrize(
    "change",
    [
        {"path": "missing.go"},
        {"start_line": 0},
        {"end_line": 999999},
        {"excerpt": "fabricated"},
        {"commit_sha": "b" * 40},
        {"repository": "attacker/repo"},
        {"permalink": "https://evil.test"},
    ],
)
def test_fabricated_citations(snapshot, change):
    e = retrieve(snapshot, "Redis")[0].model_copy(update=change)
    assert not check_citations(snapshot, [e])[0].valid


def test_semantic_rejection_is_independent_of_valid_reference(snapshot):
    evidence = retrieve(snapshot, "Redis")
    checks = check_citations(snapshot, evidence)
    c = claim()
    result = reconcile(
        [c],
        checks,
        SemanticReview(
            judgments=[
                Judgment(
                    claim_id="c1",
                    verdict="unsupported",
                    reason="Code does not establish a production event",
                )
            ]
        ),
    )[0]
    assert result.reference_valid
    assert not result.accepted_as_observation
    assert result.verdict == "unsupported"


def test_missing_duplicate_or_unreferenced_review_fails_closed(snapshot):
    evidence = retrieve(snapshot, "Redis")
    checks = check_citations(snapshot, evidence)
    judgment = Judgment(
        claim_id="c1", verdict="supported", reason="yes", supporting_quote=evidence[0].excerpt[:100]
    )
    for review in [SemanticReview(judgments=[]), SemanticReview(judgments=[judgment, judgment])]:
        result = reconcile([claim()], checks, review)[0]
        assert not result.accepted_as_observation
    assert (
        reconcile([claim(["E999"])], checks, SemanticReview(judgments=[judgment]))[0].verdict
        == "unsupported"
    )
    assert (
        reconcile(
            [claim(kind="hypothesis")], checks, SemanticReview(judgments=[judgment]), evidence
        )[0].verdict
        == "plausible"
    )


def test_exact_quote_from_wrong_evidence_does_not_pass(snapshot):
    evidence = retrieve(snapshot, "Redis")
    checks = check_citations(snapshot, evidence)
    c = claim([evidence[0].id])
    review = SemanticReview(
        judgments=[
            Judgment(
                claim_id=c.id,
                verdict="supported",
                reason="incorrect model verdict",
                supporting_quote="This quotation is not in the cited source at all.",
            )
        ]
    )
    result = reconcile([c], checks, review, evidence)[0]
    assert result.reference_valid
    assert result.verdict == "insufficient_evidence"
    assert not result.accepted_as_observation
