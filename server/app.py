"""Intention web API: auth, personal records, top-10 leaderboards."""

from __future__ import annotations

import hmac
import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from hashlib import pbkdf2_hmac, sha256
from pathlib import Path
from typing import Iterator, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
WEB_DIR = ROOT / "web"
DB_PATH = DATA_DIR / "intention.db"
SECRET_PATH = DATA_DIR / "secret.key"

USERNAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁёІіЇїЄєҐґ0-9]{2,24}$")
ITERATIONS = 120_000
TOKEN_TTL = 60 * 60 * 24 * 30  # 30 days
DB_TIMEOUT = 5.0  # seconds to wait for a lock
BUSY_TIMEOUT_MS = 5000

VALID_VARIANTS = {
    "colors": {"2", "3"},
    "numbers": {str(n) for n in range(2, 11)},
}


def _secret() -> bytes:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if SECRET_PATH.exists():
        return SECRET_PATH.read_bytes()
    value = os.urandom(32)
    SECRET_PATH.write_bytes(value)
    return value


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or os.urandom(16)
    digest = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        check = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
        return hmac.compare_digest(check.hex(), digest_hex)
    except ValueError:
        return False


def make_token(user_id: int, username: str) -> str:
    payload = json.dumps(
        {"uid": user_id, "name": username, "exp": int(time.time()) + TOKEN_TTL},
        separators=(",", ":"),
    )
    body = payload.encode("utf-8").hex()
    sig = hmac.new(_secret(), body.encode("ascii"), sha256).hexdigest()
    return f"{body}.{sig}"


def parse_token(token: str) -> dict:
    try:
        body, sig = token.split(".", 1)
        expect = hmac.new(_secret(), body.encode("ascii"), sha256).hexdigest()
        if not hmac.compare_digest(expect, sig):
            raise ValueError("bad sig")
        data = json.loads(bytes.fromhex(body).decode("utf-8"))
        if int(data["exp"]) < time.time():
            raise ValueError("expired")
        return data
    except (ValueError, KeyError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="Invalid session")


def db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=DB_TIMEOUT)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    return conn


@contextmanager
def db_conn() -> Iterator[sqlite3.Connection]:
    """Connection with commit/rollback on exit and guaranteed close()."""
    conn = db()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db() -> None:
    with db_conn() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS scores (
                user_id INTEGER NOT NULL,
                mode TEXT NOT NULL,
                variant TEXT NOT NULL,
                best_streak INTEGER NOT NULL DEFAULT 0,
                best_accuracy REAL NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (user_id, mode, variant),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_scores_board
                ON scores (mode, variant, best_streak DESC, best_accuracy DESC);
            """
        )


init_db()

# Same-origin frontend: no CORS middleware needed.
# Docs are disabled so the public server exposes only its own pages.
app = FastAPI(
    title="Intention",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


class AuthIn(BaseModel):
    username: str = Field(min_length=2, max_length=24)
    password: str = Field(min_length=4, max_length=128)


class ScoreIn(BaseModel):
    mode: str
    variant: str
    streak: int = Field(ge=0, le=1_000_000)
    accuracy: float = Field(ge=0, le=100)


def current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Need login")
    data = parse_token(authorization.split(" ", 1)[1].strip())
    with db_conn() as conn:
        row = conn.execute("SELECT id, username FROM users WHERE id = ?", (data["uid"],)).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Need login")
    return {"id": row["id"], "username": row["username"]}


def validate_variant(mode: str, variant: str) -> None:
    if mode not in VALID_VARIANTS or str(variant) not in VALID_VARIANTS[mode]:
        raise HTTPException(status_code=400, detail="Unknown game variant")


def user_payload(user_id: int, username: str) -> dict:
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT mode, variant, best_streak, best_accuracy FROM scores WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    records: dict = {"colors": {}, "numbers": {}}
    for row in rows:
        records[row["mode"]][row["variant"]] = {
            "best_streak": row["best_streak"],
            "best_accuracy": round(row["best_accuracy"], 1),
        }
    return {
        "username": username,
        "token": make_token(user_id, username),
        "records": records,
    }


@app.post("/api/register")
def register(body: AuthIn) -> dict:
    name = body.username.strip()
    if not USERNAME_RE.match(name):
        raise HTTPException(
            status_code=400,
            detail="Name: 2–24 letters or digits (Latin or Cyrillic)",
        )
    with db_conn() as conn:
        exists = conn.execute("SELECT id FROM users WHERE username = ?", (name,)).fetchone()
        if exists:
            raise HTTPException(status_code=409, detail="Name already taken")
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (name, hash_password(body.password), int(time.time())),
        )
        user_id = int(cur.lastrowid)
    return user_payload(user_id, name)


@app.post("/api/login")
def login(body: AuthIn) -> dict:
    name = body.username.strip()
    with db_conn() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (name,),
        ).fetchone()
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Wrong name or password")
    return user_payload(row["id"], row["username"])


@app.get("/api/me")
def me(user: dict = Depends(current_user)) -> dict:
    data = user_payload(user["id"], user["username"])
    data.pop("token", None)
    return data


@app.post("/api/score")
def submit_score(body: ScoreIn, user: dict = Depends(current_user)) -> dict:
    validate_variant(body.mode, body.variant)
    now = int(time.time())
    with db_conn() as conn:
        row = conn.execute(
            """
            SELECT best_streak, best_accuracy FROM scores
            WHERE user_id = ? AND mode = ? AND variant = ?
            """,
            (user["id"], body.mode, body.variant),
        ).fetchone()
        streak = body.streak
        accuracy = round(float(body.accuracy), 1)
        if row:
            better = streak > row["best_streak"] or (
                streak == row["best_streak"] and accuracy > row["best_accuracy"]
            )
            if better:
                conn.execute(
                    """
                    UPDATE scores SET best_streak = ?, best_accuracy = ?, updated_at = ?
                    WHERE user_id = ? AND mode = ? AND variant = ?
                    """,
                    (streak, accuracy, now, user["id"], body.mode, body.variant),
                )
        else:
            conn.execute(
                """
                INSERT INTO scores (user_id, mode, variant, best_streak, best_accuracy, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user["id"], body.mode, body.variant, streak, accuracy, now),
            )
    data = user_payload(user["id"], user["username"])
    data.pop("token", None)
    rec = data["records"].get(body.mode, {}).get(body.variant, {"best_streak": 0, "best_accuracy": 0})
    return {"ok": True, "record": rec}


@app.get("/api/leaderboard")
def leaderboard(mode: str, variant: str, user: dict = Depends(current_user)) -> dict:
    validate_variant(mode, variant)
    with db_conn() as conn:
        rows = conn.execute(
            """
            SELECT u.username, s.best_streak, s.best_accuracy
            FROM scores s
            JOIN users u ON u.id = s.user_id
            WHERE s.mode = ? AND s.variant = ?
            ORDER BY s.best_streak DESC, s.best_accuracy DESC, u.username COLLATE NOCASE
            LIMIT 10
            """,
            (mode, variant),
        ).fetchall()
        mine = conn.execute(
            """
            SELECT best_streak, best_accuracy FROM scores
            WHERE user_id = ? AND mode = ? AND variant = ?
            """,
            (user["id"], mode, variant),
        ).fetchone()
    return {
        "mode": mode,
        "variant": variant,
        "top": [
            {
                "place": i + 1,
                "username": r["username"],
                "best_streak": r["best_streak"],
                "best_accuracy": round(r["best_accuracy"], 1),
            }
            for i, r in enumerate(rows)
        ],
        "me": {
            "best_streak": mine["best_streak"] if mine else 0,
            "best_accuracy": round(mine["best_accuracy"], 1) if mine else 0.0,
        },
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
