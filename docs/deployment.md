# Deployment status and remaining host input

Public saved-report viewer: https://repository-investigation-agent.vercel.app

Vercel project: `repository-investigation-agent`, in the existing `manenims-projects` team. It serves static HTML/CSS/JS and a saved live-model report. Generation is disabled in the viewer. Its exports do not require a model request. No secrets, local environment files, live investigation database or private repository data are included. Source packaging is reproducible with `python -m scripts.build_sample_site`.

**The FastAPI backend is not publicly deployed.** The connected Vercel account supports static deployment. Current Vercel Daemons support long-running processes but explicitly lack persistent storage; ordinary Functions also do not make an in-process queue/SQLite filesystem durable. A Vercel-specific version needs a persistent managed database plus queue/workflow integration, which is additional implementation and account provisioning rather than a valid drop-in deploy of this app. No hosted-durability claim is made.

No configured VPS SSH target, Render credentials or Railway credentials were found. A persistent container host was requested from the user. No paid plan, disk, service, database or new recurring subscription was purchased. Render's current disk instructions require a paid service, so its free ephemeral filesystem is not a suitable SQLite deployment.

## Exact full-service deployment path on an existing host

1. Copy the source to an existing Linux host with Docker Compose and an HTTPS reverse proxy. Do not copy your developer `.venv`, `work`, evaluation database, `.git` authentication or unrelated credentials.
2. Create `.env` from `.env.example`. Configure `OPENAI_API_KEY`, `OPENAI_MODEL`, a new random `ACCESS_TOKEN`, `SOURCE_MODE=github`, `PROVIDER=openai`, and desired daily limits. Use `chmod 600 .env`. The current development API key expires 10 November; use a suitably managed deployment credential for ongoing hosting.
3. Run `docker compose up --build -d`. Compose provisions the local persistent `reports` named volume and starts exactly one process. It binds `127.0.0.1:8000` and disables filesystem writes except `/data` and `/tmp`.
4. Route the HTTPS hostname through the host's existing proxy to `127.0.0.1:8000`. Keep the API token server-side except for deliberate entry into the user's own browser; do not put it in query strings or public JavaScript.
5. Check `/health` and `/ready` over HTTPS. Readiness verifies database access and worker liveness, not paid-provider quota.
6. Submit the supported repository and issue #1 through the UI. Observe each stage. Save the run ID and download both exports; check their pinned SHA and evidence quotations.
7. Restart with `docker compose restart trace`. Confirm the same completed run is retrievable with authentication, its exports match, and `/ready` returns 200. Start a run and restart during execution to confirm it is explicitly failed rather than replayed.
8. Back up the database through SQLite's online backup API. Do not run `docker compose down -v` unless deliberately deleting reports. Monitor disk space, rate-limit refusals, failed runs and token usage.

To enable me to complete this remotely, provide the existing host's connection/deployment configuration or connect a persistent hosting account. A new paid resource requires a separate spending decision.

Official platform evidence checked 3 November 2026: [Vercel Daemons FAQ](https://vercel.com/docs/daemons#what-does-the-daemons-beta-support), [Render persistent disks](https://render.com/docs/disks), [Vercel deployment REST API](https://vercel.com/docs/rest-api/deployments/create-a-new-deployment).
