"""Read-only, zero-inference smoke test of Refit's public HTTPS account ingress.

Intentionally never registers, authenticates, imports, starts jobs or consumes inference.
The existing HTTP evidence acceptance is a separate test.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import ipaddress
import json
import re
from pathlib import Path
import socket
import ssl
import sys
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def check(origin: str, expected_revision: str | None = None) -> dict:
    address = urlsplit(origin)
    if address.scheme != "https" or not address.hostname or address.username or address.password or address.query or address.fragment or address.path not in ("", "/"):
        raise ValueError("Supply a bare HTTPS origin with no credentials, path or query.")
    host = address.hostname
    port = address.port or 443
    # The standard TLS context verifies both chain and the IP-address SAN.
    context = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=10) as raw:
        with context.wrap_socket(raw, server_hostname=host) as conn:
            certificate = conn.getpeercert()
    expires = datetime.fromtimestamp(ssl.cert_time_to_seconds(certificate["notAfter"]), timezone.utc)
    remaining = int((expires - datetime.now(timezone.utc)).total_seconds())
    if remaining < 24 * 3600:
        raise AssertionError("The public TLS certificate expires within 24 hours.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if ("IP Address", host) not in certificate.get("subjectAltName", ()):
            raise AssertionError("The HTTPS certificate does not cover the public IP address.")

    observations = []

    def get(path: str, extra_headers: dict | None = None):
        request = Request(origin.rstrip("/") + path, headers=extra_headers or {})
        try:
            response = urlopen(request, timeout=12, context=context)
        except HTTPError as exc:
            response = exc
        with response:
            raw = response.read(65_537)
            if len(raw) > 65_536:
                raise AssertionError("Unexpectedly large response")
            return response.status, response.headers, raw.decode("utf-8")

    release_status, _, release_body = get("/api/application/release")
    deployed_revision = None
    if release_status == 200:
        deployed_revision = json.loads(release_body).get("revision")
        assert isinstance(deployed_revision, str) and re.fullmatch(r"[0-9a-f]{40}", deployed_revision)
    if expected_revision is not None and deployed_revision != expected_revision:
        raise AssertionError(f"Expected deployed revision {expected_revision}, got {deployed_revision}")
    demo_status, _, demo_body = get("/api/application/demo")
    if demo_status == 200:
        example = json.loads(demo_body)
        assert example["public_sample"] and example["run"]["id"] == "demo-python-2026-11-07"
        assert example["run"]["status"] == "compatible_on_sample"
        for route in ("/", "/docs", "/login", "/signup", "/bring", "/app",
                      "/app/agents", "/app/agents/new", "/app/runs",
                      "/app/runs/demo-python-2026-11-07"):
            status, headers, page = get(route)
            assert status == 200, (route, status)
            assert headers.get("Cache-Control") == "no-store"
            if route.startswith("/app") or route == "/bring":
                assert 'id="page"' in page, route
        observations.append({"check": "guest_workspace_and_recorded_demo", "state": "open"})
    else:
        # A source push may precede VM promotion. Verify the older deployed
        # release without falsely reporting the new guest feature as active.
        status, headers, page = get("/bring")
        assert status == 200 and "Bring your agent" in page and "Sign in" in page
        assert headers.get("Cache-Control") == "no-store"
        observations.append({"check": "guest_workspace", "state": "awaiting_host_promotion"})
    assert "frame-ancestors 'none'" in headers.get("Content-Security-Policy", "")
    assert "max-age=" in headers.get("Strict-Transport-Security", "")
    status, _, response = get("/api/application/session")
    session = json.loads(response)
    assert status == 200 and session == {"mode": "account", "username": None}
    observations.append({"check": "anonymous_session", "status": status, "mode": session["mode"]})

    for path, extra_headers, label in (
        ("/api/application/projects", None, "projects_blocked"),
        ("/api/application/runs/app-6706a75ba00f0277/evidence", None, "run_evidence_blocked"),
        ("/api/application/projects", {"Authorization": "Bearer invalid-operator-token"}, "operator_bypass_blocked"),
    ):
        status, _, response = get(path, extra_headers)
        body = json.loads(response)
        assert status == 401 and body.get("error", {}).get("code") == "sign_in_required", (label, status, body)
        observations.append({"check": label, "status": status})

    return {"status": "pass", "origin": origin.rstrip("/"), "tls_expires_at": expires.isoformat(),
            "tls_seconds_remaining": remaining, "zero_inference": True,
            "deployed_revision": deployed_revision,
            "observations": observations}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://80.240.30.92")
    parser.add_argument("--output", type=Path, default=Path("/tmp/refit-platform-smoke.json"))
    parser.add_argument("--expected-revision")
    args = parser.parse_args()
    try:
        result = check(args.url, args.expected_revision)
    except Exception as exc:
        result = {"status": "fail", "origin": args.url, "zero_inference": True,
                  "error": f"{type(exc).__name__}: {exc}"[:400]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
