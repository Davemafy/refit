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


def assert_release(health: dict, expected_revision: str) -> dict:
    if not re.fullmatch(r"[a-f0-9]{40}", expected_revision):
        raise ValueError("Expected revision must be a full 40-character lowercase Git SHA")
    actual = health.get("revision")
    assert isinstance(actual, dict), "Deployed health response omits startup revision"
    assert actual.get("commit") == expected_revision, (
        "Deployed application is not the expected commit"
    )
    assert actual.get("tracked_files_clean") is True, (
        "Deployed checkout is dirty or its cleanliness cannot be confirmed"
    )
    return {"commit": actual["commit"], "tracked_files_clean": True}


def assert_live_rejection(run: dict, artifact_status: int, artifact: dict,
                          events: dict, expected_revision: str | None) -> dict:
    assert run.get("mode") == "live", "Run was not executed by the live operator"
    assert run.get("status") == "repair_rejected_validation", (
        "Expected the real rejected repair, not a passing or simulated run"
    )
    report = run.get("report") or {}
    assert report.get("status") == run["status"], "Run verdict differs from report"
    assert run.get("patch") is None, "A rejected migration must not contain an exportable patch"
    assert artifact_status == 404 and artifact.get("error", {}).get("code") == "artifact_not_found", (
        "Rejected migration unexpectedly exposes a downloadable patch"
    )
    boundary = report.get("execution_boundary") or {}
    assert boundary.get("runtime") == "runsc", "Live report does not prove gVisor use"
    assert boundary.get("business_tools_isolated") is True, "Business tools were not isolated"
    assert boundary.get("all_containers_removed") is True, "Worker cleanup is not confirmed"
    worker_runs = boundary.get("worker_runs")
    assert type(worker_runs) is int and worker_runs > 0, "No completed isolated worker runs"
    receipts = boundary.get("cases")
    assert isinstance(receipts, list) and len(receipts) == worker_runs, (
        "Missing or incomplete per-worker containment receipts"
    )
    containers = set()
    daemons = set()
    for receipt in receipts:
        assert isinstance(receipt, dict), "Malformed containment receipt"
        assert receipt.get("runtime") == "runsc", "Worker used a different runtime"
        assert receipt.get("network") == "none", "Worker network restriction not recorded"
        assert receipt.get("read_only_root") is True, "Worker root filesystem was not read-only"
        assert receipt.get("container_absent") is True, "A worker may remain on the host"
        assert receipt.get("process_cleanup_error") is None, "Worker process cleanup failed"
        cleanup = receipt.get("cleanup_evidence") or {}
        assert cleanup.get("verified") is True and cleanup.get("reason") == "verified_absent", (
            "Worker cleanup lacks an explicit verified-absence receipt"
        )
        name = cleanup.get("container_name")
        daemon = cleanup.get("daemon_id")
        assert isinstance(name, str) and name.startswith("refit-"), (
            "Cleanup receipt is not for a Refit-owned container"
        )
        assert isinstance(daemon, str) and daemon, "Cleanup receipt lacks daemon identity"
        assert (cleanup.get("inspection") or {}).get("returncode") == 1, (
            "Missing-container inspection evidence is incomplete"
        )
        assert (cleanup.get("daemon_health") or {}).get("returncode") == 0, (
            "Docker daemon health was not independently recorded"
        )
        assert name not in containers, "Duplicate container cleanup receipt"
        containers.add(name)
        daemons.add(daemon)
    assert len(daemons) == 1, "Containment receipts came from multiple Docker daemons"
    assert run.get("execution_isolation") == "docker_tool_sandbox_verified_cleanup", (
        "Published run is missing its isolation verdict"
    )
    if expected_revision is not None:
        identity = run.get("engine_revision") or {}
        assert identity.get("commit") == expected_revision, (
            "Published run came from a different deployed revision"
        )
    assert events.get("terminal") is True and len(events.get("events", [])) >= 2, (
        "Published run has no complete event history"
    )
    assert events.get("run_id") == run.get("id"), "Event history refers to a different run"
    return {"id": run["id"], "status": run["status"], "runtime": "runsc",
            "worker_runs": worker_runs, "cleanup_verified": True,
            "patch_withheld": True}


def verify(base: str, expected_revision: str | None = None,
           require_live_rejection: bool = False) -> dict:
    validate_url(base)
    if expected_revision is not None and not re.fullmatch(r"[a-f0-9]{40}", expected_revision):
        raise ValueError("Expected revision must be a full 40-character lowercase Git SHA")
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
                # A real gVisor migration can include dozens of worker
                # receipts. A fixed 150 KB read silently truncated valid JSON.
                # Read the complete bounded response before decoding it.
                body = response.read(32 * 1024 * 1024 + 1)
                if len(body) > 32 * 1024 * 1024:
                    raise ValueError("Public API response exceeds 32 MiB acceptance limit")
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
    release = assert_release(health, expected_revision) if expected_revision else None
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
    # Inspect the existing published rejection, never start a new live task.
    live_rejection = None
    if require_live_rejection:
        candidate = next((item for item in data["runs"]
                          if item.get("mode") == "live" and
                          item.get("status") == "repair_rejected_validation"), None)
        assert candidate is not None, "No published rejected live migration found"
        live_id = candidate["id"]
        status, detail = request("/api/runs/" + live_id)
        assert status == 200
        artifact_status, artifact = request("/api/runs/" + live_id + "/artifact")
        events_status, live_events = request("/api/runs/" + live_id + "/events")
        assert events_status == 200
        live_rejection = assert_live_rejection(
            detail, artifact_status, artifact, live_events, expected_revision
        )
    # A public smoke test must NEVER trigger paid inference or code execution.
    return {
        "status": "pass",
        "origin": base,
        "release": release,
        "live_rejection": live_rejection,
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
    parser.add_argument("--expected-revision", help="Require exact deployed 40-character Git SHA and clean checkout")
    parser.add_argument("--require-live-rejection", action="store_true",
                        help="Require published gVisor rejection, cleanup and withheld patch")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = verify(args.url, expected_revision=args.expected_revision,
                    require_live_rejection=args.require_live_rejection)
    content = json.dumps(result, indent=2)
    print(content)
    if args.output:
        from pathlib import Path
        Path(args.output).write_text(content + "\n", encoding="utf8")


if __name__ == "__main__":
    main()
