# Refit: durable 48-hour host access

This GitHub Actions bridge replaces the old **dev-MCP workspace-held SSH private key**. GitHub Actions keeps the client key in an encrypted repository secret, and Vultr only accepts that key for **48 hours** after each authorization. No permanent interactive root key, public password, or reusable key in ChatGPT is needed.

The SSH key is forced to execute only `status` or `deploy <exact-main-SHA>`; it cannot open a shell, forward ports, or run arbitrary commands. The public key's `expiry-time` is enforced by OpenSSH; the same key can be reauthorized by rerunning the host setup command. The setup preserves other `authorized_keys` entries.

## One-time connection

From the Vultr **root terminal/console**, using the existing checkout:

```bash
cd /opt/refit-app
git pull --ff-only origin main
bash deploy/setup-github-ssh-access.sh
```

The setup checks the checkout, installs a root-owned forced-command handler, generates an Ed25519 key if necessary, pins the server's host key and adds an `expiry-time` authorized-key entry. It retains the current application request quotas in `/etc/refit/host-ssh/budgets.env`; it does not alter Vultr inference secrets or restart the app.

**Never send the printed private key to ChatGPT or commit it.** Open [Refit → Settings → Secrets and variables → Actions](https://github.com/Davemafy/refit/settings/secrets/actions). Create exactly these repository secrets using the corresponding marked blocks printed by setup:

- `REFIT_HOST_SSH_PRIVATE_KEY`: complete OpenSSH private key, including BEGIN/END lines.
- `REFIT_HOST_KNOWN_HOSTS`: complete `80.240.30.92 ssh-ed25519 ...` line printed from `/etc/ssh/ssh_host_ed25519_key.pub`. The pinned entry is necessary to prevent connecting to an impersonated host.

Then open [Refit host bridge workflow](https://github.com/Davemafy/refit/actions/workflows/refit-host-ssh.yml), select **Run workflow → status**, and confirm the status shows the current git SHA, active service and public HTTP response. The operator should not mistake a missing-secret failure for successful connectivity.

## Deploy and renew

In GitHub Actions choose **Run workflow → deploy**. The runner executes only the revision associated with that workflow, verifies `origin/main` matches it, fast-forwards a clean checkout, rebuilds the original gVisor runtime, reinstalls/restarts the application and runs independent HTTPS revision acceptance. The SSH session itself is limited to 23 minutes. A repository-controlled `ops/refit-host-request.json` change also supports a GitHub-connector-controlled `status` or `deploy` request without needing a new assistant workspace.

The host authorization expires 48 hours after the last setup. To renew it for another 48 hours (the GitHub secrets do **not** need replacing):

```bash
cd /opt/refit-app
sudo bash deploy/setup-github-ssh-access.sh
```

To replace the private key, run `bash deploy/setup-github-ssh-access.sh --rotate-key` on Vultr. The script generates a new key pair, replaces only this bridge's authorized-key entry, and prints the new private key and pinned host-key line. Update both GitHub Actions secrets. If the key is merely hard to copy, `--show-key` reprints the existing key without rotating it. Never paste the private key into a chat. Since the SSH key is a restricted root authorization, keep repository admin and Actions permissions limited to trusted operators. The bridge is for deployments and health checks, **not** a general interactive root shell.

For deliberate budget changes, edit the root-only `/etc/refit/host-ssh/budgets.env`, rather than allowing workflow inputs to set arbitrary values. Missing files, mismatched SHA, dirty repository, expired key, failed gVisor checks, missing auth secrets or failed HTTPS acceptance cause the deployment to fail rather than report success.
