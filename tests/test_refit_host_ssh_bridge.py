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
        self.assertIn("date -u -d '+48 hours'", setup)
        self.assertIn('== --rotate-key', setup)
        self.assertIn('STAGING=', setup)
        self.assertIn('SSH_ORIGINAL_COMMAND', command)
        self.assertRegex(command, re.compile(r'\^deploy\[\[:space:\]\].*\{40\}'))
        self.assertIn('merge --ff-only', command)
        self.assertIn('REFIT_APPLICATION_DAILY_BUDGET', command)

    def test_application_launcher_replaces_stale_checkout_override(self):
        launcher = (ROOT/'deploy/launch-application.sh').read_text()
        subprocess.run(['bash','-n',str(ROOT/'deploy/launch-application.sh')],
                       check=True,timeout=5)
        self.assertIn('zz-refit-managed-checkout.conf', launcher)
        self.assertIn('WorkingDirectory=$REPO', launcher)
        self.assertIn('Environment=REFIT_DEPLOYED_REVISION=$REVISION', launcher)
        self.assertIn('SERVICE_DIRECTORY', launcher)
        self.assertIn('api/application/release', launcher)
        self.assertIn('[[ "$installed" == "$REVISION" ]]', launcher)


    def test_devmcp_gateway_public_key_is_time_limited_and_forced(self):
        path = ROOT / 'deploy/setup-devmcp-host-access.sh'
        subprocess.run(['bash','-n',str(path)],check=True,timeout=5)
        source = path.read_text()
        self.assertIn('restrict,expiry-time=', source)
        self.assertIn('command="%s"', source)
        self.assertIn('refit-devmcp-gateway', source)
        self.assertIn('ssh-keygen -lf', source)
        self.assertIn('refit-host-ssh-command.sh', source)
        self.assertIn('REFIT_APPLICATION_DAILY_BUDGET', source)
        self.assertNotIn('BEGIN OPENSSH PRIVATE KEY', source)

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
