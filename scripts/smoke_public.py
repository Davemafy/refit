"""One-command, zero-inference public Refit end-to-end smoke test."""
from __future__ import annotations

import argparse
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit


def validate_url(base: str):
    parsed = urlsplit(base)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Specify an explicit http(s) Refit URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("No credentials, queries, or fragments in base URL")
    if parsed.path.strip("/"):
        raise ValueError("Specify the origin URL, e.g. http://IP")


def verify(base: str) -> dict:
    validate_url(base)
    base = base.rstrip("/")
    observations = []

    def request(path: str, data: dict | None = None):
        args = {"headers": {"Accept": "application/json"}}
        if data is not None:
            args["data"] = json.dumps(data).encode("utf8")
            args["headers"]["Content-Type"] = "application/json"
        req = Request(base + path, **args)
        try:
            with urlopen(req, timeout=10) as response:
                body = response.read(150_000)
                observations.append({
                    "route": path, "status": response.status,
                    "content_type": response.headers.get("Content-Type", ""),
                })
                if "application/json" in response.headers.get("Content-Type", ""):
                    return response.status, json.loads(body)
                return response.status, body.decode("utf8")
        except HTTPError as error:
            body = error.read(100_000)
            observations.append({"route": path, "status": error.code,
                                 "content_type": error.headers.get("Content-Type", "")})
            return error.code, json.loads(body)

    status, html = request("/")
    assert status == 200 and "Change the model." in html
    assert 'id="runList"' in html and 'id="diagnoseButton"' in html
    status, health = request("/api/health")
    assert status == 200 and health["status"] == "ok"
    status, caps = request("/api/capabilities")
    assert status == 200 and caps["contract_version"] == "v1"
    status, data = request("/api/runs")
    assert status == 200 and len(data["runs"]) >= 2
    refund_id = next(x["id"] for x in data["runs"]
                     if x["domain"] == "refund" and x["mode"] == "recorded")
    deployment_id = next(x["id"] for x in data["runs"]
                         if x["domain"] == "deployment" and x["mode"] == "recorded")
    status, refund = request("/api/runs/" + refund_id)
    assert status == 200 and refund["status"] == "verified_adaptation"
    assert refund["report"]["source_training"]["passed"] == 8
    assert refund["report"]["target_training"]["passed"] == 6
    assert refund["report"]["repaired_holdout"]["passed"] == 8
    status, artifact = request("/api/runs/" + refund_id + "/artifact")
    assert status == 200 and artifact["format"] == "refit.compatibility.v1"
    status, deployment = request("/api/runs/" + deployment_id)
    assert status == 200 and deployment["status"] == "compatible_on_sample"
    assert deployment["patch"] is None
    status, intent = request("/api/interpret", {
        "text": "Move our refund agent from DeepSeek to Muse."
    })
    assert status == 200 and intent["ready_for_review"] is True
    assert intent["target_model"] == "muse-glimmer-30b"
    status, events = request("/api/runs/" + refund_id + "/events")
    assert status == 200 and events["terminal"] is True
    # A public smoke test must NEVER trigger paid inference or code execution.
    return {
        "status": "pass",
        "origin": base,
        "records": {
            "refund": {"id": refund_id, "source_passed": 8,
                       "target_passed": 6, "repaired_holdout_passed": 8},
            "deployment": {"id": deployment_id, "status": "compatible_on_sample"},
        },
        "live_runs_enabled": bool(caps.get("live_runs_enabled")),
        "routes_checked": observations,
        "no_paid_actions_triggered": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = verify(args.url)
    content = json.dumps(result, indent=2)
    print(content)
    if args.output:
        from pathlib import Path
        Path(args.output).write_text(content + "\n", encoding="utf8")


if __name__ == "__main__":
    main()
