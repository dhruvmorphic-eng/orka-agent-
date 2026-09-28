# Orka agent

Approval-first sales research for Cnvrted. This standalone repository is the first milestone of the agreed agent workflow:

**Understand → clarify → propose plan → approve → research → review sample → refine → shortlist → enrich → approve campaign → send.**

## What runs today

- A local browser workspace with saved tasks and conversation messages.
- Optional Claude-powered extraction of a research brief from natural-language requests.
- A no-key guided form that asks only for missing brief fields. This mode is deterministic, not an LLM demo.
- Editable, versioned search plans, scoped explicit approval, and a persisted pending job.
- SQLite transactions and optimistic revisions protect against stale approvals, concurrent edits, and duplicate approval clicks.
- Editing a plan revokes approval and supersedes its pending job.

**Search, scraping, enrichment, voice, email sending, and calendar booking are not connected in this milestone.** Approved tasks say `approved_waiting_integration`; nothing silently executes. `/search` returns 409 without matching approval and 501 with approval until an adapter exists. This is not yet the seven-day beta or an autonomous sales system.

## Run locally

Python 3.9+ (tested on 3.9; the optional CI template targets 3.11). No frontend build step required.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m uvicorn orka.app:create_app --factory --host 127.0.0.1 --port 8010 --no-proxy-headers
```

Open http://127.0.0.1:8010. Task data is saved in `data/orka.sqlite` and ignored by Git. Set `ORKA_DB` to select another database path. Refreshing the page restores the last selected task; restarting the server preserves all tasks and pending jobs.

This is a **single-operator localhost application**, not a hosted multi-tenant service. It rejects non-loopback callers and cross-origin writes. Do not expose it through a reverse proxy or bind it publicly. Add real authentication, tenant ownership checks, quotas and deployment hardening before remote use. No Cnvrted production APIs or databases are called.

## Enable AI clarification

Set `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` securely in the server environment, then restart. Choose an available model supporting tool use in your Anthropic account. `.env.example` documents the variables; `.env` files are not automatically loaded. Never paste keys into the UI or commit them.

Configured AI requests send the user's message and current brief to Anthropic and can incur provider charges. Search budgets cover future discovery/extraction only, not model planning or enrichment. Without both variables, AI chat is disabled and the guided form remains usable. Live model calls have not been validated with account credentials in this initial milestone; tests use a fake provider boundary.

The model can propose only a validated `Brief`. It cannot approve a task or execute tools. All structured fields remain editable and must be reviewed. Provider errors leave the saved plan unchanged. API contract: [Anthropic Messages](https://platform.claude.com/docs/en/api/messages/create).

## API

All writes require `X-Orka-Client: workspace`; browser writes must be same-origin. This is a local CSRF boundary, not user authentication.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/capabilities` | Honest provider/feature availability |
| POST / GET | `/api/tasks` | Create / list tasks |
| GET | `/api/tasks/{id}` | Reload task state |
| PUT | `/api/tasks/{id}/brief` | Save full brief with expected `revision` |
| POST | `/api/tasks/{id}/message` | Extract a revised brief with expected `revision` |
| POST | `/api/tasks/{id}/approve` | Approve expected `revision` and `plan_version` |
| GET | `/api/tasks/{id}/job` | Inspect current pending job |
| POST | `/api/tasks/{id}/search` | Guarded placeholder; no provider execution |

Approval transactionally stores an immutable plan snapshot in `jobs`. Never have a future worker read a mutable task brief instead of that snapshot. Before executing, a worker must re-check that approval is still current, atomically claim the job, enforce spend limits, and persist progress. The current repository deliberately has no worker.

## Test

```sh
python -m pytest -q
node --check orka/static/app.js
```

Tests cover approval bypass, stale versions, repeated approvals, concurrent revisions, persistence across app instances, invalid inputs, model failures, cross-origin writes, and the model's inability to approve work.

`docs/github-actions.example.yml` is an inactive CI template. The current GitHub OAuth connection cannot create workflow files. An authorized maintainer can enable it later at `.github/workflows/test.yml`; no hosted CI run is claimed for this initial push.

## Next milestones

1. Integrate authenticated Cnvrted research services behind a bounded, durable worker. Keep ICP-fit suggestions distinct from verified intent.
2. Return source URLs, evidence, publication/retrieval dates and separate fit/intent judgments. Add sample review and refinement.
3. Add selected-lead enrichment with its own scoped spend approval.
4. Prepare an exact recipient/message/schedule snapshot for campaign approval. Add send idempotency, suppression, reply-stop handling and retries before sending.
5. Connect voice to the same task APIs and approval semantics.

No production deployment, migration or campaign launch is included in this repository's initial push.
