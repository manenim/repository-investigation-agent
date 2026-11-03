"""Deterministic lexical/symbol retrieval with stable original line numbers."""

import math
import re
from collections import Counter
from urllib.parse import quote

from app.models import Evidence, Snapshot

CONTEXT_BYTES = 20_000  # conservative token upper bound: UTF-8 bytes >= text tokens


def terms(text: str) -> list[str]:
    split = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    return [
        t[:-1] if t.endswith("s") and len(t) > 4 else t
        for t in re.findall(r"[a-z][a-z0-9_]{1,}", split.lower())
    ]


def retrieve(snapshot: Snapshot, query: str, budget: int = CONTEXT_BYTES) -> list[Evidence]:
    chunks = []
    for path, file in sorted(snapshot.files.items()):
        lines = file.text.splitlines()
        for start in range(0, len(lines), 34):
            end = min(start + 44, len(lines))
            excerpt = "\n".join(lines[start:end])
            chunks.append((path, start + 1, end, excerpt, Counter(terms(path + " " + excerpt))))
    query_terms = set(terms(query)) - {"the", "is", "of", "and", "to", "in", "for", "what", "how"}
    frequencies = Counter(t for c in chunks for t in c[4])

    def score(chunk):
        path, _, _, _, counts = chunk
        value = sum(
            (1 + math.log(counts[t])) * math.log(1 + len(chunks) / (1 + frequencies[t]))
            for t in query_terms
            if counts[t]
        )
        if path.endswith((".go", ".lua")) and not path.endswith("_test.go"):
            value *= 1.4
        if path.endswith("_test.go"):
            value *= 0.85
        return value

    ranked = sorted(chunks, key=lambda c: (-score(c), c[0], c[1]))
    # Reserve a small architecture anchor so investigations include the public contract.
    anchors = [c for c in chunks if c[0] == "model.go" and c[1] == 1]
    if "diagram" in query_terms or "mermaid" in query_terms:
        anchors += [c for c in chunks if c[0] in ("docs/architecture.md", "docs/sequence.md")]
    # Prefer distinct files before additional chunks from a long README or test file.
    diverse = []
    per_path: Counter[str] = Counter()
    deferred = []
    for c in ranked:
        if per_path[c[0]] < 2:
            diverse.append(c)
            per_path[c[0]] += 1
        else:
            deferred.append(c)
    chosen = anchors + diverse + deferred
    result: list[Evidence] = []
    used = set()
    total = 0
    for path, start, end, excerpt, _ in chosen:
        if (path, start) in used:
            continue
        cost = len(excerpt.encode()) + len(path) + 400
        if total + cost > budget or len(result) >= 10:
            continue
        used.add((path, start))
        total += cost
        result.append(
            Evidence(
                id=f"E{len(result) + 1}",
                repository=snapshot.repository,
                commit_sha=snapshot.sha,
                path=path,
                start_line=start,
                end_line=end,
                excerpt=excerpt,
                permalink=f"https://github.com/{snapshot.repository}/blob/"
                f"{snapshot.sha}/{quote(path, safe='/')}#L{start}-L{end}",
            )
        )
    return result
