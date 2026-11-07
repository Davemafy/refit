"""Offline checks for the finite GitHub Actions SSH bridge."""
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]

class SSHBridgeTests(unittest.TestCase):
    def test_bash_syntax_and_restricted_entry(self):
        for name in ('deploy/setup-github-ssh-access.sh', 'deploy/refit-host-ssh-command.sh'):
            with self.subTest(script=name):
                subprocess.run(['bash', '-n', str(ROOT/name)], check=True, timeout=5)
        setup = (ROOT/'deploy/setup-github-ssh-access.sh').read_text()
        command = (ROOT/'deploy/refit-host-ssh-command.sh').read_text()
        self.assertIn('expiry-time=', setup)
        self.assertIn('restrict,expiry-time=', setup)
        self.assertIn('SSH_ORIGINAL_COMMAND', command)
        self.assertRegex(command, re.compile(r'\^deploy\[\[:space:\]\].*\{40\}'))
        self.assertIn('merge --ff-only', command)
        self.assertIn('REFIT_APPLICATION_DAILY_BUDGET', command)

    def test_workflow_never_requests_root_shell(self):
        workflow = (ROOT/'.github/workflows/refit-host-ssh.yml').read_text()
        self.assertIn('workflow_dispatch:', workflow)
        self.assertIn("paths:\n      - 'ops/refit-host-request.json'", workflow)
        self.assertIn('StrictHostKeyChecking=yes', workflow)
        self.assertIn('REFIT_HOST_SSH_PRIVATE_KEY', workflow)
        self.assertIn('REFIT_HOST_KNOWN_HOSTS', workflow)
        self.assertNotIn('StrictHostKeyChecking=no', workflow)

if __name__=='__main__':
    unittest.main()
