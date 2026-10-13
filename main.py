import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi import Path as PathParam
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

DB = os.environ.get("BATON_DB", "baton.db")
STATIC = Path(__file__).parent / "static"

NAME = r"^[a-z0-9_]{1,40}$"


class Claim(BaseModel):
    holder: str = Field(min_length=1, max_length=40)
    minutes: int = Field(default=30, ge=1, le=480)
    note: str = Field(default="", max_length=120)


class Extend(BaseModel):
    holder: str = Field(min_length=1, max_length=40)
    minutes: int = Field(default=15, ge=1, le=480)


class Release(BaseModel):
    holder: str = Field(min_length=1, max_length=40)
    force: bool = False


app = FastAPI(title="baton")


def connect():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db


with closing(connect()) as db, db:
    db.executescript(
        """
        create table if not exists resources (
            name text primary key,
            holder text,
            note text not null default '',
            held_until integer
        );
        create table if not exists events (
            id integer primary key autoincrement,
            name text not null,
            holder text not null,
            action text not null,
            at integer not null
        );
        """
    )


def view(row, now):
    left = max(0, (row["held_until"] or 0) - now)
    return {
        "name": row["name"],
        "holder": row["holder"] if left else None,
        "note": row["note"] if left else "",
        "seconds_left": left,
    }


def fetch(db, name):
    return db.execute("select * from resources where name = ?", (name,)).fetchone()


def log(db, name, holder, action, now):
    db.execute(
        "insert into events (name, holder, action, at) values (?, ?, ?, ?)",
        (name, holder, action, now),
    )


@app.get("/api/resources")
def list_resources():
    now = int(time.time())
    with closing(connect()) as db:
        rows = db.execute("select * from resources order by name").fetchall()
    return [view(r, now) for r in rows]


@app.get("/api/events")
def list_events():
    with closing(connect()) as db:
        rows = db.execute(
            "select name, holder, action, at from events order by id desc limit 25"
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/resources/{name}/claim")
def claim(body: Claim, name: str = PathParam(pattern=NAME)):
    now = int(time.time())
    with closing(connect()) as db, db:
        db.execute("insert or ignore into resources (name) values (?)", (name,))
        cur = db.execute(
            "update resources set holder = ?, note = ?, held_until = ? "
            "where name = ? and (held_until is null or held_until <= ? or holder = ?)",
            (body.holder, body.note, now + body.minutes * 60, name, now, body.holder),
        )
        if cur.rowcount == 0:
            raise HTTPException(409, view(fetch(db, name), now))
        log(db, name, body.holder, "claimed", now)
        return view(fetch(db, name), now)


@app.post("/api/resources/{name}/extend")
def extend(body: Extend, name: str = PathParam(pattern=NAME)):
    now = int(time.time())
    with closing(connect()) as db, db:
        cur = db.execute(
            "update resources set held_until = held_until + ? "
            "where name = ? and holder = ? and held_until > ?",
            (body.minutes * 60, name, body.holder, now),
        )
        if cur.rowcount == 0:
            raise HTTPException(409, f"{body.holder} does not hold {name}")
        log(db, name, body.holder, "extended", now)
        return view(fetch(db, name), now)


@app.post("/api/resources/{name}/release")
def release(body: Release, name: str = PathParam(pattern=NAME)):
    now = int(time.time())
    with closing(connect()) as db, db:
        row = fetch(db, name)
        if row is None:
            raise HTTPException(404, f"no resource called {name}")
        current = view(row, now)
        if current["holder"] is None:
            return current
        if current["holder"] != body.holder and not body.force:
            raise HTTPException(403, current)
        db.execute(
            "update resources set holder = null, note = '', held_until = null where name = ?",
            (name,),
        )
        action = "released" if current["holder"] == body.holder else "forced release of"
        log(db, name, body.holder, action, now)
        return view(fetch(db, name), now)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
