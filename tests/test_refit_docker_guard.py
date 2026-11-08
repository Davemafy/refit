"""Deny-by-default test suite for the restricted host Docker authority."""
from __future__ import annotations
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.container_agent import command as app_command
from scripts.docker_guard import permitted, diagnostic_mount
from scripts.sandbox_runner import DockerSandbox

APP = "sha256:" + "a" * 64
DIAGNOSTIC = "sha256:" + "b" * 64
IMAGES = {"application": APP, "diagnostic": DIAGNOSTIC}
NAME = "refit-app-" + "a" * 20
DNAME = "refit-" + "b" * 20
SRC = Path("/var/lib/refit-application/sandbox-staging/refit-sandbox-abc123/payload")
CID = SRC.parent / "container.id"


class DockerGuardPolicyTests(unittest.TestCase):
    def test_real_app_vector_is_approved_and_cannot_choose_another_image(self):
        argv = app_command(APP, NAME)[1:]
        self.assertTrue(permitted(argv, IMAGES))
        self.assertTrue(permitted(["image", "inspect", "--format={{.Id}}", APP], IMAGES))
        self.assertTrue(permitted(["inspect", NAME], IMAGES))
        for alternative in ("--privileged", "runc", "host", "--volume", "/var/run/docker.sock"):
            changed = list(argv)
            if alternative == "runc":
                changed[changed.index("runsc")] = "runc"
            elif alternative == "host":
                changed[changed.index("none")] = "host"
            else:
                changed.insert(-1, alternative)
            with self.subTest(alternative=alternative):
                self.assertFalse(permitted(changed, IMAGES))
        self.assertFalse(permitted(argv[:-1] + [DIAGNOSTIC], IMAGES))

    def test_real_diagnostic_vector_is_approved_only_for_valid_staging(self):
        with patch.dict(os.environ, {"REFIT_DIAGNOSTIC_IMAGE_ID": DIAGNOSTIC}):
            argv = DockerSandbox(runtime="runsc")._command(DNAME, SRC, CID)[1:]
        with patch("scripts.docker_guard.diagnostic_mount", return_value=True) as stage:
            self.assertTrue(permitted(argv, IMAGES))
            stage.assert_called_once_with(str(SRC), str(CID))
        with patch("scripts.docker_guard.diagnostic_mount", return_value=False):
            self.assertFalse(permitted(argv, IMAGES))
        changed = argv[:]
        changed[changed.index("none")] = "bridge"
        with patch("scripts.docker_guard.diagnostic_mount", return_value=True):
            self.assertFalse(permitted(changed, IMAGES))
        changed = argv[:]
        changed[changed.index("--read-only")] = "--privileged"
        with patch("scripts.docker_guard.diagnostic_mount", return_value=True):
            self.assertFalse(permitted(changed, IMAGES))

    def test_denies_arbitrary_root_equivalent_commands(self):
        forbidden = [
            ["ps", "-a"], ["exec", "-it", NAME, "sh"],
            ["build", "-t", "test", "."], ["run", "--privileged", "alpine"],
            ["cp", "/etc/shadow", NAME + ":/etc"],
            ["volume", "create", "host"],
            ["container", "inspect", "postgresql"],
            ["rm", "-f", "another-container"],
            ["image", "inspect", "--format={{.Id}}", DIAGNOSTIC],
            ["info", "--format", "{{json .SecurityOptions}}"],
            ["system", "prune", "-af"],
            ["run", "-v", "/:/host", "--name", NAME, APP],
        ]
        for argv in forbidden:
            with self.subTest(argv=argv):
                self.assertFalse(permitted(argv, IMAGES))
        self.assertTrue(permitted(["info", "--format", "{{json .Runtimes}}"], IMAGES))
        self.assertTrue(permitted(["info", "--format", "{{json .ID}}"], IMAGES))
        self.assertTrue(permitted(["rm", "-f", NAME], IMAGES))
        self.assertTrue(permitted(["container", "inspect", DNAME], IMAGES))

    def test_rejects_unsafe_staging_paths(self):
        self.assertFalse(diagnostic_mount("/tmp/unsafe/payload", "/tmp/unsafe/container.id"))
        self.assertFalse(diagnostic_mount(str(SRC), str(CID.parent / "wrong.id")))
        self.assertFalse(diagnostic_mount(
            "/var/lib/refit-application/sandbox-staging/refit-sandbox-abc123/../payload", str(CID)))
        self.assertFalse(diagnostic_mount(
            "/var/lib/refit-application/sandbox-staging/refit-sandbox-abc123/payload", "/etc/passwd"))


if __name__ == "__main__":
    unittest.main()
