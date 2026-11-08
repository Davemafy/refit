"""External, zero-inference anonymous acceptance for Refit's branded domain."""
from __future__ import annotations

import argparse
from http.cookiejar import CookieJar
import json
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener


def check(origin, expected_revision=None):
    origin = origin.rstrip("/")
    browser = build_opener(HTTPCookieProcessor(CookieJar()))

    def request(path, body=None):
        headers = {"Accept": "application/json"}
        if body is not None:
            headers.update({"Origin": origin, "Content-Type": "application/json"})
        operation = Request(origin + path, headers=headers,
                            data=json.dumps(body).encode() if body is not None else None)
        try:
            with browser.open(operation, timeout=15) as response:
                return response.status, response.read()
        except HTTPError as exc:
            return exc.code, exc.read()

    code, html = request("/app")
    assert code == 200 and b"Refit" in html, "Branded workspace did not load"
    code, body = request("/api/application/release")
    release = json.loads(body)
    assert code == 200 and isinstance(release.get("revision"), str), release
    if expected_revision:
        assert release["revision"] == expected_revision, "Production is not at the requested commit"

    code, body = request("/api/application/session")
    guest = json.loads(body)
    assert code == 200 and guest.get("username") is None, guest

    code, body = request("/api/application/guest-session", {})
    session = json.loads(body)
    assert code == 201 and session.get("guest") is True, (code, session)
    code, body = request("/api/application/projects")
    projects = json.loads(body)
    assert code == 200 and projects.get("projects") == [], (code, projects)
    code, body = request("/api/application")
    policy = json.loads(body)
    assert code == 200 and len(policy.get("models", [])) >= 2, (code, policy)

    # A deliberately invalid request must fail before any paid broker calls.
    code, body = request("/api/application/runs", {
        "import_id": "import-invalid", "source": "not-a-model",
        "target": "also-not-a-model", "budget": 7, "authorize": True,
    })
    rejected = json.loads(body)
    assert code == 422 and rejected.get("error", {}).get("code") == "invalid_models", (code, rejected)
    return {
        "origin": origin, "revision": release["revision"],
        "anonymous_workspace": True, "anonymous_projects_private": True,
        "invalid_model_rejected_without_inference": True,
        "remaining_global_requests": policy.get("global_remaining_today"),
        "available_requests_in_visitor_workspace": policy.get("max_requests"),
        "live_migration_started": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="https://refit.davemafy.xyz")
    parser.add_argument("--expected-revision")
    args = parser.parse_args()
    print(json.dumps(check(args.origin, args.expected_revision), indent=2))
