# Codebase Doctor — Implementation Plan

## 1. Purpose and delivery target

Build a semester MVP that accepts a GitHub repository, analyzes a deliberately limited Python codebase, presents evidence-backed findings, and can propose a small repair in an isolated workspace. The repair must be validated before it can be offered for human approval. The product must never merge to a production branch automatically.

**Target team and schedule assumed:** 3–4 students over 12 weeks. If the team or semester length differs, preserve the phase order and trim optional work first.

**Storage decision for the current build:** keep data on the user's machine in SQLite; do not use Supabase. The local app is single-user and binds to loopback. Add hosted storage and authentication only when deployment or multi-user use is requested.

## 2. MVP success criteria

The MVP is complete when a user can:

1. Sign in and connect a GitHub repository using least-privilege access (or select a public repository for the first demo).
2. Start a scan and see progress and a final report for a bounded Python repository.
3. Review findings with category, severity, confidence, evidence, file/line references, and scanner or agent provenance.
4. Request a proposed fix for a supported finding and inspect its diff.
5. Run the patch in an isolated, resource-limited environment; see test and scan results.
6. Approve or reject a validated patch. Approval creates a draft pull request or downloadable patch; it does not merge.
7. See an audit trail for scans, agent decisions, patch attempts, validation results, and approvals.

**Quality bar for the demo:** seeded test repositories produce repeatable static findings; unsafe or failed patches cannot be marked verified; every displayed AI conclusion links to evidence; a failed validation leaves the source repository unchanged.

## 3. Scope boundaries

### Build for MVP

- Python repository support; bounded repository size and file count.
- GitHub public repository ingestion first; private repositories only after OAuth/token handling and access controls are reviewed.
- Deterministic tools: Semgrep and Bandit, plus Python dependency-file parsing and one dependency audit tool if setup is reliable.
- AST-aware symbol chunking for Python, with lexical fallback for parse failures.
- Four core roles: Coordinator, Bug/Security analysis (may be one combined LLM investigation service in v1), Fix Planner, Verification. Add Critic only after the secure end-to-end path works.
- One configured LLM provider behind a small provider interface, structured JSON outputs, bounded retries and timeouts.
- Isolated per-run workspace/container, read-only source mount where practical, no host Docker socket, network disabled during tests by default, CPU/memory/time limits.
- Dashboard: repositories, scan status, findings, finding detail, patch diff, validation, approval/rejection, audit log.

### Defer

- Autonomous merge, writes to the default branch, arbitrary shell/tool access for agents.
- Multiple programming languages, enterprise monorepos, custom-trained models.
- Long-term cross-repository memory, elaborate confidence calibration, real-time agent graph visualization.
- Full CI/CD integrations, performance optimization agent, broad benchmark study, production multi-tenant scale.

## 4. Recommended initial architecture

Use a modular monolith for the semester rather than several independently deployed services. Keep analysis and execution behind explicit interfaces so components can later be split out.

```text
Next.js UI
   │ REST + polling initially
Local API ── SQLite (repos, scans, findings, patches, approvals, audit)
   │          local background jobs (scan/patch jobs)
   ├── GitHub adapter
   ├── Analysis pipeline (file inventory → AST chunks → Semgrep/Bandit → LLM)
   ├── Orchestrator (persisted run state, bounded transitions)
   └── Sandbox runner (isolated job workspace/container)
                         │
                 artifacts/results
```

Do not introduce Qdrant initially. For a bounded Python repository, persist AST chunks and use lexical/symbol search plus the findings' file and import neighborhood as context. Add embeddings only if a measured retrieval failure justifies the operational cost. This keeps the first version testable and reduces infrastructure work.

### Suggested stack

- Frontend: Next.js, TypeScript, Tailwind; a diff viewer can start with a lightweight diff component before Monaco.
- Backend: local Python API; the first implementation uses the standard library to avoid an external package install requirement.
- Persistence: SQLite on local disk; use migrations when the schema grows. Do not add Supabase for the current phase.
- Jobs: bounded local background jobs for the first vertical slice; move to a durable worker queue only when concurrency or restart recovery requires it.
- Execution: Docker or an equivalent isolated runner managed by the backend host; resource and network controls are required.
- Repository access: GitHub App installation flow for the target deployment, or public clone-only mode for the first milestone.
- Tooling: Semgrep, Bandit, pytest, and a Python dependency audit tool selected during week 2.
- Deployment: one development/staging environment using Docker Compose; secrets supplied through environment/secret storage, never committed.

## 5. Core workflow and state model

Represent scans and repair attempts as persisted state machines, not as a single long API request.

### Scan states

`queued → ingesting → analyzing → completed | failed | cancelled`

### Repair states

`requested → planning → awaiting_approval (if required) → applying → validating → ready_for_review → approved | rejected | failed | rolled_back`

Every transition records actor, timestamp, input/output references, and reason. Enforce allowed transitions in backend code and database constraints where practical. Retry only idempotent steps, with an attempt limit. Store large logs and diffs as artifacts; store references and metadata in SQLite for the local phase.

### Risk policy for MVP

- All patches are confined to a temporary branch/workspace.
- Any patch modifying authentication, cryptography, permissions, CI, dependency lockfiles, or more than a small configured file/line threshold is high risk and cannot be automatically applied without explicit approval.
- Even low-risk patches require validation and a user action before PR creation.
- No automatic merge path exists.

## 6. Data model (minimum useful schema)

- `users`: identity and auth provider subject.
- `repositories`: owner/name, provider ID, default branch, installation reference, scan settings.
- `scans`: repository, commit SHA, state, timestamps, tool versions, summary.
- `files` or `code_chunks`: scan, path, language, symbol, start/end lines, content hash, bounded source text or artifact reference.
- `findings`: scan, stable fingerprint, category, severity, confidence, title, description, evidence, path/line range, source, status.
- `agent_runs`: scan/repair, role, model/tool versions, state, token/cost metadata if available, structured result reference.
- `patches`: finding, base SHA, patch artifact, changed paths, risk, state.
- `validation_runs`: patch, command/tool, exit state, logs/artifact references, test summary.
- `approvals`: patch, user, decision, timestamp, note.
- `audit_events`: actor, action, entity, timestamp, sanitized metadata.

Use foreign keys, created/updated timestamps, and repository ownership checks on every API read/write. Avoid storing secrets in these tables. Define retention and deletion behavior for repository source and generated artifacts before connecting private repositories.

## 7. 12-week delivery roadmap

| Week | Outcome | Concrete work and exit check |
|---|---|---|
| 1 | Product and threat model agreed | Choose Python, repository size limits, public-only vs GitHub App path, local-only access boundary, risk policy, and evaluation fixtures. Create wireframes and architecture decisions. Exit: written scope and threat boundaries accepted by team. |
| 2 | Running skeleton | Repo structure, lint/format config, local API health route, web shell, SQLite schema, CI build. Exit: one-command local startup and basic CI. |
| 3 | Repository records | Local repository CRUD, GitHub/public-repository adapter, input validation, and job record model. Defer user authentication while the service remains loopback-only. Exit: user can register a repository and retrieve metadata safely. |
| 4 | Ingestion and scan jobs | Clone/download at pinned commit, file allow/deny rules, size limits, secret-safe logs, worker and progress polling. Exit: bounded repo scan job completes or reports clear failure. |
| 5 | Deterministic analysis | AST inventory/chunking, Semgrep/Bandit invocation, normalized finding schema, fingerprints, tool version capture. Exit: seeded vulnerable/clean fixtures produce expected normalized results. |
| 6 | Findings experience | Dashboard, scan history/progress, finding filters/detail, source evidence with line references, audit events. Exit: user can understand and navigate scan output without reading raw logs. |
| 7 | AI investigation and planning | LLM provider adapter, structured outputs, retrieved context and tool findings as evidence, bounded prompts/retries, confidence caveats. Exit: AI explanation/plan attaches to a finding and cites repository evidence. |
| 8 | Patch proposal and diff | Generate unified diff, validate paths and patch syntax, calculate changed-file/line risk, persist immutable patch artifact. Exit: user can inspect a proposed patch; it has not changed the source checkout. |
| 9 | Isolated verification | Sandbox runner, resource controls, pytest and scanners, capture logs/results, reject invalid/out-of-scope patch. Exit: seeded failing patch is rejected; passing patch is marked ready for review. |
| 10 | Approval and delivery | Approval/rejection UI, audit trail, create draft PR or downloadable patch; idempotency and rollback/cleanup behavior. Exit: no path merges automatically; rejection and failure clean up the workspace. |
| 11 | Hardening and evaluation | Authorization review, prompt-injection cases, malicious repo fixtures, time/resource limits, failure handling, baseline measurements. Exit: threat checklist and evaluation results recorded. |
| 12 | Demo and handoff | Fix critical defects, prepare reproducible demo, architecture/setup docs, limitations, final report and presentation. Exit: fresh setup can reproduce the end-to-end demo from documentation. |

**Critical path:** repository ingest → deterministic scan → findings UI → isolated patch validation → approval. AI/RAG depth is secondary to completing this safely.

## 8. Work allocation for a 4-person team

For a 3-person team, combine frontend with product/evaluation and combine orchestration with repository analysis; keep sandbox ownership explicit.

1. **Frontend/product:** screens, user flows, API integration, demo usability.
2. **Backend/data:** API, auth, schema, migrations, audit, job lifecycle.
3. **Analysis/AI:** ingestion, AST chunking, scanners, prompts, structured results.
4. **Execution/quality:** sandbox, patch validation, test fixtures, security review, integration and evaluation.

All team members review safety-sensitive changes. Assign one integration owner to maintain API contracts and weekly end-to-end demos. Keep tasks small enough to complete within a week.

## 9. Initial repository layout

```text
apps/
  web/                    # Next.js UI
  api/                    # FastAPI application
    app/api/               # routes and request models
    app/core/              # config, auth, permissions
    app/db/                # models, migrations, repositories
    app/jobs/              # worker tasks and state transitions
    app/integrations/      # GitHub and scanner adapters
    app/analysis/          # inventory, AST, findings, retrieval
    app/agents/            # coordinator and structured agent roles
    app/sandbox/           # patch and validation runner interface
packages/
  contracts/              # shared API schemas/OpenAPI client generation
fixtures/
  vulnerable-python/       # intentionally seeded, non-production examples
  clean-python/
docs/                      # architecture decisions, threat model, demo guide
infra/                     # local Compose and deployment manifests
```

Keep scanner and model calls behind interfaces; persist their version/configuration with each run so results can be explained and reproduced.

## 10. API surface to implement first

- `POST /repositories` — register repository.
- `GET /repositories` and `GET /repositories/{id}` — list/detail with ownership enforcement.
- `POST /repositories/{id}/scans` — enqueue scan at a pinned commit.
- `GET /scans/{id}` — state/progress/summary.
- `GET /scans/{id}/findings` and `GET /findings/{id}` — findings and evidence.
- `POST /findings/{id}/repair-attempts` — create a proposed repair job.
- `GET /repair-attempts/{id}` — plan, patch, validation state and artifact references.
- `POST /repair-attempts/{id}/decision` — approve/reject with explicit allowed state.
- `GET /repositories/{id}/audit-events` — paginated audit history.

Return job IDs quickly; use polling for the MVP. Add webhooks or server-sent events only if polling is inadequate for the demo.

## 11. Security and reliability requirements

- Treat repository files, issue text, README instructions, and scanner output as untrusted data, never as system instructions.
- Never expose provider secrets to the LLM or sandbox. Use short-lived, least-privilege GitHub credentials.
- Validate repository URL/owner and pin the analyzed commit. Defend against path traversal, symlinks, archive bombs, oversized files, submodules, and malicious build hooks.
- Do not execute repository code during ingestion. During tests, run as non-root with CPU, memory, process, disk, and time limits; disable network by default; do not mount credentials or host sockets.
- Apply a patch only after validating paths and diff scope. Ensure the patch cannot modify files outside the workspace.
- Redact tokens and sensitive environment values from logs and model context. Do not log full source by default.
- Authorize every repository, scan, finding, patch, and audit query against the current user.
- Make job transitions idempotent; clean temporary workspaces after completion/failure; retain only artifacts required for review.
- Fail closed: if validation is incomplete, timed out, or unavailable, the patch is not verified.

## 12. Evaluation plan

Create a small fixed test set of 10–20 public or synthetic Python repositories with known issues and clean controls. Record exact commits and expected findings. Include seeded cases for a bug, unsafe input handling, vulnerable dependency metadata, no-finding control, parse failure, malformed model output, patch path escape, timeout, and test regression.

Measure at minimum:

- Scanner precision/recall on labeled cases (report fixture limitations).
- Finding explanation evidence validity: referenced path/line exists at scanned commit.
- Proposed patch application rate and test pass rate.
- Regression rate on accepted/ready-for-review patches.
- Unsafe patch rejection rate on malicious/out-of-scope fixtures.
- Scan and repair completion time; failures and retries.
- Human approval/rejection counts and model/tool cost where observable.

Compare deterministic scan alone with deterministic scan plus AI explanation/planning. Add multi-agent vs single-agent comparisons only if the MVP reaches stable end-to-end operation; avoid claiming statistical significance from a tiny fixture set.

## 13. Key risks and mitigation

| Risk | Mitigation |
|---|---|
| Scope grows beyond semester | Gate features by the roadmap; defer vector DB, multi-language, and merge automation. |
| Model returns fabricated findings or invalid patches | Require evidence, schema validation, diff validation, deterministic checks, and sandbox tests; display provenance and uncertainty. |
| Repository prompt injection | Keep repository text explicitly untrusted; agent tools are allowlisted and narrow; no secrets in context. |
| Sandbox escape or resource abuse | Use isolated runner, non-root, no network by default, strict quotas, cleanup; never run arbitrary builds in the API process. |
| GitHub credential exposure | Prefer GitHub App and installation-scoped tokens; redact logs; separate credentials from jobs. |
| Tests are weak or generated tests encode the bug | Use existing tests and seeded regression fixtures first; label generated tests; do not count a generated test alone as proof. |
| Integration delays | Freeze API contracts early, integrate weekly, maintain a working vertical slice, and pin tool/model versions. |
| Inconsistent results | Pin commit and tool versions; persist prompts/config hashes and run metadata; deterministic tools remain the baseline. |

## 14. Decisions to make in week 1

Record these in short Architecture Decision Records (ADRs):

1. Python as the only MVP language (recommended).
2. Public clone-only for the first working slice versus GitHub App support in MVP (recommended: public first, App before final demo if time allows).
3. Authentication provider and hosting target.
4. Worker library and dependency audit tool.
5. Whether the final demo outputs a downloadable patch or opens a draft PR (downloadable patch is the lower-risk first target).
6. Repository size/file limits, allowed dependency/build commands, retention period, and risk thresholds.

## 15. First two weeks: concrete checklist

### Week 1

- Write a one-page user story and MVP boundary.
- Select two demo repositories and create small vulnerable/clean fixtures.
- Draw the data flow and threat boundaries.
- Sketch the 5 MVP screens: repositories, scan status, findings, finding detail/diff, audit.
- Define scan/repair state enums and API contract draft.
- Create ADRs for the week-1 decisions above.

### Week 2

- Scaffold web, API, database migration, and worker packages.
- Add formatting, linting, type checks, and CI build.
- Start API/UI/worker locally with one documented command.
- Add `health`, repository registration, and queued-job persistence.
- Demonstrate one queued job moving to completed with progress visible in the UI.

**First vertical-slice milestone:** by the end of week 4, a user can register a public repository, enqueue a scan at a pinned commit, and see a completed scan record—even if analysis is initially a stub. This validates integration before AI work begins.

## 16. Definition of done for each feature

- User-visible behavior is reachable through the UI or a documented API.
- Inputs and state transitions are validated; authorization is checked.
- Success and failure states are visible and recorded in audit events.
- Logs are sanitized; timeouts and retries are bounded.
- A small reproducible fixture or manual verification procedure is documented.
- Relevant setup and limitations are recorded in project documentation.

