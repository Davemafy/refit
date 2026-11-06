"""Daemon failures, ambiguous inspect errors and timeouts must never prove absence."""
from __future__ import annotations

import json
import subprocess
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from scripts.docker_cleanup import remove_and_verify
from scripts.sandbox_runner import DockerSandbox, verify_chain
from scripts.sandbox_tool_gateway import ToolSandboxEnvironment, ToolSandboxUnavailable


NAME = "refit-tool-test123"


def result(code=0, out="", err=""):
    return subprocess.CompletedProcess([], code, stdout=out, stderr=err)


def missing(name=NAME):
    return result(1, "[]\n", f"Error: No such container: {name}\n")


def healthy():
    return result(0, json.dumps("healthy-daemon"))


class DockerCleanupTests(unittest.TestCase):
    @patch("scripts.docker_cleanup.subprocess.run")
    def test_explicit_absence_on_healthy_daemon_is_verified(self, run):
        run.side_effect = [result(), missing(), healthy()]
        env = {"PATH": "/usr/bin", "DOCKER_HOST": "unix:///run/approved.sock"}
        proof = remove_and_verify("docker", NAME, env=env)
        self.assertTrue(proof["verified"])
        self.assertEqual(proof["daemon_id"], "healthy-daemon")
        self.assertEqual(proof["reason"], "verified_absent")
        self.assertTrue(all(c.kwargs["env"] is env for c in run.call_args_list))

    @patch("scripts.docker_cleanup.subprocess.run")
    def test_auto_removal_accepts_only_explicit_missing_response(self, run):
        run.side_effect = [missing(), missing(), healthy()]
        self.assertTrue(remove_and_verify("docker", NAME)["verified"])

    @patch("scripts.docker_cleanup.subprocess.run")
    def test_inspection_errors_are_not_equivalent_to_absence(self, run):
        bad = [result(1, err="Cannot connect to the Docker daemon"),
               result(1, err="permission denied"), result(1),
               result(1, err="Error: No such container: refit-other"),
               result(1, err=f"Error: No such container: {NAME}\nCannot connect"),
               result(2, err=f"Error: No such container: {NAME}"),
               result(0, out="[{}]"),
               subprocess.TimeoutExpired("docker inspect", 8),
               FileNotFoundError("docker missing")]
        for inspection in bad:
            with self.subTest(inspection=inspection):
                run.side_effect = [result(), inspection, healthy()]
                proof = remove_and_verify("docker", NAME)
                self.assertFalse(proof["verified"])
                self.assertEqual(proof["reason"], "absence_not_established")

    @patch("scripts.docker_cleanup.subprocess.run")
    def test_daemon_failure_after_missing_response_is_unverified(self, run):
        for health in [result(1, err="daemon unavailable"), result(0),
                       result(0, out='""'), result(0, out="null"),
                       result(0, out='"daemon"', err="connection warning"),
                       subprocess.TimeoutExpired("docker info", 8), OSError("socket failed")]:
            with self.subTest(health=health):
                run.side_effect = [result(), missing(), health]
                proof = remove_and_verify("docker", NAME)
                self.assertFalse(proof["verified"])
                self.assertEqual(proof["reason"], "daemon_health_not_established")

    @patch("scripts.docker_cleanup.subprocess.run")
    def test_removal_timeout_preserves_evidence_and_still_checks_absence(self, run):
        run.side_effect = [subprocess.TimeoutExpired("docker rm", 8), missing(), healthy()]
        proof = remove_and_verify("docker", NAME)
        self.assertFalse(proof["verified"])
        self.assertEqual(proof["removal"]["error"], "TimeoutExpired")
        self.assertEqual(proof["reason"], "removal_failed")
        self.assertEqual(run.call_count, 3)
        self.assertTrue(all(c.kwargs["timeout"] == 8 for c in run.call_args_list))

    @patch("scripts.sandbox_runner.shutil.which", return_value="/usr/bin/docker")
    @patch("scripts.docker_cleanup.subprocess.run")
    def test_generated_execution_cannot_pass_when_daemon_is_unavailable(self, run, which):
        run.side_effect = [result(), result(1, err="daemon unavailable"),
                           result(1, err="daemon unavailable"), result(1, err="daemon unavailable")]
        record = DockerSandbox().run("print(1)")
        self.assertEqual(record["status"], "cleanup_unverified")
        self.assertFalse(record["container_removed_verified"])
        self.assertTrue(verify_chain(record["ledger"]))
        self.assertFalse(record["ledger"][-1]["event"]["evidence"]["verified"])

    @patch("scripts.sandbox_runner.secrets.token_hex", return_value="cidtest")
    @patch("scripts.sandbox_runner.shutil.which", return_value="/usr/bin/docker")
    @patch("scripts.docker_cleanup.subprocess.run")
    def test_zero_exit_code_without_creation_receipt_is_not_container_proof(self, run, which, token):
        run.side_effect = [result(), result(), missing("refit-cidtest"), healthy()]
        record = DockerSandbox().run("print(1)")
        self.assertFalse(record["container_created"])
        self.assertIsNone(record["container_id"])
        self.assertEqual(record["status"], "runtime_error")
        self.assertTrue(record["container_removed_verified"])

    def session(self):
        session = object.__new__(ToolSandboxEnvironment)
        session.closed = False
        session.cleanup_verified = False
        session.proc = None
        session.docker = "docker"
        session.docker_env = {"PATH": "/usr/bin"}
        session.container = NAME
        session.domain, session.phase, session.index = "refund", "train", 0
        session.runtime = "runsc"
        session.records = []
        session.started = time.monotonic()
        session.temp = tempfile.TemporaryDirectory()
        return session

    @patch("scripts.docker_cleanup.subprocess.run")
    def test_tool_gateway_records_failure_and_repeated_close_stays_failed(self, run):
        run.side_effect = [result(), result(1, err="daemon unavailable"), healthy()]
        session = self.session()
        with self.assertRaisesRegex(ToolSandboxUnavailable, "cleanup not verified"):
            session.close()
        self.assertFalse(session.records[0]["container_absent"])
        self.assertIn("cleanup_evidence", session.records[0])
        with self.assertRaisesRegex(ToolSandboxUnavailable, "previously unverified"):
            session.close()
        self.assertEqual(run.call_count, 3)

    @patch("scripts.docker_cleanup.subprocess.run")
    def test_worker_shutdown_timeout_cannot_skip_docker_removal(self, run):
        run.side_effect = [result(), missing(), healthy()]
        session = self.session()
        session.proc = Mock()
        session.proc.poll.return_value = None
        session.proc.wait.side_effect = subprocess.TimeoutExpired("docker run", 2)
        with self.assertRaises(ToolSandboxUnavailable):
            session.close()
        session.proc.kill.assert_called_once()
        self.assertEqual(run.call_count, 3)
        self.assertFalse(session.records[0]["container_absent"])
        self.assertEqual(session.records[0]["process_cleanup_error"], "TimeoutExpired")

    @patch("scripts.docker_cleanup.subprocess.run")
    def test_successful_gateway_close_is_idempotent(self, run):
        run.side_effect = [result(), missing(), healthy()]
        session = self.session()
        session.close()
        session.close()
        self.assertTrue(session.records[0]["container_absent"])
        self.assertEqual(len(session.records), 1)
        self.assertEqual(run.call_count, 3)


if __name__ == "__main__":
    unittest.main()
