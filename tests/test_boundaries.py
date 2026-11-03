import base64

import httpx
import pytest
from pydantic import ValidationError

from app.ingestion import GitHubSource, IngestionError, blob_hash
from app.models import InvestigationInput, safe_path
from app.retrieval import retrieve
from app.verification import check_citations


@pytest.mark.parametrize(
    "changes",
    [
        {"repository": "other/repo"},
        {"issue_url": "http://127.0.0.1/secrets"},
        {
            "issue_url": "https://github.com/manenim/gateway-rate-limiter/issues/1?url=http://localhost"
        },
        {"issue_url": "https://github.com/manenim/task-orchestrator/issues/1"},
        {"ref": "../main"},
        {"ref": "main?token=x"},
        {"ref": "main//x"},
        {"ref": "HEAD@{1}"},
        {"ref": "/main"},
        {"ref": "main.lock"},
        {"body": "x" * 6001},
    ],
)
def test_input_rejects_unsafe_values(changes):
    values = {"title": "Question", "body": "Description", **changes}
    with pytest.raises(ValidationError):
        InvestigationInput(**values)


def test_issue_inputs_and_valid_refs():
    for ref in ["main", "feature/timeout", "v1.0.0", "a" * 40]:
        assert InvestigationInput(ref=ref, title="T", body="B").ref == ref
    with pytest.raises(ValidationError):
        InvestigationInput()
    assert InvestigationInput(issue_url="https://github.com/manenim/gateway-rate-limiter/issues/1")


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", "a/../b", "a\\b", "a//b", "a\x00b"])
def test_paths(path):
    assert not safe_path(path)


def test_retrieval_and_line_mapping(snapshot):
    ev = retrieve(snapshot, "RedisLimiter EvalSha timeout ScriptLoad", budget=20_000)
    assert any(e.path == "redis.go" and e.start_line <= 103 <= e.end_line for e in ev)
    assert all(c.valid for c in check_citations(snapshot, ev))
    assert sum(len(e.excerpt.encode()) + len(e.path) + 400 for e in ev) <= 20_000
    for e in ev:
        assert e.excerpt == "\n".join(
            snapshot.files[e.path].text.splitlines()[e.start_line - 1 : e.end_line]
        )


async def test_ingestion_timeouts_bounded():
    calls = []

    def fail(request):
        calls.append(request)
        raise httpx.ReadTimeout("secret prompt must never be propagated")

    with pytest.raises(IngestionError, match="three bounded"):
        await GitHubSource(transport=httpx.MockTransport(fail)).get(
            "/repos/manenim/gateway-rate-limiter"
        )
    assert len(calls) == 3
    assert all(r.method == "GET" and r.url.host == "api.github.com" for r in calls)


async def test_download_budget_and_no_redirects():
    source = GitHubSource(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 100))
    )
    with pytest.raises(IngestionError, match="budget"):
        await source.get("/test", limit=50)
    source = GitHubSource(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(302, headers={"location": "http://localhost"})
        )
    )
    with pytest.raises(IngestionError, match="302"):
        await source.get("/test")


def git_mock(*, size=15, private=False, corrupt=False, truncated=False):
    data = b"package limiter"
    sha = blob_hash(data)

    def handler(request):
        route = request.url.path
        if route.endswith("/gateway-rate-limiter"):
            d = {"private": private, "full_name": "manenim/gateway-rate-limiter"}
        elif "/commits/" in route:
            d = {"sha": "a" * 40}
        elif "/trees/" in route:
            d = {
                "truncated": truncated,
                "tree": [
                    {
                        "path": "model.go",
                        "type": "blob",
                        "mode": "100644",
                        "size": size,
                        "sha": sha,
                    },
                    {
                        "path": "../secret.go",
                        "type": "blob",
                        "mode": "100644",
                        "size": 5,
                        "sha": sha,
                    },
                    {
                        "path": "vendor/x.go",
                        "type": "blob",
                        "mode": "100644",
                        "size": 5,
                        "sha": sha,
                    },
                ],
            }
        else:
            d = {
                "encoding": "base64",
                "content": base64.b64encode(b"wrong" if corrupt else data).decode(),
            }
        return httpx.Response(200, json=d)

    return GitHubSource(transport=httpx.MockTransport(handler))


async def test_ingestion_skips_unsafe_vendor_oversize():
    req = InvestigationInput(title="A", body="B")
    snap, _ = await git_mock().ingest(req)
    assert list(snap.files) == ["model.go"]
    assert "../secret.go" in snap.skipped
    snap, _ = await git_mock(size=40_001).ingest(req)
    assert not snap.files
    for source in [git_mock(private=True), git_mock(corrupt=True), git_mock(truncated=True)]:
        with pytest.raises(IngestionError):
            await source.ingest(req)
