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
                CREATE TABLE IF NOT EXISTS public_trials (
                    day TEXT NOT NULL,
                    client_digest TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    PRIMARY KEY (day, client_digest)
                );
                CREATE TABLE IF NOT EXISTS guest_issues (
                    day TEXT NOT NULL,
                    client_digest TEXT NOT NULL,
                    owner TEXT NOT NULL UNIQUE,
                    PRIMARY KEY (day, client_digest, owner)
                );
                CREATE TABLE IF NOT EXISTS guest_migrations (
                    day TEXT NOT NULL,
                    client_digest TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    reservation TEXT NOT NULL PRIMARY KEY,
                    requests INTEGER NOT NULL
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

    def open_guest(self, day, client_digest):
        """Create an independent private visitor principal; never share one per IP.

        The issuance ledger is persistent across restarts and cookie clearing.
        The HMAC client digest is not the address itself.
        """
        if not (isinstance(client_digest, str) and len(client_digest) == 64):
            raise ValueError("Invalid visitor identifier")
        owner = "guest-" + secrets.token_hex(16)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM guest_issues WHERE day<?", (day,))
            count = db.execute("SELECT count(*) FROM guest_issues WHERE day=? AND client_digest=?",
                               (day, client_digest)).fetchone()[0]
            if count >= 12:
                return None
            db.execute("INSERT INTO guest_issues VALUES (?,?,?)", (day, client_digest, owner))
        # Create the owner and its secure, scoped session, not a shared account.
        return owner, self.review_session(owner, int(time.time()) + SESSION_TTL)

    def claim_guest_run(self, day, client_digest, owner, budget, reservation):
        """Atomic per-client daily control, independent of guest cookie rotation."""
        if (not owner.startswith("guest-") or type(budget) is not int or
                not 1 <= budget <= 32 or len(client_digest) != 64):
            return False
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM guest_migrations WHERE day<?", (day,))
            matching = db.execute(
                "SELECT count(*), coalesce(sum(requests),0) FROM guest_migrations "
                "WHERE day=? AND client_digest=?", (day, client_digest)).fetchone()
            if matching[0] >= 3 or matching[1] + budget > 64:
                return False
            db.execute("INSERT INTO guest_migrations VALUES (?,?,?,?,?)",
                       (day, client_digest, owner, reservation, budget))
        return True

    def release_guest_run(self, reservation, owner):
        with self.db() as db:
            db.execute("DELETE FROM guest_migrations WHERE reservation=? AND owner=?",
                       (reservation, owner))

    def claim_public_trial(self, day, client_digest, owner, daily_limit):
        """Atomically reserve one anonymous trial per client and UTC day.

        Never store client IP addresses. Claims survive service restarts and
        cannot be multiplied by clearing session cookies.
        """
        if (not isinstance(day, str) or len(day) != 10 or
                not isinstance(client_digest, str) or len(client_digest) != 64 or
                not owner.startswith("guest-") or not 1 <= daily_limit <= 64):
            raise ValueError("Invalid public trial reservation")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM public_trials WHERE day < ?", (day,))
            if db.execute("SELECT 1 FROM public_trials WHERE day=? AND client_digest=?",
                          (day, client_digest)).fetchone():
                return "already_used"
            count = db.execute("SELECT COUNT(*) FROM public_trials WHERE day=?", (day,)).fetchone()[0]
            if count >= daily_limit:
                return "daily_limit"
            db.execute("INSERT INTO public_trials (day, client_digest, owner) VALUES (?,?,?)",
                       (day, client_digest, owner))
        return "reserved"

    def release_public_trial(self, day, client_digest, owner):
        """Undo only a reservation that never launched an inference run."""
        with self.db() as db:
            db.execute("DELETE FROM public_trials WHERE day=? AND client_digest=? AND owner=?",
                       (day, client_digest, owner))

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

    def expired_guest_owners(self):
        """List temporary principals with no active session; preserve rate ledgers."""
        timestamp = int(time.time())
        with self.db() as db:
            db.execute("DELETE FROM sessions WHERE expires<=?", (timestamp,))
            rows = db.execute(
                "SELECT id FROM users WHERE id LIKE 'guest-%' AND "
                "NOT EXISTS (SELECT 1 FROM sessions WHERE sessions.owner=users.id)"
            ).fetchall()
        return [row[0] for row in rows]

    def purge_guest_owner(self, owner):
        """Delete only expired anonymous identity/source; never touch user accounts."""
        if not isinstance(owner, str) or not owner.startswith("guest-"):
            raise ValueError("Only expired temporary guest workspaces may be purged.")
        timestamp = int(time.time())
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            live = db.execute(
                "SELECT 1 FROM sessions WHERE owner=? AND expires>?",
                (owner, timestamp)).fetchone()
            if live:
                return False
            db.execute("DELETE FROM sessions WHERE owner=?", (owner,))
            db.execute("DELETE FROM projects WHERE owner=?", (owner,))
            db.execute("DELETE FROM users WHERE id=?", (owner,))
        return True

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
