"""Create a clearly fictional, isolated showcase database for presentations."""
from __future__ import annotations

import json
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE_DIR = ROOT / "data" / "showcase"
os.environ["CODEBASE_DOCTOR_DATA"] = str(SHOWCASE_DIR)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import server  # noqa: E402  (sets up the isolated schema after env is set)

rng = random.Random(42)
now = datetime.now(timezone.utc)

repos = [
    ("acme-labs", "commerce-api", "Python", "FastAPI", "payments, checkout, orders"),
    ("northstar-demo", "identity-service", "Python", "Django", "authentication, sessions, JWT"),
    ("atlasworks-demo", "dispatch-engine", "Python", "Flask", "routing, scheduling, workers"),
    ("cinder-labs-demo", "feature-flags", "TypeScript", "Node.js", "flags, targeting, cache"),
    ("lumen-demo", "analytics-worker", "Python", "Celery", "events, aggregation, exports"),
    ("harbor-cloud-demo", "inventory-service", "Python", "FastAPI", "stock, reservations, webhooks"),
    ("papertrail-demo", "notification-hub", "TypeScript", "Express", "email, templates, retries"),
    ("verdant-demo", "checkout-core", "Python", "Django", "cart, tax, shipping"),
    ("monorail-demo", "search-indexer", "Python", "Flask", "indexing, queries, ranking"),
    ("bluejay-demo", "tenant-gateway", "Python", "FastAPI", "tenancy, authorization, routing"),
    ("relayworks-demo", "webhook-relay", "Python", "FastAPI", "signatures, retries, delivery"),
    ("orbit-demo", "document-parser", "Python", "Python", "uploads, parsing, extraction"),
]

# Every finding is fictional and tied to a deliberately fictional repository name.
issue_catalog = [
    ("security", "critical", "auth.jwt-algorithm", "JWT algorithm is not explicitly pinned", "Token verification accepts an algorithm from the token header; pin the expected signing algorithm.", "app/auth/tokens.py", 84, "claims = jwt.decode(token, key, options={\"verify_signature\": True})"),
    ("security", "high", "python.subprocess-shell", "Shell enabled in subprocess", "User-controlled export format reaches a shell command. Prefer a fixed executable and argument list.", "app/exports/runner.py", 126, "subprocess.Popen(command, shell=True, cwd=export_dir)"),
    ("security", "high", "web.sql-interpolation", "SQL query uses string interpolation", "A request parameter is interpolated into a query. Use parameterized SQL.", "app/repositories/orders.py", 211, "query = f\"SELECT * FROM orders WHERE id = {order_id}\""),
    ("security", "high", "secrets.debug-key", "Development signing key fallback is active", "A hard-coded fallback key can make deployed tokens forgeable if configuration is missing.", "app/settings/security.py", 37, "SECRET_KEY = os.getenv(\"APP_SECRET\", \"dev-secret-change-me\")"),
    ("bug", "high", "async.blocking-io", "Blocking network call inside async handler", "This synchronous call blocks the event loop and can stall concurrent requests.", "app/api/webhooks.py", 92, "response = requests.post(target_url, json=payload, timeout=30)"),
    ("bug", "medium", "python.mutable-default", "Mutable default argument is shared across calls", "The default list persists between calls. Use None and initialize inside the function.", "app/services/labels.py", 58, "def normalize_labels(labels=[]):"),
    ("bug", "medium", "python.broad-exception", "Broad exception hides processing failures", "Catching Exception can conceal unrelated defects. Catch the expected error and preserve context.", "app/workers/reconcile.py", 173, "except Exception: return None"),
    ("quality", "medium", "python.resource-leak", "File handle may not close on error", "Use a context manager to ensure the temporary file closes on every execution path.", "app/storage/local.py", 65, "handle = open(cache_path, \"wb\")"),
    ("performance", "medium", "orm.n-plus-one", "Potential N+1 query in list endpoint", "The loop accesses a related field for each record. Consider eager loading the relation.", "app/api/customers.py", 144, "for order in orders: result.append(order.customer.display_name)"),
    ("dependency", "medium", "dependency.outdated", "Dependency is behind the supported release line", "Review the package changelog and update with a lockfile change after running the test suite.", "requirements.txt", 18, "urllib3==1.26.14"),
    ("testing", "low", "tests.missing-edge-case", "No regression test covers empty input", "Add a boundary case for an empty collection to protect this code path.", "tests/test_search.py", 1, "# Search tests cover typical terms; empty query is not covered."),
    ("quality", "low", "python.todo", "Unresolved TODO in request path", "Confirm whether this behavior is still required and either implement or remove the placeholder.", "app/services/checkout.py", 203, "# TODO: handle duplicate provider callbacks"),
]

with server.db() as conn:
    # This script only ever resets data/showcase/codebase_doctor.sqlite3.
    conn.execute("DELETE FROM audit_events")
    conn.execute("DELETE FROM findings")
    conn.execute("DELETE FROM scans")
    conn.execute("DELETE FROM repositories")
    repo_ids = []
    for owner, name, language, framework, topics in repos:
        repo_id = str(uuid.uuid4())
        full_name = f"{owner}/{name}"
        conn.execute("INSERT INTO repositories VALUES (?, ?, ?, ?, ?, ?)",
                     (repo_id, name, full_name, f"https://github.com/{full_name}", "main", (now-timedelta(days=rng.randint(20,120))).isoformat()))
        repo_ids.append((repo_id, full_name, language, framework, topics))

    # Three believable scan runs per repo: 36 total. All names, results and SHAs are fictional.
    scan_rows = []
    findings_added = 0
    for idx, (repo_id, full_name, language, framework, topics) in enumerate(repo_ids):
        repo_slug = full_name.rsplit("/", 1)[-1].replace("-", "_")
        for run_no in range(3):
            scan_id = str(uuid.uuid4())
            age_hours = (2 + idx * 5) if run_no == 0 else (72 + idx * 11 + run_no * 220)
            started = now - timedelta(hours=age_hours)
            state = "failed" if (idx in (3, 8) and run_no == 1) else "completed"
            finish = started + timedelta(minutes=rng.randint(1, 8))
            sha = uuid.uuid5(uuid.NAMESPACE_DNS, f"showcase:{full_name}:{run_no}").hex[:40]
            # 3-7 issues in each latest scan, enough to make the issues page feel populated.
            nfindings = rng.randint(3, 7) if run_no == 0 else (rng.randint(1, 3) if state == "completed" else 0)
            summary = {"files_scanned": rng.randint(124, 1450), "findings": nfindings,
                       "source": "showcase-fixture", "language": language, "framework": framework,
                       "topics": topics, "sample_data": True}
            conn.execute("INSERT INTO scans (id, repository_id, state, commit_sha, started_at, finished_at, error, summary_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (scan_id, repo_id, state, sha, started.isoformat(), finish.isoformat() if state in ("completed", "failed") else None,
                          "Sample rate-limit event; no real scan was run." if state == "failed" else None, json.dumps(summary)))
            scan_rows.append((scan_id, repo_id, full_name, state, started, finish, summary, run_no))
            if state == "completed":
                # The latest scan is more detailed. Older scans show a smaller historical issue set.
                selected = rng.sample(issue_catalog, min(nfindings, len(issue_catalog)))
                for category, severity, rule, title, description, path, line, evidence in selected:
                    # Vary file paths and line numbers while retaining plausible code context.
                    path = path.replace("app/", f"app/{repo_slug}/", 1) if path.startswith("app/") else path
                    line = max(1, line + rng.randint(-22, 43))
                    fingerprint = f"{rule}:{path}:{line}"
                    conn.execute("INSERT INTO findings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                 (str(uuid.uuid4()), scan_id, category, severity, rule, title, description, path, line, evidence, fingerprint))
                    findings_added += 1

    # Action history, explicitly annotated as showcase fixtures.
    for repo_id, full_name, language, framework, topics in repo_ids:
        conn.execute("INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?)",
                     (str(uuid.uuid4()), repo_id, None, "repository.added", f"SHOWCASE SAMPLE · {full_name} connected for presentation.", (now-timedelta(days=rng.randint(15,100))).isoformat()))
    for scan_id, repo_id, full_name, state, started, finished, summary, run_no in scan_rows:
        conn.execute("INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?)",
                     (str(uuid.uuid4()), repo_id, scan_id, "scan.queued", "SHOWCASE SAMPLE · A sample scan was queued; no external repository was contacted.", (started-timedelta(seconds=11)).isoformat()))
        conn.execute("INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?)",
                     (str(uuid.uuid4()), repo_id, scan_id, "scan.started", f"SHOWCASE SAMPLE · Analysis fixture for {full_name}.", started.isoformat()))
        action = "scan.completed" if state == "completed" else "scan.failed"
        detail = f"SHOWCASE SAMPLE · {summary['files_scanned']} files · {summary['findings']} sample findings · {framework}."
        conn.execute("INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?)",
                     (str(uuid.uuid4()), repo_id, scan_id, action, detail, (finished or started).isoformat()))

print(f"Created isolated showcase database: {server.DB_PATH}")
print(f"Sample repositories: {len(repos)} · scan runs: {len(scan_rows)} · findings: {findings_added} · audit events: {len(repos) + len(scan_rows)*3}")
print("All sample data is fictional; no remote repository was accessed.")
