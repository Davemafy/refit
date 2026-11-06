# Public deployment — Refit on the existing Vultr VM

This is the **ship-first** path for the working, same-origin demo and API.
The separate UI workstream can later replace the root page without changing
any Python backend endpoints.

## First deployment

On the Ubuntu 24.04 Vultr VM, as root (not on the laptop):

```bash
cd /opt/refit-app
git pull --ff-only
bash deploy/launch-public.sh
```

The script first runs offline tests and syntax checks, then:

- Installs Nginx only if missing; creates a systemd service as the unprivileged
  `refit` user (not root, not in the Docker group).
- Binds the Python backend to 127.0.0.1:8097, with Nginx on HTTP port 80.
- Exposes the demo at `/` and `/demo`; the backend at `/api/*`.
- Enables restart on failure and requires backend health checks to pass.
- Serves genuine recorded Vultr results, an intent parser and patch export.
- Deliberately disables public paid inference, live agent execution,
  and sandbox diagnostics until TLS/operator authentication are provisioned.

For a host with another application already using port 80, the script checks
Nginx configuration and refuses to overwrite a nonstandard default site.
With a DNS hostname already pointing to the VM, use:

```bash
REFIT_HOSTNAME=refit.example.com bash deploy/launch-public.sh
```

Substitute an actual DNS name; this command does **not** register a domain
or issue an HTTPS certificate.

## External acceptance check

From any separate internet-connected computer after deploying, run:

```bash
python3 -m scripts.smoke_public --url http://YOUR_VULTR_IP
```

This checks the rendered HTML, API health, capabilities, the two authentic
recorded migration cases, signed-by-digest patch artifact, recorded events and
natural-language interpretation. It triggers **no billable calls**.

Expected factual evidence:

- Refund: 8/8 source, 6/8 replacement, 8/8 repaired holdout.
- Deployment: compatible on the tested sample; **no patch**.
- All data served through actual HTTP routes from the running backend.

Local VM acceptance:

```bash
systemctl --no-pager status refit-public nginx
curl -fsS http://127.0.0.1:8097/api/health
python3 -m scripts.smoke_public --url http://127.0.0.1:8097
```

The web panel is a standalone integration fallback, not the final UI design.
The frontend team should use `docs/api-contract.md` as its source of truth.

## Replacing the fallback with the final UI

Deploy the independently built frontend on localhost port 3000 (or its own
static directory). Keep these Nginx routes pointing to port 8097:

- `/api/*` — Refit Python backend.
- `/demo*` — the always-available integration demo.

Only change the final Nginx `location /` block to the frontend's port 3000
or static build, then run `nginx -t && systemctl reload nginx`. Keep all
frontend requests to `/api/*` same-origin; never paste the operator or
Vultr inference token into JavaScript bundles.

## Enabling real operator runs later

**First establish HTTPS**, using an actual domain and a TLS certificate.
Then provision a securely stored bearer token and a separate restricted
execution service with access to the Vultr inference credential and gVisor.
Do not lift the read-only public service's restrictions merely to enable a
live button. The operator-only endpoints are already implemented, but this
public deployment intentionally leaves them unavailable.

The provided gVisor scripts and evidence are separate:
`deploy/install-gvisor.sh` and `deploy/verify-gvisor-on-host.sh`.

A public page and green tests do **not** establish full migration-agent
isolation, support for third-party agent imports, or a production service.
