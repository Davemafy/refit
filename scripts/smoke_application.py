"""Exercise the deployed operator HTTP boundary with a single explicit budget."""
import argparse
import base64
import io
import zipfile
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPO = "simonw/llm"
REVISION = "b9786a2daa44a995ff7719c655c5338bf685d551"
SOURCE = "deepseek-v4.1-flash-1017"
TARGET = "glm-5.2"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--github", action="store_true", help="Opt into live GitHub API; CI defaults to a local ZIP.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    base = "http://127.0.0.1:8098"
    token = os.environ["REFIT_APPLICATION_TOKEN"]

    def request(path, data=None, *, authenticated=True):
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["Authorization"] = "Bearer " + token
        raw = json.dumps(data).encode() if data is not None else None
        with urlopen(Request(base + path, data=raw, headers=headers), timeout=30) as response:
            return response.read()

    def api(path, data=None):
        try:
            return json.loads(request("/api/application" + path, data))
        except HTTPError as error:
            # CI must show the actual bounded server rejection rather than a
            # context-free HTTP 422. This response contains no account secret.
            reason = error.read(1000).decode("utf8", errors="replace")
            raise RuntimeError(f"Refit API HTTP {error.code} at {path}: {reason}") from error

    assert b"Bring your agent" in request("/bring", authenticated=False)
    try:
        request("/api/application", authenticated=False)
    except HTTPError as error:
        assert error.code == 401
    else:
        raise AssertionError("Unauthenticated access unexpectedly accepted")
    assert SOURCE in api("")["models"]
    # Zero-inference CI must not depend on the availability of GitHub.
    # The explicit --github / --execute path retains pinned remote source tests.
    if args.github or args.execute:
        imported = api("/imports", {"method": "github", "repository": REPO, "revision": REVISION})
        assert imported["discovery"]["preset"] == "llm-0.37.1"
    else:
        fixture = b"import os\nOPENAI_BASE_URL = os.environ.get('OPENAI_BASE_URL')\nOPENAI_MODEL = os.environ.get('OPENAI_MODEL')\n"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zipped:
            zipped.writestr("agent.py", fixture)
        imported = api("/imports", {
            "method": "zip", "archive": base64.b64encode(buffer.getvalue()).decode("ascii")})
        assert imported["file_count"] == 1
        assert imported["file_paths"] == ["agent.py"]
        assert imported["discovery"]["runtime"] == "python"
    print(json.dumps(imported), flush=True)
    if not args.execute:
        return
    run = api("/runs", {"import_id": imported["id"], "source": SOURCE, "target": TARGET,
                         "budget": 24, "authorize": True})
    route = "/runs/" + run["id"]
    print(json.dumps({"run_id": run["id"]}), flush=True)
    cursor = 0
    while run["status"] in {"running", "cancelling"}:
        raw = request("/api/application" + route + f"/events?after={cursor}").decode()
        for line in raw.splitlines():
            if line.startswith("data: "):
                event = json.loads(line[6:])
                cursor = event["seq"]
                if event["type"] in {"phase_completed", "terminal"}:
                    print(json.dumps(event), flush=True)
        run = api(route)
    evidence = api(route + "/evidence")
    if args.output:
        args.output.write_text(json.dumps(evidence, indent=2))
    print(json.dumps(run), flush=True)
    assert run["export_available"], run["status"]
    assert api(route + "/artifact")["model"] == TARGET
    assert all(c["passed"] and c["verdict"]["required_tool_observed"] for c in evidence["run"]["verification"])
    receipts = [e["details"]["receipt"] for e in evidence["events"] if e["type"] == "sandbox_cleanup"]
    assert len(receipts) >= 7 and all(r["verified"] for r in receipts)
    assert run["model_requests"] <= 24


if __name__ == "__main__":
    main()
