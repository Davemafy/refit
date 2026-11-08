"""Executable security-policy and integrity tests for Refit's sandbox runner.

Docker integration tests are opt-in for CI or a disposable Vultr test VM:
    REFIT_TEST_DOCKER=1 python -m unittest tests.test_refit_sandbox -v
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import unittest
from unittest.mock import patch

from scripts.sandbox_runner import (
    DockerSandbox, HOSTILE_PROBE, SAFE_PROBE, chain_events, verify_chain,
)


def fake_commands(results):
    sequence = iter(results)
    def execute(command, **kwargs):
        if "--cidfile" in command:
            from pathlib import Path
            Path(command[command.index("--cidfile") + 1]).write_text("a" * 64)
            mount = command[command.index("--mount") + 1]
            payload = Path(mount.split("src=", 1)[1].split(",", 1)[0])
            assert payload.stat().st_mode & 0o777 == 0o755
            assert (payload / "program.py").stat().st_mode & 0o777 == 0o644
        response = next(sequence)
        if isinstance(response, Exception):
            raise response
        return response
    return execute


class SandboxPolicyTests(unittest.TestCase):
    def test_hardened_command_has_no_network_or_host_secret_mounts(self):
        from pathlib import Path
        flags = DockerSandbox()._command(
            "refit-test", Path("/tmp/refit-fake/payload"), Path("/tmp/refit-fake/cid"))
        self.assertIn("none", flags)
        self.assertEqual(flags[flags.index("--network") + 1], "none")
        self.assertEqual(flags[flags.index("--runtime") + 1], "runc")
        self.assertEqual(flags[flags.index("--user") + 1], "65534:65534")
        self.assertEqual(flags[flags.index("--cap-drop") + 1], "ALL")
        self.assertIn("--read-only", flags)
        self.assertIn("no-new-privileges:true", flags)
        self.assertEqual(flags[flags.index("--memory") + 1], "128m")
        self.assertEqual(flags[flags.index("--pids-limit") + 1], "32")
        self.assertIn("readonly", flags[flags.index("--mount") + 1])
        self.assertNotIn("/var/run/docker.sock", " ".join(flags))
        self.assertNotIn("/etc/refit", " ".join(flags))
        self.assertNotIn("--privileged", flags)
        self.assertNotIn("--env-file", flags)
        self.assertNotIn("-e", flags)
        self.assertNotIn("--publish", flags)

    def test_private_host_visible_staging_supports_docker_mount(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory(prefix="refit-shared-stage-") as directory:
            root = Path(directory)
            runner = DockerSandbox(staging_root=root)
            self.assertEqual(runner.staging_root, root)
            # The Docker source must be visible to the host daemon, not a
            # private /tmp namespace remapped by systemd.
            with patch("scripts.sandbox_runner.secrets.token_hex", return_value="stage1"), \
                 patch("scripts.sandbox_runner.shutil.which", return_value="/usr/bin/docker"), \
                 patch("scripts.sandbox_runner.subprocess.run") as run:
                run.side_effect = fake_commands([
                    subprocess.CompletedProcess(args=["docker"], returncode=0),
                    subprocess.CompletedProcess(args=["docker", "rm"], returncode=0, stdout="", stderr=""),
                    subprocess.CompletedProcess(args=["docker", "inspect"], returncode=1,
                                               stdout="[]\n", stderr="Error: No such container: refit-stage1\n"),
                    subprocess.CompletedProcess(args=["docker", "info"], returncode=0,
                                               stdout='"healthy-daemon"', stderr=""),
                ])
                result = runner.run("print(1)")
                command = run.call_args_list[0].args[0]
                mount = command[command.index("--mount") + 1]
                self.assertIn("src=" + str(root) + "/", mount)
                self.assertTrue(result["container_removed_verified"])
            with self.assertRaises(ValueError):
                DockerSandbox(staging_root=Path("relative-staging"))

    def test_payload_readable_under_private_operator_umask(self):
        previous = os.umask(0o077)
        try:
            self.test_successful_execution_records_cleanup()
        finally:
            os.umask(previous)

    def test_runtime_and_image_allowlist(self):
        self.assertEqual(DockerSandbox(runtime="runsc").runtime, "runsc")
        with self.assertRaises(ValueError):
            DockerSandbox(runtime="privileged")
        with self.assertRaises(ValueError):
            DockerSandbox(image="attacker/payload")
        with self.assertRaises(ValueError):
            DockerSandbox(timeout_seconds=1000)

    def test_trusted_image_identity_is_content_addressed(self):
        pinned = "sha256:" + "a" * 64
        with patch.dict(os.environ, {"REFIT_DIAGNOSTIC_IMAGE_ID": pinned}):
            runner = DockerSandbox(runtime="runsc")
            self.assertEqual(runner.image, pinned)
            self.assertEqual(runner._command("refit-safe", __import__("pathlib").Path("/tmp/refit"),
                         __import__("pathlib").Path("/tmp/cid"))[-6], pinned)
            with self.assertRaises(ValueError):
                DockerSandbox(image="attacker/image")
        with patch.dict(os.environ, {"REFIT_DIAGNOSTIC_IMAGE_ID": "python:latest"}):
            with self.assertRaises(ValueError):
                DockerSandbox()

    def test_ledger_detects_modified_or_reordered_records(self):
        records = chain_events([
            {"type": "launch_requested", "digest": "abc"},
            {"type": "execution_observed", "exit_code": 1},
            {"type": "cleanup_checked", "container_absent": True},
        ])
        self.assertTrue(verify_chain(records))
        records[1]["event"]["exit_code"] = 0
        self.assertFalse(verify_chain(records))
        records[1]["event"]["exit_code"] = 1
        self.assertTrue(verify_chain(records))
        self.assertFalse(verify_chain(list(reversed(records))))

    @patch("scripts.sandbox_runner.secrets.token_hex", return_value="abc123")
    @patch("scripts.sandbox_runner.shutil.which", return_value="/usr/bin/docker")
    @patch("scripts.sandbox_runner.subprocess.run")
    def test_successful_execution_records_cleanup(self, run, which, token):
        run.side_effect = fake_commands([
            subprocess.CompletedProcess(args=["docker"], returncode=0),
            subprocess.CompletedProcess(args=["docker", "rm"], returncode=0, stdout="", stderr=""),
            subprocess.CompletedProcess(args=["docker", "inspect"], returncode=1,
                                        stdout="[]\n", stderr="Error: No such container: refit-abc123\n"),
            subprocess.CompletedProcess(args=["docker", "info"], returncode=0,
                                        stdout='"healthy-daemon"\n', stderr=""),
        ])
        result = DockerSandbox().run("print(1)", {"answer": 1})
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["ledger_valid"])
        self.assertTrue(result["container_removed_verified"])
        first = run.call_args_list[0].args[0]
        self.assertEqual(first[0], "prlimit")
        self.assertIn("--fsize=65536:65536", first)
        self.assertIn("--network", first)
        self.assertEqual(len(result["ledger"]), 3)

    @patch("scripts.sandbox_runner.secrets.token_hex", return_value="abc123")
    @patch("scripts.sandbox_runner.shutil.which", return_value="/usr/bin/docker")
    @patch("scripts.sandbox_runner.subprocess.run")
    def test_timeout_still_forces_docker_removal(self, run, which, token):
        run.side_effect = fake_commands([
            subprocess.TimeoutExpired(cmd="docker", timeout=2),
            subprocess.CompletedProcess(args=["docker", "rm"], returncode=0, stdout="", stderr=""),
            subprocess.CompletedProcess(args=["docker", "inspect"], returncode=1,
                                        stdout="[]\n", stderr="Error: No such container: refit-abc123\n"),
            subprocess.CompletedProcess(args=["docker", "info"], returncode=0,
                                        stdout='"healthy-daemon"\n', stderr=""),
        ])
        result = DockerSandbox(timeout_seconds=2).run("while True: pass")
        self.assertEqual(result["status"], "timeout")
        self.assertTrue(result["container_removed_verified"])
        self.assertTrue(result["timed_out"])
        self.assertEqual(run.call_args_list[1].args[0][1:3], ["rm", "-f"])

    @patch("scripts.sandbox_runner.shutil.which", return_value="/usr/bin/docker")
    @patch("scripts.sandbox_runner.subprocess.run")
    def test_cleanup_failure_is_visible_not_hidden(self, run, which):
        run.side_effect = fake_commands([
            subprocess.CompletedProcess(args=["docker"], returncode=0),
            subprocess.CompletedProcess(args=["docker", "rm"], returncode=1, stdout="", stderr="permission denied"),
            subprocess.CompletedProcess(args=["docker", "inspect"], returncode=0, stdout="[{}]", stderr=""),
            subprocess.CompletedProcess(args=["docker", "info"], returncode=0, stdout='"healthy-daemon"', stderr=""),
        ])
        result = DockerSandbox().run("print(1)")
        self.assertFalse(result["container_removed_verified"])
        self.assertEqual(result["status"], "cleanup_unverified")
        self.assertTrue(result["ledger_valid"])

    @patch("scripts.sandbox_runner.shutil.which", return_value="/usr/bin/docker")
    @patch("scripts.sandbox_runner.subprocess.run")
    def test_input_validation_stops_untrusted_code_before_docker(self, run, which):
        runner = DockerSandbox()
        for code, payload in [
            ("", {}),
            ("a" * 30000, {}),
            ("print('\\0')\0", {}),
            ("print(1)", {"oversize": "x" * 90000}),
        ]:
            with self.subTest(size=len(code)):
                with self.assertRaises(ValueError):
                    runner.run(code, payload)
        run.assert_not_called()


@unittest.skipUnless(
    os.getenv("REFIT_TEST_DOCKER") == "1",
    "needs opt-in and a real disposable Docker-capable runner",
)
class RealDockerContainmentTests(unittest.TestCase):
    def runner(self):
        # Override only the real, opt-in integration tests. Mock policy tests
        # should continue asserting the standard runc baseline.
        return DockerSandbox(runtime=os.environ.get('REFIT_TEST_RUNTIME', 'runc'),
                             timeout_seconds=25)

    def test_safe_generated_python_execution(self):
        result = self.runner().run(
            SAFE_PROBE,
            {"counts": {"source_passed": 8, "target_passed": 6}},
            label="safe_probe",
        )
        self.assertEqual(result["status"], "passed", result["stderr"])
        self.assertEqual(result["exit_code"], 0)
        self.assertTrue(result["container_removed_verified"])
        self.assertTrue(result["ledger_valid"])
        self.assertEqual(json.loads(result["stdout"])["delta"], 2)

    def test_hostile_program_cannot_access_host_or_egress(self):
        result = self.runner().run(
            HOSTILE_PROBE, label="hostile_probe")
        self.assertEqual(result["status"], "passed", result["stderr"])
        self.assertTrue(result["container_removed_verified"])
        self.assertTrue(result["ledger_valid"])
        probes = json.loads(result["stdout"])
        self.assertEqual(probes["key_file"], "FileNotFoundError")
        self.assertFalse(probes["key_in_env"])
        self.assertNotEqual(probes["dns"], "unexpectedly_resolved")
        self.assertNotEqual(probes["outbound_connection"], "unexpectedly_connected")
        self.assertNotEqual(probes["root_write"], "unexpectedly_writable")


if __name__ == "__main__":
    unittest.main()
