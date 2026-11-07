"""Persistent account, session, invite and project storage for the HTTPS service."""
import argparse
from contextlib import contextmanager
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time

USERNAME = re.compile(r"[a-z0-9][a-z0-9_-]{2,39}")
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
SESSION_TTL = 12 * 3600
PROJECT_LIMIT = 3


def digest(secret):
    return hashlib.sha256(secret.encode()).hexdigest()


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=1, maxmem=64 * 1024**2)


class Accounts:
    def __init__(self, state):
        self.path = Path(state) / "accounts.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.touch(mode=0o600, exist_ok=True)
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, salt BLOB NOT NULL, hash BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS invites (hash TEXT PRIMARY KEY, expires INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    hash TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES users(id), expires INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES users(id),
                    summary TEXT NOT NULL, snapshot TEXT NOT NULL
                );
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()

    def invite(self, ttl=86400):
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        with self.db() as db:
            db.execute("DELETE FROM invites WHERE expires<=?", (now,))
            db.execute("INSERT INTO invites VALUES (?,?)", (digest(token), now + ttl))
        return token

    @staticmethod
    def credentials(username, password):
        if (not isinstance(username, str) or not USERNAME.fullmatch(username)
                or not isinstance(password, str) or not 12 <= len(password) <= 128):
            raise ValueError("Use a 3–40 character lowercase username and a 12–128 character password.")

    def register(self, username, password):
        """Public signup; preserve strong passwords, transactional uniqueness and session isolation."""
        self.credentials(username, password)
        owner, salt = secrets.token_hex(16), secrets.token_bytes(16)
        hashed = password_hash(password, salt)
        try:
            with self.db() as db:
                db.execute("INSERT INTO users VALUES (?,?,?,?)", (owner, username, salt, hashed))
        except sqlite3.IntegrityError:
            raise ValueError("That username is unavailable.") from None
        return self.session(owner)

    def login(self, username, password):
        self.credentials(username, password)
        with self.db() as db:
            row = db.execute("SELECT id,salt,hash FROM users WHERE username=?", (username,)).fetchone()
        owner, salt, expected = row or (None, bytes(16), bytes(64))
        if not hmac.compare_digest(password_hash(password, salt), expected) or owner is None:
            raise ValueError("Invalid username or password.")
        return self.session(owner)

    def review_session(self, owner, expires):
        # This identity cannot be used with public username/password authentication.
        with self.db() as db:
            db.execute("INSERT OR IGNORE INTO users VALUES (?,?,?,?)",
                       (owner, "!" + owner, b"", b""))
        return self.session(owner, expires)

    def session(self, owner, expires=None):
        secret = secrets.token_urlsafe(32)
        now = int(time.time())
        with self.db() as db:
            db.execute("DELETE FROM sessions WHERE expires<=?", (now,))
            db.execute("INSERT INTO sessions VALUES (?,?,?)", (digest(secret), owner, min(now + SESSION_TTL, expires) if expires else now + SESSION_TTL))
        return secret

    def resolve(self, secret):
        if not TOKEN.fullmatch(secret):
            return None
        with self.db() as db:
            return db.execute("""SELECT users.id, users.username FROM sessions
                JOIN users ON sessions.owner=users.id WHERE sessions.hash=? AND sessions.expires>?""",
                (digest(secret), int(time.time()))).fetchone()

    def logout(self, secret):
        if TOKEN.fullmatch(secret):
            with self.db() as db:
                db.execute("DELETE FROM sessions WHERE hash=?", (digest(secret),))

    def save_project(self, owner, ident, summary, snapshot):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT count(*) FROM projects WHERE owner=?", (owner,)).fetchone()[0] >= PROJECT_LIMIT:
                raise ValueError("Remove an imported project before uploading another.")
            db.execute("INSERT INTO projects VALUES (?,?,?,?)",
                       (ident, owner, json.dumps(summary), json.dumps(snapshot)))

    def list_projects(self, owner):
        with self.db() as db:
            return [json.loads(row[0]) for row in db.execute(
                "SELECT summary FROM projects WHERE owner=? ORDER BY rowid DESC", (owner,))]

    def project(self, owner, ident):
        with self.db() as db:
            row = db.execute("SELECT snapshot,summary FROM projects WHERE owner=? AND id=?", (owner, ident)).fetchone()
            return tuple(map(json.loads, row)) if row else None

    def source_report(self, owner, ident):
        with self.db() as db:
            row = db.execute("SELECT json_extract(snapshot, '$.source_report') FROM projects WHERE owner=? AND id=?",
                             (owner, ident)).fetchone()
            return json.loads(row[0]) if row and row[0] else ([] if row else None)

    def remove_project(self, owner, ident):
        with self.db() as db:
            return db.execute("DELETE FROM projects WHERE owner=? AND id=?", (owner, ident)).rowcount == 1


def main():
    parser = argparse.ArgumentParser(description="Issue a single-use Refit enrollment invitation.")
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    print(Accounts(args.state).invite())


if __name__ == "__main__":
    main()
