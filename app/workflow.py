import asyncio
import logging
import time
from collections.abc import Callable

from app.models import Analysis, InvestigationInput, Report, ResolvedIssue, safe_path
from app.providers import PROMPT_VERSION, Provider
from app.retrieval import retrieve
from app.store import Store
from app.verification import check_citations, reconcile

log = logging.getLogger(__name__)


async def investigate(store: Store, run_id: str, source, provider: Provider) -> Report:
    run = store.get(run_id)
    if run is None:
        raise ValueError("Missing run")
    issue = InvestigationInput.model_validate(run["request"])
    timings = {}
    progress: dict[str, dict] = {}

    async def stage(name, work):
        store.update(run_id, status="running", stage=name, progress=progress)
        started = time.monotonic()
        try:
            result = await work()
        finally:
            timings[name] = round(time.monotonic() - started, 3)
        progress[name] = {"seconds": timings[name], "status": "complete"}
        if name in ("documentation", "investigation"):
            progress[name]["artifact"] = result.model_dump()
        store.update(run_id, progress=progress)
        log.info("run=%s stage=%s seconds=%.3f", run_id, name, timings[name])
        return result

    snapshot, issue = await stage("ingestion", lambda: source.ingest(issue))

    progress["ingestion"].update(
        commit_sha=snapshot.sha,
        files=len(snapshot.files),
        skipped=snapshot.skipped,
        model=provider.model,
        prompt_version=PROMPT_VERSION,
    )

    async def select():
        return retrieve(snapshot, issue.title + " " + issue.body)

    evidence = await stage("retrieval", select)
    progress["retrieval"]["evidence"] = [e.model_dump() for e in evidence]
    if not evidence:
        raise ValueError("No source evidence available under the configured budget")
    documentation = await stage(
        "documentation", lambda: provider.analyze("documentation", issue, evidence)
    )
    investigation = await stage(
        "investigation", lambda: provider.analyze("investigation", issue, evidence, documentation)
    )
    # Prefix model-supplied IDs so stage IDs cannot collide.
    documentation = Analysis.model_validate(documentation.model_dump())
    investigation = Analysis.model_validate(investigation.model_dump())
    for prefix, artifact in [("doc", documentation), ("issue", investigation)]:
        for claim in artifact.claims:
            claim.id = prefix + ":" + claim.id
    claims = documentation.claims + investigation.claims

    async def verify():
        checks = check_citations(snapshot, evidence)
        review = await provider.review(claims, evidence)
        return checks, reconcile(claims, checks, review, evidence)

    checks, verified = await stage("verification", verify)
    proposal_findings = []
    for proposal in investigation.proposals + documentation.proposals:
        for path in proposal.affected_files:
            if not safe_path(path):
                proposal_findings.append("Unsafe proposed path removed from plan")
            elif path not in snapshot.files:
                proposal_findings.append(
                    f"{path}: proposed file is absent from the inspected snapshot; confirm whether a new file is intended."
                )
        proposal.affected_files = [p for p in proposal.affected_files if safe_path(p)]
    insufficient = (
        investigation.insufficient_evidence
        or not any(c.accepted_as_observation and c.claim.id.startswith("issue:") for c in verified)
        or bool(proposal_findings)
        or any(c.verdict in ("unsupported", "insufficient_evidence") for c in verified)
    )
    report = Report(
        run_id=run_id,
        repository=snapshot.repository,
        commit_sha=snapshot.sha,
        created_at=run["created_at"],
        issue=ResolvedIssue.model_validate(issue.model_dump()),
        mode=provider.mode,
        model=provider.model,
        prompt_version=PROMPT_VERSION,
        snapshot=snapshot,
        proposal_findings=proposal_findings,
        evidence=evidence,
        documentation=documentation,
        investigation=investigation,
        citation_checks=checks,
        claims=verified,
        insufficient_evidence=insufficient,
        timings=timings,
        usage=provider.usage,
    )
    store.update(run_id, status="complete", stage="complete", progress=progress, report=report)
    return report


class Worker:
    """One worker and four pending slots; no distributed or durable execution claims."""

    def __init__(self, store: Store, source, provider_factory: Callable[[], Provider]):
        self.store = store
        self.source = source
        self.provider_factory = provider_factory
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=4)
        self.task: asyncio.Task | None = None

    def start(self):
        self.store.recover()
        self.task = asyncio.create_task(self.loop())

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.store.recover()

    async def loop(self):
        while True:
            run_id = await self.queue.get()
            provider = None
            try:
                provider = self.provider_factory()
                async with asyncio.timeout(420):
                    await investigate(self.store, run_id, self.source, provider)
            except asyncio.CancelledError:
                self.store.update(run_id, status="failed", error="Worker stopped before completion")
                raise
            except Exception as exc:
                # Exception messages may contain prompts or credentials: never log them.
                from app.ingestion import IngestionError
                from app.providers import ProviderError

                message = (
                    str(exc)
                    if isinstance(exc, (IngestionError, ProviderError))
                    else (
                        "Workflow failed validation or exceeded its deadline. Operator review required."
                    )
                )
                log.warning("run=%s failed_type=%s", run_id, type(exc).__name__)
                self.store.update(run_id, status="failed", error=message)
            finally:
                client = getattr(provider, "client", None)
                if client is not None:
                    await client.close()
                self.queue.task_done()
