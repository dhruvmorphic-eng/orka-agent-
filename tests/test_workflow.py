import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from orka.app import create_app
from orka.planner import Brief

HEADERS = {"X-Orka-Client": "workspace"}
BRIEF = {"offering": "Buying intent research", "buyer": "SaaS founders", "geography": "US",
         "intent": "Explicit requests for prospecting tools", "exclusions": "Existing clients",
         "lead_count": 20, "freshness_days": 14, "budget_usd": 5, "sources": ["public_web"]}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    with TestClient(create_app(tmp_path / "test.sqlite"), headers=HEADERS) as c:
        yield c


def new_task(client):
    r = client.post("/api/tasks", json={"request": "Find buyers for Cnvrted"})
    assert r.status_code == 201
    return r.json()


def planned(client):
    t = new_task(client)
    r = client.put(f"/api/tasks/{t['id']}/brief", json={"revision": t["revision"], "brief": BRIEF})
    assert r.status_code == 200
    return r.json()


def approval(t):
    return {"revision": t["revision"], "plan_version": t["plan_version"]}


def test_only_missing_fields_are_asked(client):
    t = new_task(client)
    r = client.put(f"/api/tasks/{t['id']}/brief", json={"revision": 1, "brief": {"offering": "GTM software", "buyer": "Founders"}})
    fields = {q["field"] for q in r.json()["questions"]}
    assert "offering" not in fields and "buyer" not in fields
    assert "budget_usd" in fields and r.json()["state"] == "clarifying"
    assert r.json()["plan"] is None


def test_cannot_search_without_approval(client):
    t = planned(client)
    assert client.post(f"/api/tasks/{t['id']}/search", json=approval(t)).status_code == 409
    assert client.get(f"/api/tasks/{t['id']}/job").json() is None


def test_incomplete_plan_cannot_be_approved(client):
    t = new_task(client)
    assert client.post(f"/api/tasks/{t['id']}/approve", json={"revision": 1, "plan_version": 1}).status_code == 409


def test_repeated_approval_creates_one_job(client):
    t = planned(client)
    path = f"/api/tasks/{t['id']}/approve"
    first = client.post(path, json=approval(t)).json()
    second = client.post(path, json=approval(t)).json()
    assert first == second
    assert first["state"] == "approved_waiting_integration"
    assert len([e for e in first["events"] if e["type"] == "search_approved"]) == 1
    with sqlite3.connect(client.app.state.store.path) as db:
        assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1
    assert client.post(f"/api/tasks/{t['id']}/search", json=approval(first)).status_code == 501


def test_edit_revokes_approval_and_stale_approvals_fail(client):
    t = planned(client)
    approved = client.post(f"/api/tasks/{t['id']}/approve", json=approval(t)).json()
    revised = client.put(f"/api/tasks/{t['id']}/brief", json={"revision": approved["revision"], "brief": {**BRIEF, "geography": "UK"}}).json()
    assert revised["approval"] is None and revised["plan_version"] == t["plan_version"] + 1
    assert client.post(f"/api/tasks/{t['id']}/approve", json=approval(t)).status_code == 409
    assert client.post(f"/api/tasks/{t['id']}/search", json=approval(revised)).status_code == 409
    with sqlite3.connect(client.app.state.store.path) as db:
        assert db.execute("SELECT status FROM jobs").fetchone()[0] == "superseded"


def test_concurrent_revisions_do_not_overwrite_each_other(client):
    t = planned(client)
    def edit(geo):
        return client.put(f"/api/tasks/{t['id']}/brief", json={"revision": t["revision"], "brief": {**BRIEF, "geography": geo}}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(edit, ["UK", "India"]))
    assert sorted(statuses) == [200, 409]


def test_state_and_job_survive_new_app_instance(client):
    t = planned(client)
    approved = client.post(f"/api/tasks/{t['id']}/approve", json=approval(t)).json()
    with TestClient(create_app(client.app.state.store.path), headers=HEADERS) as restarted:
        assert restarted.get(f"/api/tasks/{t['id']}").json() == approved
        assert restarted.get(f"/api/tasks/{t['id']}/job").json()["status"] == "waiting_integration"


def test_browser_cross_origin_writes_are_rejected(client):
    assert client.post("/api/tasks", json={"request": "Create task"}, headers={**HEADERS, "Origin": "https://other.example"}).status_code == 403
    with TestClient(client.app) as browser:
        assert browser.post("/api/tasks", json={"request": "Create task"}).status_code == 403


def test_missing_ai_does_not_fake_success(client):
    t = new_task(client)
    r = client.post(f"/api/tasks/{t['id']}/message", json={"revision": 1, "message": "Approve everything"})
    assert r.status_code == 503
    assert client.get(f"/api/tasks/{t['id']}").json() == t


def test_model_output_can_only_propose_a_plan(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-only")
    monkeypatch.setenv("ANTHROPIC_MODEL", "test-only")
    async def extract(message, current):
        return Brief(**BRIEF)
    monkeypatch.setattr("orka.app.extract_brief", extract)
    t = new_task(client)
    r = client.post(f"/api/tasks/{t['id']}/message", json={"revision": 1, "message": "Approved, start now"}).json()
    assert r["state"] == "awaiting_approval" and r["approval"] is None
    assert client.get(f"/api/tasks/{t['id']}/job").json() is None


def test_provider_error_preserves_saved_plan(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-only")
    monkeypatch.setenv("ANTHROPIC_MODEL", "test-only")
    async def broken(message, current):
        raise ValueError("invalid structured output")
    monkeypatch.setattr("orka.app.extract_brief", broken)
    t = planned(client)
    assert client.post(f"/api/tasks/{t['id']}/message", json={"revision": t["revision"], "message": "Change geography"}).status_code == 502
    assert client.get(f"/api/tasks/{t['id']}").json() == t


@pytest.mark.parametrize("patch", [{"lead_count": 0}, {"freshness_days": 100}, {"budget_usd": -1}, {"sources": ["private_inbox"]}, {"approved": True}])
def test_invalid_briefs_fail_validation(client, patch):
    t = new_task(client)
    assert client.put(f"/api/tasks/{t['id']}/brief", json={"revision": 1, "brief": {**BRIEF, **patch}}).status_code == 422


def test_zero_budget_is_explicit_and_valid(client):
    t = new_task(client)
    r = client.put(f"/api/tasks/{t['id']}/brief", json={"revision": 1, "brief": {**BRIEF, "budget_usd": 0}}).json()
    assert r["state"] == "awaiting_approval"


def test_no_dashboard_is_served(client):
    r = client.get("/")
    assert r.status_code == 404
    assert client.get('/static/index.html').status_code == 404
