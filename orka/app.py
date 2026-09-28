"""Local, single-operator milestone. Bind to loopback only; see README."""
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .planner import Brief, ai_enabled, extract_brief
from .store import Store



class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CreateTask(Input):
    request: str = Field(min_length=3, max_length=4000)


class ReviseTask(Input):
    revision: int = Field(ge=1)
    brief: Brief


class Message(Input):
    revision: int = Field(ge=1)
    message: str = Field(min_length=1, max_length=4000)


class Approval(Input):
    revision: int = Field(ge=1)
    plan_version: int = Field(ge=1)


def create_app(db_path=None):
    if db_path is None:
        from .settings import load_credentials
        load_credentials()
    app = FastAPI(title="Orka · Approval-first sales agent", version="0.1.0")
    store = Store(db_path or os.environ.get("ORKA_DB", "data/orka.sqlite"))
    app.state.store = store
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        # This prototype has no multi-user auth. Reject non-loopback callers and cross-site writes.
        if not request.client or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            return JSONResponse({"detail": "Local access only"}, status_code=403)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if request.headers.get("x-orka-client") != "workspace" or (origin and origin != str(request.base_url).rstrip("/")):
                return JSONResponse({"detail": "Same-origin workspace request required"}, status_code=403)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/capabilities")
    def capabilities():
        return {"ai_planner": ai_enabled(), "search": False, "enrichment": False, "campaigns": False, "voice": False, "mode": "local_single_operator"}

    @app.get("/api/tasks")
    def tasks():
        return store.list()

    @app.post("/api/tasks", status_code=201)
    def create(body: CreateTask):
        return store.create(body.request)

    @app.get("/api/tasks/{task_id}")
    def get(task_id: str):
        return store.get(task_id)

    @app.put("/api/tasks/{task_id}/brief")
    def revise(task_id: str, body: ReviseTask):
        return store.revise(task_id, body.revision, body.brief.model_dump())

    @app.post("/api/tasks/{task_id}/message")
    async def message(task_id: str, body: Message):
        task = store.get(task_id)
        if task["revision"] != body.revision:
            raise HTTPException(409, "This task changed. Reload before sending.")
        if not ai_enabled():
            raise HTTPException(503, "AI planner is not configured. Use the terminal guided conversation; your task is saved.")
        try:
            brief = await extract_brief(body.message, task["brief"])
        except (httpx.HTTPError, ValueError, KeyError):
            raise HTTPException(502, "The planner could not produce a valid brief. Your saved plan is unchanged; retry or edit the fields.")
        return store.revise(task_id, body.revision, brief.model_dump(), body.message)

    @app.post("/api/tasks/{task_id}/approve")
    def approve(task_id: str, body: Approval):
        return store.approve(task_id, body.revision, body.plan_version)

    @app.get("/api/tasks/{task_id}/job")
    def job(task_id: str):
        return store.job(task_id)

    @app.post("/api/tasks/{task_id}/search")
    def search(task_id: str, body: Approval):
        task = store.get(task_id)
        if (task["revision"] != body.revision or not task["approval"]
                or task["approval"]["plan_version"] != body.plan_version
                or task["plan_version"] != body.plan_version):
            raise HTTPException(409, "The current search plan must be explicitly approved first.")
        raise HTTPException(501, "Search adapter is not connected. No search was executed.")

    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/")
    def home():
        return FileResponse(static / "index.html")

    return app
