"""Crash-safe local run store for the single-process Refit operator service.

The live API must use one worker process, one server instance and persistent
local storage. This is not a distributed queue or multi-host lock.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets


RUN_ID = re.compile(r"(?:live|diagnostic|app)-[0-9a-f]{16}\Z")
ALLOWED_MODES = {"live", "live_diagnostic", "application_live"}


class RunStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def save(self, run_id: str, run: dict, events: list[dict]):
        if not RUN_ID.fullmatch(run_id) or run.get("id") != run_id:
            raise ValueError("invalid durable run id")
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        record = {"schema": 2, "run": run, "events": events}
        blob = json.dumps(record, indent=2, ensure_ascii=False).encode("utf8") + b"\n"
        path = self.directory / (run_id + ".json")
        temp = self.directory / ("." + run_id + "." + secrets.token_hex(8) + ".tmp")
        # Unlike umask(), os.open(mode=0600) is safe in a threaded server.
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as file:
                file.write(blob)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp, path)
            descriptor = os.open(self.directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            temp.unlink(missing_ok=True)

    def load(self):
        """Return records, plus names of invalid files for operator visibility.

        Legacy v1 snapshots store just the run and no event history.
        """
        records = []
        invalid = []
        if not self.directory.is_dir():
            return records, invalid
        for path in sorted(self.directory.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf8"))
                if not isinstance(raw, dict):
                    raise ValueError("invalid stored document")
                run = raw.get("run", raw)
                events = raw.get("events", [])
                if (not isinstance(run, dict) or
                        not isinstance(run.get("id"), str) or
                        not RUN_ID.fullmatch(run["id"]) or
                        path.name != run["id"] + ".json" or
                        run.get("mode") not in ALLOWED_MODES or
                        not isinstance(run.get("status"), str) or
                        not isinstance(events, list)):
                    raise ValueError("invalid saved run")
                for index, event in enumerate(events):
                    if (not isinstance(event, dict) or event.get("seq") != index + 1
                            or not isinstance(event.get("type"), str)
                            or not isinstance(event.get("message"), str)):
                        raise ValueError("invalid saved event sequence")
                records.append((run, events))
            except (OSError, TypeError, ValueError):
                invalid.append(path.name)
        return records, invalid
