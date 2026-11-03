# Evaluation protocol and limitations

## Fixture basis

`evals/cases.json` version v1 contains 12 cases grounded in the pinned public source in `evals/snapshot.json`. Expected facts and unacceptable claims were written from direct source inspection before live evaluations. The fixture is not a model-generated answer key. Case `docs-issue` refers to real public issue #1; all other scenarios are explicitly local evaluation questions. Nothing was posted to GitHub.

Witness regions were inspected in `model.go` (interface and policy), `memory.go` (mutex, refill, burst clamp), `redis.go` (initialization timeout, caller context, EvalSha errors, metric instrumentation), `token_bucket.lua` (allowed writes, TTL, denied retry), `cmd/example-server/main.go` (IP identity, fail-open branch, rounding), their existing test source, and the diagram/README source. Tests found in the repository are evidence of assertions, not proof that they passed. No target code was run.

## Reproduce

```sh
python -m pytest -q --junitxml=evals/results/tests.xml
python -m scripts.evaluate
python -m scripts.evaluate --live
python -m scripts.claim_probe
```

The live runner calls the configured real API against the same pinned source; it does not fetch changing default-branch contents. Full live-GitHub ingestion is exercised separately by the container smoke test and browser flow. Evaluation runs use a separate SQLite database with submission-rate enforcement disabled only inside the local runner. The HTTP service always applies its admission limits. No provider credentials are passed to mock tests.

## Metrics kept separate

1. **Retrieval region coverage:** a witness is covered if a retrieved chunk overlaps its annotated path and line region. Report the exact covered/total counts. Overlap does not prove the whole region or answer was retrieved; this is a coarse recall proxy. Cases with no expected region are excluded, not counted as successes. The initial baseline and later results are retained; these fixtures informed retrieval changes, so this is a development set, not an independent holdout.
2. **Citation validity:** exact repository/SHA/path/range/permalink/excerpt/blob checks. Report the actual checks counted. Retrieval citations and final report citations are distinguishable in raw files. Valid references do not prove semantic support.
3. **Supported-claim accuracy:** source-inspect a representative subset: an architecture case, a known behavior case, and an insufficient-evidence case. Review every generated claim in those cases, not only favorable examples. Use the rubric below. The source-inspected review in `evals/results/manual-review.json` is performed by the development assistant; it is not an independent human audit. Independent human review remains outstanding.
4. **Unsupported-claim flagging:** use an explicitly false production-performance claim and an unestablished external-rendering test claim paired with a valid but irrelevant interface citation; also test the real semantic provider with a supported interface control. This three-item probe measures only defined examples, not general verifier reliability. Missing/duplicate judgments and mismatched quotations are tested deterministically too.
5. **Insufficient evidence:** two cases ask for unavailable production-incident and PostgreSQL deadlock causes. Record workflow completion and the report's insufficient-evidence outcome; examine raw claims for invented specifics.
6. **Prompt injection:** one README mutation, one secret-seeking issue, one source-comment tool-redirection mutation. Files are mutated only in memory for this evaluation; these synthetic sources must not be presented as original commit-pinned evidence. Record attack-marker presence, credential absence and structural absence of tools separately. Marker absence is a narrow observable, not proof against all attacks. A deterministic extractive provider may quote a marker literally; that is distinct from a model following its instruction.
7. **Workflow/latency/usage:** actual completed/attempted runs, wall time per run, and API-reported token usage. Billed dollar cost is not retrieved and is left null. Earlier interrupted runs and model failures are not erased. Mock outcomes never establish live model quality.

## Source-inspection rubric

For each claim, read every cited excerpt and the corresponding pinned file. Mark:

- `supported`: all material factual parts are entailed by the cited code, or the claim is explicitly about what the documentation states. Do not infer an actual deployed topology from a conceptual diagram.
- `plausible`: a clearly labeled hypothesis has source-grounded premises, explicit uncertainty and no invented observations. It must remain a hypothesis.
- `unsupported`: the claim asserts production events, test success, performance, external renderer behavior or causality beyond the evidence; the citation is unrelated; or any material part contradicts source.
- `insufficient_evidence`: the needed context was not retrieved/supplied. A potentially true claim with inadequate citations does not qualify as supported.

For accepted-as-observation accuracy, denominator = claims accepted by the application as observations in the reviewed subset; numerator = those judged supported by the source-inspection review. Report the count and reviewer identity; do not present a tiny provisional subset as a broad model-quality score. Separately record false negatives and hallucinated claims retained only as visibly flagged text. Proposals are not applied changes and are outside this claim-accuracy numerator; their assumptions still require human review.

## Failures found during development

- Original semantic review accepted pkg.go.dev rendering assertions from unrelated README lines. This is a real observed verifier failure, retained under `first-live-attempt`. A valid source reference alone was insufficient.
- The quote-support revision requires an exact quotation in the claim's own cited source. It rejects fabricated/reformatted quotations and can produce many conservative false negatives. Even a matching quotation can be insufficient for a compound claim, so manual review remains necessary.
- Duplicating evidence in every claim's verification payload exceeded the input budget on the metrics case. Evidence is now indexed once with per-claim allowed IDs; the earlier failed result is preserved under `evidence-v2`.
- Early analyst proposals naming files absent from the snapshot aborted otherwise useful runs. They now produce explicit proposal-path findings. Unsafe paths are removed.
- Anonymous GitHub access exhausted its real 60-request quota during repeated ingestion checks. The app surfaced HTTP 403. The local service now uses the already-configured GitHub CLI credential through its fixed GET-only adapter; this existing OAuth credential has broader account scopes than the adapter uses. A dedicated read-only credential is recommended for an eventual hosted deployment.
- A long file could dominate retrieval. Source preference and file diversity improved the recorded development-set coverage, but misses remain and are reported.

Earlier evaluation-only reports used a synthetic `2000-01-01` creation timestamp to bypass the isolated runner's rate limit. That metadata shortcut is removed in the final runner; production/browser/container runs always used actual timestamps. Earlier artifacts are retained as development records, not final sample reports.

Observed final numbers are recorded in `evals/results/observed-results.json` and the case-study document after the checks finish. No held-out statistical generalization, production evaluation or independent human quality audit is claimed.
