import asyncio

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import InvestigationInput
from app.providers import SampleProvider
from app.store import Store
from app.workflow import Worker

TOKEN = "a-long-test-access-token-with-32-characters"
AUTH = {"Authorization": "Bearer " + TOKEN}


def application(tmp_path, **kwargs):
    return create_app(
        Settings(
            _env_file=None,
            db_path=str(tmp_path / "runs.db"),
            access_token=TOKEN,
            provider="sample",
            source_mode="snapshot",
        ),
        **kwargs,
    )


def test_api_to_persisted_report_exports_and_restart(tmp_path):
    app = application(tmp_path)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").json()["ready"]
        assert client.post("/investigations", json={"title": "A", "body": "B"}).status_code == 401
        response = client.post(
            "/investigations",
            headers=AUTH,
            json={"title": "Redis timeout", "body": "Explain WithTimeout and EvalSha"},
        )
        assert response.status_code == 202
        run_id = response.json()["id"]
        # Queue completion is an observable synchronization point, not an arbitrary sleep.
        client.portal.call(app.state.worker.queue.join)
        run = client.get("/investigations/" + run_id, headers=AUTH).json()
        assert run["status"] == "complete", run
        assert run["report"]["mode"] == "offline_sample"
        assert all(c["valid"] for c in run["report"]["citation_checks"])
        assert client.get(f"/investigations/{run_id}/report.md", headers=AUTH).status_code == 200
        assert client.get(f"/investigations/{run_id}/report.json", headers=AUTH).json()[
            "commit_sha"
        ]
        assert client.get("/investigations/" + run_id).status_code == 401
        assert client.get("/investigations/missing", headers=AUTH).status_code == 404
        assert client.post("/investigations", content="x" * 12001, headers=AUTH).status_code == 413
        assert "script-src" in client.get("/").headers["content-security-policy"]
    with TestClient(application(tmp_path)) as client:
        assert client.get("/investigations/" + run_id, headers=AUTH).json()["status"] == "complete"


def test_admission_and_recovery(tmp_path):
    store = Store(str(tmp_path / "db"))
    req = InvestigationInput(title="A", body="B")
    run_id = store.create(req, daily=1)
    from app.store import AdmissionError

    with pytest.raises(AdmissionError, match="Daily"):
        store.create(req, daily=1)
    store.update(run_id, status="running", stage="documentation")
    store.recover()
    assert store.get(run_id)["status"] == "failed"
    assert "restarted" in store.get(run_id)["error"]


async def test_worker_failure_explicit_and_keeps_serving(tmp_path):
    class BrokenSource:
        async def ingest(self, request):
            raise RuntimeError("SECRET_IN_ERROR")

    store = Store(str(tmp_path / "db"))
    worker = Worker(store, BrokenSource(), SampleProvider)
    worker.start()
    try:
        for _ in range(2):
            run = store.create(InvestigationInput(title="A", body="B"))
            worker.queue.put_nowait(run)
            await asyncio.wait_for(worker.queue.join(), 2)
            assert store.get(run)["status"] == "failed"
            assert "SECRET" not in store.get(run)["error"]
        assert worker.queue.maxsize == 4
    finally:
        await worker.stop()


def test_queue_and_storage_admission(tmp_path):
    store = Store(str(tmp_path / "db"))
    req = InvestigationInput(title="A", body="B")
    from app.store import AdmissionError

    for _ in range(3):
        store.create(req)
    with pytest.raises(AdmissionError, match="minute"):
        store.create(req)
    with pytest.raises(AdmissionError, match="storage"):
        store.create(req, capacity=3)


def test_github_issue_report_can_be_loaded_and_exported(tmp_path):
    app = application(tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/investigations",
            headers=AUTH,
            json={"issue_url": "https://github.com/manenim/gateway-rate-limiter/issues/1"},
        )
        run_id = response.json()["id"]
        client.portal.call(app.state.worker.queue.join)
        result = client.get(f"/investigations/{run_id}/report.json", headers=AUTH)
        assert result.status_code == 200
        assert result.json()["issue"]["issue_url"].endswith("/issues/1")
        assert result.json()["issue"]["title"].startswith("Docs:")
