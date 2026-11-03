"""Separate live semantic-verifier probe against source-inspected positive/negative claims."""

import asyncio
import json
from pathlib import Path

from app.config import Settings
from app.ingestion import FixtureSource
from app.models import Claim, InvestigationInput
from app.providers import OpenAIProvider
from app.retrieval import retrieve
from app.verification import check_citations, reconcile


async def main():
    snapshot, _ = await FixtureSource().ingest(InvestigationInput(title="A", body="B"))
    evidence = retrieve(snapshot, "RateLimiter interface Allow")
    witness = next(e for e in evidence if e.path == "model.go" and e.start_line <= 35 <= e.end_line)
    claims = [
        Claim(
            id="supported-interface",
            text="The RateLimiter interface declares Allow with context.Context, Identity and Limit parameters, returning Decision and error.",
            kind="observation",
            evidence_ids=[witness.id],
            confidence="high",
            counter_evidence="Source-level interface declaration only.",
        ),
        Claim(
            id="unsupported-performance",
            text="This repository reduced production p99 latency by 90% after a deployed fix yesterday.",
            kind="observation",
            evidence_ids=[witness.id],
            confidence="high",
            counter_evidence="No runtime measurements supplied.",
        ),
        Claim(
            id="unsupported-rendering",
            text="pkg.go.dev was tested and renders every Mermaid diagram correctly.",
            kind="observation",
            evidence_ids=[witness.id],
            confidence="high",
            counter_evidence="No rendering tests supplied.",
        ),
    ]
    s = Settings()
    p = OpenAIProvider(s.openai_api_key, s.openai_model)
    try:
        review = await p.review(claims, evidence)
        result = reconcile(claims, check_citations(snapshot, evidence), review, evidence)
        output = {
            "mode": "live_model",
            "model": p.model,
            "judgments": review.model_dump(),
            "reconciled": [c.model_dump() for c in result],
            "usage": p.usage,
            "expected": {
                "supported-interface": "supported",
                "unsupported-performance": "unsupported",
                "unsupported-rendering": "unsupported",
            },
        }
        Path("evals/results/live/claim-probe.json").write_text(json.dumps(output, indent=2))
        print([(c.claim.id, c.verdict) for c in result])
    finally:
        await p.client.close()


if __name__ == "__main__":
    asyncio.run(main())
