# Hosted deployment and verification status

- Live service: https://repository-investigation-agent.onrender.com
- Saved actual-model report viewer: https://repository-investigation-agent.vercel.app
- Source: https://github.com/manenim/repository-investigation-agent
- Render web service: `srv-dbl03ut9fdbs73cgnpj0`, Docker, Free ($0/month), Oregon.
- Render database: `dpg-dbkvtcm1egvs7396f1g0-a`, PostgreSQL 18, Free ($0/month), Oregon, 1 GB, autoscaling disabled.
- **Database expires 3 December 2026. Current model key expires 10 November 2026.** The app displays these dates. No paid resource, upgrade, subscription or card purchase was made.

## Established results

The service built and started at commit `03288fc3193be7a02efca971ea1876c7a68ee423`. Public health and readiness returned HTTP 200; authenticated POST created a queued investigation and the worker persisted its explicit failure. Unauthenticated report access returned 401. Render's internal Postgres connection works; local direct external connections were intermittent.

[Hosted CI passed](https://github.com/manenim/repository-investigation-agent/actions/runs/41667367525) for that commit. Local checks currently cover 44 automated cases. Separate integration exercised a real local PostgreSQL 16 server, including API→report, exports, app restart, interrupted-run recovery and admission control; it used the deterministic provider and does not establish live model quality.

Local real-provider and real-GitHub runs generated complete reports and both exports. A local Docker restart preserved a completed report byte-for-byte and marked a deliberately interrupted run failed. See `evals/results/container-restart.json` and the actual report artifacts.

## Exact remaining blocker

**The hosted real-GitHub investigation returned HTTP 403 before generation.** Anonymous GitHub access is unavailable from the deployment. A dedicated credential restricted to reading `manenim/gateway-rate-limiter` is required. GitHub's token creation page requires owner reauthentication (security key, GitHub Mobile, authenticator app or password). The confirmation page was left open for the owner.

The local GitHub CLI credential has broader scopes than the app uses and was **not** uploaded to Render. No private-repository credential was silently shared with the hosting service. Render currently has the restricted OpenAI key, the demo access token, internal database URL, provider/source settings and a five-run daily limit.

The service is deployed, but a full successful hosted generation/export/restart flow is **not yet verified**. The saved-report viewer is a separately labeled useful portfolio path; it is not a mock passed off as live generation.

## Finish the hosted check

1. Complete GitHub's owner authentication, then create a fine-grained token limited to the supported public repository with Contents read, Issues read and Metadata read permissions. Use a short expiration and no write permissions. The public repository and issue are the only target resources the application can access.
2. Save it as `GITHUB_TOKEN` in the ignored local `.env.render-service` file and in the existing Render service's environment. Do not put it in GitHub source, logs, query strings or public JavaScript. Save/redeploy the existing free service; do not create another service.
3. Check `/health` and `/ready` over HTTPS. Enter the demo access token from the ignored local `.env` in the UI. Submit `manenim/gateway-rate-limiter`, `main`, and issue `https://github.com/manenim/gateway-rate-limiter/issues/1`.
4. Watch every stage, inspect flagged claims and source quotations, and download Markdown and JSON. Record the run ID and export hashes under `evals/results` without credentials.
5. In Render's Manual Deploy menu, select Restart service. After readiness returns 200, retrieve the same completed run with authentication and compare exports byte-for-byte. Also interrupt a separate test run and confirm explicit failure without paid-call replay.
6. Update this status, README, case study and deployment evidence only after those checks pass. Do not interpret a successful build as a completed end-to-end deployment.

## Storage and usage decisions

Render Free web files disappear on restart/spindown, so the application uses managed Postgres there and refuses an ephemeral SQLite fallback. SQLite remains the reproducible local-volume option. Only one app process/replica is supported; this is not a durable/distributed worker.

Free web instances sleep after 15 minutes without incoming traffic and may take about a minute to wake. User polling keeps an active investigation observable, but Render may restart a service at any time; interrupted runs fail explicitly. The free database expires after 30 days and has no managed backups. Export reports before 3 December or deliberately migrate to an appropriate host. No automatic paid upgrade is configured by this project.

The saved-report Vercel viewer is static and contains no credentials or paid-generation endpoint. Its files are reproducible with `python -m scripts.build_sample_site`.

## Reproduce on an existing persistent Docker host

Create `.env` from `.env.example`, configure a model key and random access token, and run `docker compose up --build -d`. The named `reports` volume persists SQLite; the app binds localhost:8000. Put it behind the host's existing HTTPS proxy. Use exactly one process/replica. Back up via SQLite's online backup API and do not delete the volume on upgrades. A Postgres host may instead configure `DATABASE_URL`.

Official platform evidence: [Render Free limits](https://render.com/docs/free), [Render persistent disks](https://render.com/docs/disks), [Vercel Daemons storage limits](https://vercel.com/docs/daemons#what-does-the-daemons-beta-support).
