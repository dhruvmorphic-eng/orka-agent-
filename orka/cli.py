"""Conversational terminal entry point; no dashboard or running web server needed."""
import asyncio
import os
import re
import sys
from pathlib import Path

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from .planner import Brief, ai_enabled, extract_brief
from .store import Store

SOURCE_NAMES = {"web": "public_web", "companies": "company_sites", "discussions": "public_discussions", "jobs": "job_pages"}
FIELD_NAMES = {"offer": "offering", "buyer": "buyer", "geography": "geography", "intent": "intent", "exclude": "exclusions", "count": "lead_count", "days": "freshness_days", "budget": "budget_usd", "sources": "sources"}
APPROVALS = {"yes", "approve", "approved", "go ahead", "yes, go ahead", "y"}


def clean(text):
    # Prevent terminal control sequences in user or provider content.
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", str(text))
    return "".join(c for c in text if c in "\n\t" or (c.isprintable() and c != "\x1b"))


def parse_answer(field, answer):
    value = answer.strip()
    if not value:
        raise ValueError("Give me an answer, or type /quit to save and leave.")
    if field in {"lead_count", "freshness_days"}:
        value = int(value)
    elif field == "budget_usd":
        value = float(value.removeprefix("$").strip())
    elif field == "sources":
        words = re.split(r"[,\s]+", value.lower())
        if words == ["all"]:
            value = list(SOURCE_NAMES.values())
        else:
            value = list(dict.fromkeys(SOURCE_NAMES.get(w, w) for w in words))
    return getattr(Brief.model_validate({field: value}), field)


class Terminal:
    def __init__(self, store, write=print, reader=input, enabled=ai_enabled, extractor=extract_brief):
        self.store, self.write, self.reader = store, write, reader
        self.enabled, self.extractor = enabled, extractor
        self.task = None
        self.pending = None
        self.reviewed = None

    def say(self, text):
        self.write("  " + clean(text).replace("\n", "\n  "))

    def show(self):
        t = self.task
        self.reviewed = None
        if t["questions"]:
            self.pending = t["questions"][0]["field"]
            self.say("\norka › " + t["questions"][0]["question"])
            if self.pending == "sources":
                self.say("Choose: web, companies, discussions, jobs — or all.")
            if not self.enabled() and self.pending in {"lead_count", "freshness_days", "budget_usd"}:
                self.say("A number is enough.")
            return
        self.pending = None
        b = t["brief"]
        self.say(f"\nPLAN v{t['plan_version']}  ·  {t['id'][:8]}")
        for label, key in [("Offer", "offering"), ("Buyer", "buyer"), ("Where", "geography"), ("Evidence", "intent"), ("Exclude", "exclusions")]:
            self.say(f"  {label:9} {b[key] or 'None specified'}")
        self.say(f"  Scope     {b['lead_count']} leads · last {b['freshness_days']} days · ${b['budget_usd']:g} search cap")
        self.say("  Sources   " + ", ".join(b["sources"]))
        for i, step in enumerate(t["plan"]["steps"], 1):
            self.say(f"  {i}. {step}")
        self.say(t["plan"]["approval_scope"])
        self.say(t["plan"]["estimate"] + " AI planning is billed separately.")
        self.say("Stop at the spend cap, target count, or source exhaustion.")
        if t["approval"]:
            self.say("\n✓ Approval saved. Search integration is pending; nothing has run.")
        else:
            self.reviewed = (t["revision"], t["plan_version"])
            self.say("\norka › Approve this search plan? Say yes, or tell me what to change.")
        if not self.enabled():
            self.say("To revise in guided mode: /edit geography UK  (type /help for fields)")

    def save_brief(self, brief, message):
        self.task = self.store.revise(self.task["id"], self.task["revision"], brief, message)
        self.show()

    def propose(self, message):
        self.say("… Understanding your request")
        brief = asyncio.run(self.extractor(message, self.task["brief"]))
        self.save_brief(brief.model_dump(), message)

    def handle(self, text):
        text = text.strip()
        if not text:
            return True
        if len(text) > 4000:
            self.say("Please keep this message under 4,000 characters.")
            return True
        if text.lower() in {"/quit", "/exit"}:
            return False
        if text == "/help":
            self.say("Talk naturally. Say yes only after reviewing a plan.\n/new — start a task\n/tasks — list saved tasks\n/resume NUMBER — continue a listed task\n/plan — show the current plan or next question\n/edit FIELD VALUE — revise a detail\nFields: " + ", ".join(FIELD_NAMES) + "\n/quit — save and leave")
        elif text == "/new":
            self.task = self.pending = self.reviewed = None
            self.say("What would you like me to find?")
        elif text == "/tasks":
            for i, t in enumerate(self.store.list(), 1):
                self.say(f"{i}. {t['request']} [{t['state']}]")
            self.say("Use /resume NUMBER to continue.")
        elif text.startswith("/resume "):
            rows = self.store.list()
            try:
                index = int(text.split(maxsplit=1)[1]) - 1
                if index < 0 or index >= len(rows):
                    raise ValueError()
                self.task = rows[index]
                self.say("Resumed: " + self.task["request"])
                self.show()
            except (ValueError, IndexError):
                self.say("Use /tasks, then /resume followed by a listed number.")
        elif text == "/plan":
            if self.task:
                self.task = self.store.get(self.task["id"])
                self.show()
            else:
                self.say("Tell me what you want to find first.")
        elif text.startswith("/edit "):
            if not self.task:
                self.say("Start a task first.")
            else:
                parts = text.split(maxsplit=2)
                if len(parts) != 3 or parts[1] not in FIELD_NAMES:
                    self.say("Use /edit FIELD VALUE. Type /help for the field names.")
                else:
                    field = FIELD_NAMES[parts[1]]
                    self.save_brief({**self.task["brief"], field: parse_answer(field, parts[2])}, text)
        elif text.startswith("/"):
            self.say("Unknown command. Type /help, or just talk to me.")
        elif not self.task:
            if len(text) < 3:
                self.say("Tell me a little more about the research goal.")
                return True
            self.task = self.store.create(text)
            self.say("✓ Task saved")
            if self.enabled():
                self.propose(text)
            else:
                self.show()
        elif text.lower().rstrip(".! ") in APPROVALS:
            if self.reviewed is None:
                self.say("Let's finish and review the plan before approving it.")
                self.show()
            else:
                revision, version = self.reviewed
                self.task = self.store.approve(self.task["id"], revision, version)
                self.reviewed = None
                self.say("✓ Search approval saved. Search is not connected yet; no research or emails have run.")
        elif self.enabled():
            self.propose(text)
        elif self.pending:
            self.save_brief({**self.task["brief"], self.pending: parse_answer(self.pending, text)}, text)
        else:
            self.say("Use /edit FIELD VALUE to revise this plan, or yes to approve. Natural-language revisions need AI configuration.")
        return True

    def run(self):
        self.say("\nORKA / CNVRTED\nYour sales agent. Tell me the goal; we'll work out the next move.\n")
        self.say("AI conversation enabled." if self.enabled() else "Guided conversation · AI provider not connected. I'll ask one question at a time.")
        self.say("Planning + approval ready · search / enrichment / voice / sending pending\n/help for shortcuts · /tasks to resume · Ctrl+C to leave\n")
        self.say("What would you like me to find?")
        while True:
            try:
                if not self.handle(self.reader("\n  you › ")):
                    break
            except (EOFError, KeyboardInterrupt):
                break
            except HTTPException as exc:
                self.reviewed = None
                self.say(exc.detail)
                if self.task:
                    self.task = self.store.get(self.task["id"])
                    self.show()
            except (ValueError, ValidationError):
                self.say("That answer didn't fit. Check the number or source name and try again; your saved plan is unchanged.")
            except (httpx.HTTPError, KeyError, RuntimeError):
                self.say("The AI provider couldn't finish. Your task is saved. Retry, use /edit, or type /plan.")
        self.say("\nSession saved. See you next time.\n")


def main():
    default = Path(__file__).resolve().parent.parent / "data" / "orka.sqlite"
    Terminal(Store(os.environ.get("ORKA_DB", str(default)))).run()
