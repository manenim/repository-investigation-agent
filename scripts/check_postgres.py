"""Exercise the real PostgreSQL adapter without printing connection secrets."""

import json
import os
from pathlib import Path

from dotenv import dotenv_values
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import InvestigationInput
from app.store import AdmissionError, Store


def check(url: str):
    token = "postgres-integration-test-token-32-characters"
    settings = Settings(
        _env_file=None,
        database_url=url,
        access_token=token,
        provider="sample",
        source_mode="snapshot",
    )
    app = create_app(settings)
    auth = {"Authorization": "Bearer " + token}
    created = []
    try:
        with TestClient(app) as client:
            assert client.get("/ready").status_code == 200
            response = client.post(
                "/investigations",
                headers=auth,
                json={"title": "PostgreSQL integration check", "body": "Trace Redis Allow"},
            )
            assert response.status_code == 202
            run_id = response.json()["id"]
            created.append(run_id)
            client.portal.call(app.state.worker.queue.join)
            report = client.get(f"/investigations/{run_id}/report.json", headers=auth)
            assert report.status_code == 200
            assert report.json()["snapshot"]["sha"]
            markdown = client.get(f"/investigations/{run_id}/report.md", headers=auth)
            assert markdown.status_code == 200
            before = report.content
        with TestClient(create_app(settings)) as client:
            assert (
                client.get(f"/investigations/{run_id}/report.json", headers=auth).content == before
            )
        store = Store(url)
        interrupted = store.create(
            InvestigationInput(title="PG recovery", body="Deliberate interruption"),
            enforce_submission_limits=False,
        )
        created.append(interrupted)
        store.update(interrupted, status="running")
        store.recover()
        assert store.get(interrupted)["status"] == "failed"
        try:
            store.create(InvestigationInput(title="Admission", body="Capacity check"), capacity=1)
        except AdmissionError:
            pass
        else:
            raise AssertionError("Capacity enforcement did not reject")
        return {
            "backend": "postgresql",
            "api_to_report": True,
            "json_and_markdown_export": True,
            "report_survives_app_restart": True,
            "interrupted_run_marked_failed": True,
            "capacity_admission_enforced": True,
            "mode": "deterministic_provider_real_database",
        }
    finally:
        with Store(url).connect() as db:
            for run_id in created:
                db.execute("DELETE FROM runs WHERE id=?", (run_id,))


if __name__ == "__main__":
    url = os.getenv("TEST_POSTGRES_URL") or dotenv_values(".env.render").get(
        "EXTERNAL_DATABASE_URL"
    )
    if not url:
        raise SystemExit("Configure TEST_POSTGRES_URL or the ignored Render connection file")
    try:
        result = check(url)
        Path("evals/results/postgres-integration.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
    except Exception as exc:
        print("PostgreSQL integration failed:", type(exc).__name__)
        raise SystemExit(1) from None
