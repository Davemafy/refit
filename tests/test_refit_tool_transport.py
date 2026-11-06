"""Real pipe regressions; no Docker, network, or inference calls."""
from contextlib import contextmanager
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from scripts.sandbox_tool_gateway import ToolSandboxEnvironment, ToolSandboxUnavailable


class ToolTransportTests(unittest.TestCase):
    @contextmanager
    def worker(self, body):
        with tempfile.TemporaryDirectory() as directory:
            ready = Path(directory) / "ready"
            script = (
                "import os,sys,time\nfrom pathlib import Path\n"
                "def mark(): Path(sys.argv[1]).touch()\n" + body
            )
            proc = subprocess.Popen(
                [sys.executable, "-u", "-c", script, str(ready)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, bufsize=0,
            )
            try:
                deadline = time.monotonic() + 3
                while not ready.exists():
                    if proc.poll() is not None or time.monotonic() > deadline:
                        self.fail("test worker failed to become ready")
                    time.sleep(.005)
                session = object.__new__(ToolSandboxEnvironment)
                session.closed = False
                session.proc = proc
                session.started = time.monotonic()
                yield session
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=3)
                proc.stdin.close()
                proc.stdout.close()

    def assert_deadline(self, body, command=None, pipe_size=None):
        with self.worker(body) as session, patch(
                "scripts.sandbox_tool_gateway.REPLY_SECONDS", .15):
            if pipe_size is not None:
                import fcntl
                fcntl.fcntl(session.proc.stdin.fileno(), fcntl.F_SETPIPE_SZ, pipe_size)
            started = time.monotonic()
            with self.assertRaisesRegex(ToolSandboxUnavailable, "timed out"):
                session._exchange(command or {"op": "verify"})
            self.assertLess(time.monotonic() - started, .8)

    def test_partial_response_does_not_block_after_first_readable_byte(self):
        self.assert_deadline("os.write(1,b'{\"result\":'); mark(); time.sleep(2)\n")

    def test_continuous_trickle_does_not_extend_total_deadline(self):
        self.assert_deadline(
            "os.write(1,b'{\"result\":\"'); mark()\n"
            "for _ in range(80):\n time.sleep(.025); os.write(1,b'x')\n"
        )

    @unittest.skipUnless(sys.platform == "linux", "requires Linux pipe sizing")
    def test_worker_not_reading_request_cannot_block_sender(self):
        self.assert_deadline("mark(); time.sleep(2)\n",
                             {"padding": "x" * 30000}, pipe_size=4096)

    def test_fragmented_complete_replies_and_next_exchange_work(self):
        with self.worker(
            "mark()\nfor _ in range(2):\n"
            " sys.stdin.buffer.readline()\n"
            " os.write(1,b'{\"result\":'); time.sleep(.025)\n"
            " os.write(1,b'{\"ok\":true}}\\n')\n"
        ) as session:
            for _ in range(2):
                self.assertEqual(session._exchange({"op": "verify"}),
                                 {"result": {"ok": True}})

    def test_eof_before_newline_is_not_a_complete_response(self):
        with self.worker(
            "os.write(1,b'{\"result\":{}}'); mark(); time.sleep(.15)\n"
        ) as session:
            with self.assertRaisesRegex(ToolSandboxUnavailable, "incomplete"):
                session._exchange({"op": "verify"})

    def test_oversized_partial_response_is_rejected(self):
        with self.worker("mark(); os.write(1,b'x'*131073); time.sleep(2)\n") as session:
            with self.assertRaisesRegex(ToolSandboxUnavailable, "oversized"):
                session._exchange({"op": "verify"})
