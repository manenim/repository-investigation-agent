# Truthful portfolio description

## CV bullets

- Built an independent FastAPI repository-investigation tool with commit-pinned GitHub ingestion, bounded lexical retrieval, typed LLM workflow stages, SQLite persistence, and Markdown/JSON evidence reports.
- Implemented citation integrity checks and a separate claim-support review with exact-source quotation gates; tested validation, provider failures, prompt-injection boundaries, report exports, and worker restart behavior, and published a saved-report portfolio viewer.

## Short interview explanation

“This is an independent project I built to explore trustworthy internal AI tooling. It takes one public Go repository and an issue, resolves a commit, selects bounded source context, and produces architecture notes and an investigation report. Every claim has inspectable evidence and a separate verification outcome. An early live test showed why citation checks alone are inadequate: the verifier accepted an external rendering claim that the source did not prove. I added quotation checks and retained the failure in the evaluation record. The backend runs locally with a bounded worker and persistent SQLite volume; the public deployment is explicitly a saved-report viewer. I would next complete persistent remote hosting and obtain an independent human review of model quality before expanding repository or user scope.”

Do not describe this as employer production use, multi-agent orchestration, large adoption, or a measured application-performance improvement.
