import hmac
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import Settings
from app.export import markdown
from app.ingestion import ROOT, FixtureSource, GitHubSource
from app.models import InvestigationInput, Report
from app.providers import OpenAIProvider, SampleProvider
from app.store import AdmissionError, Store
from app.workflow import Worker

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpx2").setLevel(logging.WARNING)


def create_app(settings: Settings | None = None, source=None, provider_factory=None) -> FastAPI:
    config = settings or Settings()
    if config.render and not config.database_url:
        raise RuntimeError("Render deployment requires DATABASE_URL; ephemeral SQLite is refused")
    store = Store(config.database_url or config.db_path)
    source = source or (
        FixtureSource() if config.source_mode == "snapshot" else GitHubSource(config.github_token)
    )
    factory = provider_factory or (
        SampleProvider
        if config.provider == "sample"
        else lambda: OpenAIProvider(config.openai_api_key, config.openai_model)
    )
    worker = Worker(store, source, factory)

    @asynccontextmanager
    async def lifespan(app):
        worker.start()
        yield
        await worker.stop()
        store.close()

    app = FastAPI(title="Trace / Repository Investigation", version="0.1.0", lifespan=lifespan)
    app.state.store, app.state.worker = store, worker

    @app.middleware("http")
    async def limits_and_headers(request: Request, call_next):
        if request.method == "POST":
            size = 0
            parts = []
            async for part in request.stream():
                size += len(part)
                if size > 12_000:
                    return JSONResponse({"detail": "Request exceeds 12 KB limit"}, status_code=413)
                parts.append(part)
            request._body = b"".join(parts)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    async def authenticate(authorization: str = Header(default="")):
        if not config.access_token or len(config.access_token) < 24:
            raise HTTPException(503, "Operator must configure a strong ACCESS_TOKEN")
        expected = "Bearer " + config.access_token
        if not hmac.compare_digest(authorization.encode(), expected.encode()):
            raise HTTPException(401, "Enter a valid demo access token")

    def find(run_id):
        if len(run_id) != 32 or any(c not in "0123456789abcdef" for c in run_id):
            raise HTTPException(404, "Investigation not found")
        run = store.get(run_id)
        if run is None:
            raise HTTPException(404, "Investigation not found")
        return run

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/ready")
    async def ready():
        try:
            with store.connect() as db:
                db.execute("SELECT 1").fetchone()
            healthy = worker.task is not None and not worker.task.done()
        except Exception:
            healthy = False
        return JSONResponse({"ready": healthy}, status_code=200 if healthy else 503)

    @app.get("/config")
    async def public_config():
        return {
            "repository": "manenim/gateway-rate-limiter",
            "provider": config.provider,
            "deployment_notice": config.deployment_notice,
            "source": config.source_mode,
            "generation_configured": bool(
                len(config.access_token) >= 24
                and (config.openai_api_key or config.provider == "sample")
            ),
        }

    @app.post("/investigations", status_code=202, dependencies=[Depends(authenticate)])
    async def create(request: InvestigationInput):
        if config.provider != "sample" and not config.openai_api_key:
            raise HTTPException(503, "Live generation needs an operator-configured model API key")
        if not worker.task or worker.task.done():
            raise HTTPException(503, "Worker is unavailable")
        if worker.queue.full():
            raise HTTPException(429, "Investigation queue is full; try again later")
        try:
            run_id = store.create(request, config.max_daily_runs, config.max_stored_runs)
        except AdmissionError as exc:
            raise HTTPException(429, str(exc)) from None
        worker.queue.put_nowait(run_id)
        return {"id": run_id, "status": "queued", "status_url": f"/investigations/{run_id}"}

    @app.get("/investigations/{run_id}", dependencies=[Depends(authenticate)])
    async def get(run_id: str):
        return find(run_id)

    def completed_report(run_id):
        run = find(run_id)
        if run["status"] != "complete":
            raise HTTPException(409, "Report is not complete")
        return Report.model_validate(run["report"])

    @app.get("/investigations/{run_id}/report.md", dependencies=[Depends(authenticate)])
    async def export_md(run_id: str):
        return Response(
            markdown(completed_report(run_id)),
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{run_id}.md"'},
        )

    @app.get("/investigations/{run_id}/report.json", dependencies=[Depends(authenticate)])
    async def export_json(run_id: str):
        return Response(
            completed_report(run_id).model_dump_json(indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{run_id}.json"'},
        )

    @app.get("/sample.md")
    async def sample_markdown():
        path = ROOT / "evals/sample-report.md"
        if not path.exists():
            raise HTTPException(404, "Sample Markdown unavailable")
        return FileResponse(path, media_type="text/markdown", filename="sample-report.md")

    @app.get("/sample")
    async def sample():
        path = ROOT / "evals/sample-report.json"
        if not path.exists():
            raise HTTPException(404, "Sample report has not yet been generated")
        return JSONResponse(json.loads(path.read_text()))

    @app.get("/")
    async def home():
        return FileResponse(Path(__file__).parent / "static/index.html")

    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    return app


app = create_app()
