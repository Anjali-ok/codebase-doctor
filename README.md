# Codebase Doctor

Local-first implementation of the Codebase Doctor project. Application records are stored in a SQLite database on this machine; no Supabase project is used.

## Start the application

Requires Python 3.10 or later. The API and static frontend use only Python's standard library, so no package installation is required.

```bash
python3 backend/server.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Data is stored at `data/codebase_doctor.sqlite3` and ignored by Git. Set `CODEBASE_DOCTOR_DATA` to move it elsewhere.

## Local credentials and GitHub OAuth

Copy `.env.example` to `.env`, then set the GitHub App Client Secret and a newly rotated OpenAI API key in `.env`. The server reads these values on startup and never writes them into source files. Do not commit `.env`.

In the GitHub App settings, set **Callback URL** to `http://localhost:8000/api/github/callback`. Keep webhooks inactive while running locally; GitHub cannot reach a localhost webhook, and webhook delivery is not needed for OAuth or manual scans. The OAuth flow validates a short-lived state value and stores the returned user token in `data/github-oauth.json` with owner-only file permissions. Use **Connect GitHub** in Repositories to authorize. Disconnect removes this local token file.

The OAuth callback setting must match `.env` exactly. To use another port, update both `GITHUB_CALLBACK_URL` and the GitHub App callback URL. For API-only development, an optional fine-grained GitHub token can be set in the process environment:

```bash
GITHUB_TOKEN=your_token_here python3 backend/server.py
```

Do not commit tokens or expose this development server to a public network. Public repositories may be scanned without a token, subject to GitHub's unauthenticated API rate limits. Private repository access requires a token with narrowly scoped read access. The application currently binds to `127.0.0.1` by default.

## Current implementation

- Local SQLite persistence for repositories, scan runs, findings, and audit events.
- GitHub repository registration and GitHub API-based source retrieval pinned to the commit used by the scan.
- Python AST starter rules for dynamic code execution, shell-enabled subprocess calls, and a limited SQL concatenation pattern. Repository code is parsed but never executed.
- Scan state and errors are persisted; the UI displays data returned by the API and does not include preloaded sample findings.
- GitHub App user authorization through a localhost OAuth callback, local token storage, and disconnect.
- Optional OpenAI Responses API review for a finding, with the response persisted in SQLite and shown in the finding detail panel. The model sees the finding and its evidence only; it is instructed to treat repository content as untrusted data.
- Patch generation, sandboxed test execution, automatic fixes, and pull-request creation are not implemented yet. The Test Center is an honest placeholder; these features require isolated workspaces and verification before they can be safely enabled.

## API

- `GET /api/health`
- `GET /api/github/status`, `GET /api/github/connect`, `GET /api/github/callback`, `POST /api/github/disconnect`
- `POST /api/findings/{id}/ai-review`
- `GET|POST /api/repositories`
- `GET|DELETE /api/repositories/{id}`
- `GET /api/repositories/{id}/audit`
- `POST /api/repositories/{id}/scans`
- `GET /api/scans` and `GET /api/scans/{id}`

The API is intended for local development and currently has no authentication. Keep it bound to localhost.

## Presentation showcase

Generate an isolated fictional dataset, then run a second server on port 8001:

```bash
python3 backend/seed_showcase.py
CODEBASE_DOCTOR_DATA="$PWD/data/showcase" CODEBASE_DOCTOR_SHOWCASE=1 CODEBASE_DOCTOR_PORT=8001 python3 backend/server.py
```

Open [http://127.0.0.1:8001](http://127.0.0.1:8001). The showcase has fictional repositories, scan histories, findings, and audit events; the header is marked `SHOWCASE · SAMPLE DATA`. Repository mutation and scan actions are disabled in this mode. Re-run the seed command to reset only the showcase database. The normal local database remains at `data/codebase_doctor.sqlite3`.
