"""GET-only GitHub boundary. No repository code is executed or written."""

import asyncio
import base64
import hashlib
import json
import re
from contextlib import nullcontext
from pathlib import Path
from urllib.parse import quote

import httpx

from app.models import InvestigationInput, Snapshot, SourceFile, safe_path

MAX_FILES = 60
MAX_FILE_BYTES = 40_000
MAX_TOTAL_BYTES = 512_000
MAX_TREE_ENTRIES = 2000
ROOT = Path(__file__).resolve().parents[1]


class IngestionError(Exception):
    pass


def blob_hash(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def eligible(path: str) -> bool:
    return (
        safe_path(path)
        and not any(
            p in path.split("/")
            for p in ["vendor", "node_modules", ".git", "dist", "generated", "benchmark-records"]
        )
        and path.endswith((".go", ".lua", ".md", ".mod"))
        and not path.endswith((".pb.go", "_grpc.pb.go"))
    )


class GitHubSource:
    def __init__(self, token: str = "", transport=None):
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            self.headers["Authorization"] = "Bearer " + token
        self.transport = transport
        self._client: httpx.AsyncClient | None = None

    async def get(self, route: str, limit: int = 2_000_000):
        # route is constructed by application code; redirects are never followed.
        for attempt in range(3):
            try:
                async with (
                    nullcontext(self._client)
                    if self._client
                    else httpx.AsyncClient(
                        base_url="https://api.github.com",
                        headers=self.headers,
                        timeout=httpx.Timeout(20, connect=10),
                        follow_redirects=False,
                        transport=self.transport,
                    )
                ) as client:
                    async with client.stream("GET", route) as response:
                        if response.status_code in (429, 502, 503, 504):
                            raise httpx.ReadTimeout("Transient GitHub failure")
                        if (
                            response.status_code == 403
                            and response.headers.get("x-ratelimit-remaining") == "0"
                        ):
                            raise IngestionError(
                                "GitHub rate limit exhausted; configure a read-only GITHUB_TOKEN"
                            )
                        if response.status_code != 200:
                            raise IngestionError(f"GitHub returned HTTP {response.status_code}")
                        raw = bytearray()
                        async for part in response.aiter_bytes():
                            raw.extend(part)
                            if len(raw) > limit:
                                raise IngestionError("GitHub response exceeded download budget")
                        return json.loads(raw)
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 2:
                    raise IngestionError(
                        "GitHub unavailable after three bounded attempts"
                    ) from None
                await asyncio.sleep(0.2 * 2**attempt)
        raise IngestionError("GitHub unavailable")

    async def ingest(self, request: InvestigationInput) -> tuple[Snapshot, InvestigationInput]:
        async with httpx.AsyncClient(
            base_url="https://api.github.com",
            headers=self.headers,
            timeout=httpx.Timeout(20, connect=10),
            follow_redirects=False,
            transport=self.transport,
        ) as client:
            self._client = client
            try:
                return await self._ingest(request)
            finally:
                self._client = None

    async def _ingest(self, request: InvestigationInput) -> tuple[Snapshot, InvestigationInput]:
        repo = request.repository
        metadata = await self.get(f"/repos/{repo}", 32_000)
        if metadata.get("private") is not False or metadata.get("full_name") != repo:
            raise IngestionError("Only the allowlisted public repository is permitted")
        commit = await self.get(f"/repos/{repo}/commits/{quote(request.ref, safe='')}")
        sha = commit.get("sha", "")
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise IngestionError("GitHub did not resolve an immutable commit")
        tree = await self.get(f"/repos/{repo}/git/trees/{sha}?recursive=1")
        if tree.get("truncated") or len(tree.get("tree", [])) > MAX_TREE_ENTRIES:
            raise IngestionError("Repository inventory exceeds supported size")
        files: dict[str, SourceFile] = {}
        skipped = []
        entries = [e for e in tree["tree"] if e.get("type") == "blob"]
        selected = [e for e in entries if eligible(e["path"]) and e.get("mode") == "100644"]
        if len(selected) > MAX_FILES:
            raise IngestionError("Too many eligible files; narrow repository support required")
        total = 0
        for entry in entries:
            path = entry["path"]
            if entry not in selected or entry.get("size", MAX_FILE_BYTES + 1) > MAX_FILE_BYTES:
                skipped.append(path)
                continue
            total += entry["size"]
            if total > MAX_TOTAL_BYTES:
                raise IngestionError("Repository source exceeds total byte budget")
            blob = await self.get(f"/repos/{repo}/git/blobs/{entry['sha']}", 65_000)
            if blob.get("encoding") != "base64":
                raise IngestionError("Unexpected GitHub blob encoding")
            raw = base64.b64decode(blob["content"])
            if len(raw) != entry["size"] or blob_hash(raw) != entry["sha"]:
                raise IngestionError("Blob integrity mismatch")
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                skipped.append(path)
                continue
            if "\0" in text:
                skipped.append(path)
                continue
            files[path] = SourceFile(text=text, blob_sha=entry["sha"], size=len(raw))
        if request.issue_url:
            number = request.issue_url.rsplit("/", 1)[1]
            issue = await self.get(f"/repos/{repo}/issues/{number}", 64_000)
            if "pull_request" in issue:
                raise IngestionError("Expected an issue, not a pull request")
            if len(str(issue["title"])) > 200 or len(str(issue.get("body") or "")) > 6000:
                raise IngestionError(
                    "GitHub issue exceeds the supported title/body budget; paste a shorter description"
                )
            request = request.model_copy(
                update={"title": str(issue["title"]), "body": str(issue.get("body") or "")}
            )
        return Snapshot(repository=repo, sha=sha, files=files, skipped=skipped), request


class FixtureSource:
    """Explicit offline sample mode, never silently substituted for live GitHub."""

    async def ingest(self, request: InvestigationInput) -> tuple[Snapshot, InvestigationInput]:
        data = json.loads((ROOT / "evals/snapshot.json").read_text())
        if request.ref not in ("main", data["sha"]):
            raise IngestionError("Offline sample only supports the bundled commit or main alias")
        if request.issue_url:
            if not request.issue_url.endswith("/issues/1"):
                raise IngestionError("Only issue #1 is bundled in the offline fixture")
            request = request.model_copy(
                update={"title": data["issue"]["title"], "body": data["issue"]["body"][:6000]}
            )
        files = {p: SourceFile.model_validate(f) for p, f in data["files"].items() if eligible(p)}
        for f in files.values():
            if blob_hash(f.text.encode()) != f.blob_sha:
                raise IngestionError("Bundled fixture failed blob integrity check")
        return Snapshot(
            repository=data["repository"], sha=data["sha"], files=files, source="pinned_fixture"
        ), request
