import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from .planner import Brief, plan_for, questions


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, task_id TEXT NOT NULL, plan_version INTEGER NOT NULL,
                    status TEXT NOT NULL, plan TEXT NOT NULL,
                    UNIQUE(task_id, plan_version)
                );
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def read(self, db, task_id):
        row = db.execute("SELECT document FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Task not found")
        return json.loads(row[0])

    def save(self, db, task):
        task["updated_at"] = now()
        db.execute("INSERT OR REPLACE INTO tasks VALUES (?, ?)", (task["id"], json.dumps(task)))
        return task

    def list(self):
        with self.connection() as db:
            tasks = [json.loads(r[0]) for r in db.execute("SELECT document FROM tasks")]
            return sorted(tasks, key=lambda t: t["updated_at"], reverse=True)

    def get(self, task_id):
        with self.connection() as db:
            return self.read(db, task_id)

    def create(self, request):
        brief = Brief().model_dump()
        task = {"id": str(uuid.uuid4()), "request": request, "revision": 1, "plan_version": 0,
                "state": "clarifying", "brief": brief, "plan": None, "approval": None,
                "questions": questions(brief), "created_at": now(),
                "messages": [{"role": "user", "text": request}],
                "events": [{"type": "created", "at": now()}]}
        with self.connection() as db:
            return self.save(db, task)

    def revise(self, task_id, revision, brief, message=None):
        brief = Brief.model_validate(brief).model_dump()
        with self.connection() as db:
            task = self.read(db, task_id)
            if task["revision"] != revision:
                raise HTTPException(409, "This task changed. Reload before saving.")
            task["revision"] += 1
            task["plan_version"] += 1
            task["brief"] = brief
            task["questions"] = questions(brief)
            task["plan"] = None if task["questions"] else plan_for(brief)
            task["state"] = "clarifying" if task["questions"] else "awaiting_approval"
            task["approval"] = None
            db.execute("UPDATE jobs SET status='superseded' WHERE task_id=?", (task_id,))
            if message and not (task["messages"] and task["messages"][-1] == {"role": "user", "text": message}):
                task["messages"].append({"role": "user", "text": message})
            task["messages"].append({"role": "assistant", "text":
                " ".join(q["question"] for q in task["questions"][:2]) if task["questions"] else
                "Here’s the search I propose. Tell me what to change, or approve it when you’re ready."})
            task["events"].append({"type": "plan_revised", "plan_version": task["plan_version"], "at": now()})
            return self.save(db, task)

    def approve(self, task_id, revision, version):
        with self.connection() as db:
            task = self.read(db, task_id)
            if version != task["plan_version"]:
                raise HTTPException(409, "That plan version is no longer current.")
            if task["approval"] and task["approval"]["plan_version"] == version:
                return task  # Repeated clicks cannot enqueue duplicate work.
            if revision != task["revision"]:
                raise HTTPException(409, "This task changed. Reload before approving.")
            if task["state"] != "awaiting_approval" or not task["plan"]:
                raise HTTPException(409, "Complete and review the plan before approving.")
            task["revision"] += 1
            task["approval"] = {"plan_version": version, "at": now(), "scope": "search_only", "actor": "local_operator"}
            task["state"] = "approved_waiting_integration"
            db.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, ?)",
                       (str(uuid.uuid4()), task_id, version, "waiting_integration", json.dumps(task["plan"])))
            task["events"].append({"type": "search_approved", "plan_version": version, "at": now()})
            task["messages"].append({"role": "assistant", "text": "Search plan approved and saved. Search is not connected yet; no research has run and no emails have been sent."})
            return self.save(db, task)

    def job(self, task_id):
        with self.connection() as db:
            task = self.read(db, task_id)
            row = db.execute("SELECT id, status, plan_version FROM jobs WHERE task_id=? AND plan_version=?",
                             (task_id, task["plan_version"])).fetchone()
            return dict(zip(("id", "status", "plan_version"), row)) if row else None
