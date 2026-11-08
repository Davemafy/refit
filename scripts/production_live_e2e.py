"""Opt-in production E2E: real signed-in user, live Vultr models, gVisor, export and diagnostics.

Never runs on ordinary pushes. One explicitly authorized check spends up to
9 migration inference calls plus one generated-code diagnostic call.
No credentials are emitted or stored as artifacts.
"""
import argparse
import base64
import io
import json
import os
import secrets
import time
import zipfile

from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor

AGENT = '''import json,os,sys
from urllib.request import Request,urlopen
req=Request(os.environ["OPENAI_BASE_URL"]+"/chat/completions",
 data=json.dumps({"model":os.environ["OPENAI_MODEL"],
  "messages":[{"role":"system","content":"Output only the single word requested by the user. No other text."},
              {"role":"user","content":sys.argv[1]}],
  "max_tokens":32}).encode(),
 headers={"Content-Type":"application/json",
          "Authorization":"Bearer "+os.environ["OPENAI_API_KEY"]})
with urlopen(req,timeout=65) as response:
 text=json.load(response)["choices"][0]["message"]["content"]
print(text.strip().strip('"').upper())'''


def run(origin, revision):
    session = build_opener(HTTPCookieProcessor(CookieJar()))
    base = origin + "/api/application"

    def call(method, endpoint, value=None):
        encoded = None if value is None else json.dumps(value, separators=(",", ":")).encode()
        request = Request(
            base + endpoint, data=encoded, method=method,
            headers={"Origin": origin, "Content-Type": "application/json",
                     "Accept": "application/json"})
        try:
            with session.open(request, timeout=30) as response:
                if response.status not in (200, 201, 202):
                    raise AssertionError(f"{method} {endpoint}: HTTP {response.status}")
                return json.load(response)
        except HTTPError as error:
            try:
                reason = json.load(error).get("error", {}).get("code", "unknown")
            except (ValueError, TypeError):
                reason = "unparsed"
            raise AssertionError(f"{method} {endpoint}: HTTP {error.code} {reason}") from None

    assert call("GET", "/release")["revision"] == revision
    review_token = os.environ.get("REFIT_REVIEW_TOKEN")
    if review_token:
        assert call("POST", "/review-session", {"code": review_token})["signed_in"]
        assert call("GET", "/session")["username"] == "Review workspace"
    else:
        user = "qa-" + secrets.token_hex(6)
        passwd = secrets.token_urlsafe(24)
        assert call("POST", "/register", {"username": user, "password": passwd})["signed_in"]
        assert call("GET", "/session")["username"] == user
    capacity = call("GET", "")
    assert {"glm-5.2", "deepseek-v4.1-flash-1017"} <= set(capacity["models"])
    assert capacity["max_requests"] >= 9, (
        "No authorized capacity remains for one complete acceptance; "
        "no run was submitted or inference billed."
    )
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("agent.py", AGENT)
    imp = call("POST", "/imports", {
        "method": "zip", "archive": base64.b64encode(archive.getvalue()).decode()})
    assert "agent.py" in imp["file_paths"]
    cases = [
        {"name":"train_blue","split":"train",
         "prompt":"Reply with only BLUE.", "stdout":"BLUE"},
        {"name":"validate_green","split":"validation",
         "prompt":"Reply with only GREEN.", "stdout":"GREEN"},
        {"name":"holdout_red","split":"holdout",
         "prompt":"Reply with only RED.", "stdout":"RED"},
    ]
    created = call("POST", "/runs", {
        "import_id": imp["id"],
        "source":"deepseek-v4.1-flash-1017", "target":"glm-5.2",
        "budget":9, "authorize":True,
        "setup":{"format":"refit.agent.v1","module":"agent",
                 "args":["{prompt}"],"cases":cases}})
    rid = created["id"]
    print("PRODUCTION MIGRATION", rid, flush=True)

    def poll(field):
        deadline = time.monotonic()+220
        while time.monotonic() < deadline:
            run = call("GET", "/runs/"+rid)
            value = run["status"] if field == "status" else (
                run.get("diagnostic") or {}).get("status")
            if value and value not in ("queued","running","cancelling"):
                return run
            time.sleep(2)
        raise AssertionError("Production migration timed out")

    result = poll("status")
    evidence = call("GET", "/runs/"+rid+"/evidence")
    completed = [e["details"] for e in evidence["events"] if e["type"]=="case_completed"]
    cleanup = [e["details"]["receipt"] for e in evidence["events"]
               if e["type"]=="sandbox_cleanup"]
    if result["status"] not in ("compatible_on_sample","verified_adaptation"):
        print(json.dumps({"run":rid,"status":result["status"],
                          "model_requests":result["model_requests"],
                          "case_outcomes":[{"name":x["case"],"error":x["error"],
                                            "transport":x.get("worker_transport_exit_code")}
                                           for x in completed]},sort_keys=True),flush=True)
        raise AssertionError("Live migration did not verify")
    assert result["export_available"] is True
    assert len(completed)>=7 and all(e["passed"] for e in completed)
    assert len(cleanup)>=7 and all(e["verified"] for e in cleanup)
    export=call("GET", "/runs/"+rid+"/artifact")
    assert export["model"]=="glm-5.2"
    requested=call("POST", "/runs/"+rid+"/diagnose", {})
    assert requested["status"]=="running"
    checked=poll("diagnostic")["diagnostic"]
    assert checked["status"]=="verified", {
        "diagnostic_status":checked["status"],
        "error":checked.get("error") or checked.get("validation_error")}
    assert checked["verified"] is True
    assert "newly_failed_cases" in checked["observed"]
    assert "recovered_cases" in checked["observed"]
    assert checked["expected"]==checked["observed"]
    assert checked["cross_check"]["expected"]==checked["cross_check"]["observed"]
    for worker in (checked["sandbox"], checked["cross_check"]["sandbox"]):
        assert worker["runtime"]=="runsc"
        assert worker["status"]=="passed"
        assert worker["container_created"] and worker["container_removed_verified"]
        assert worker["ledger_valid"]
    summary={"verified":True,"revision":revision,"run_id":rid,
             "run_status":result["status"],
             "inference_migration":result["model_requests"],
             "inference_diagnostic":checked["model_requests"],
             "case_evaluations":len(completed),
             "worker_cleanup":len(cleanup),
             "verified_export":True,"sandbox_runtime":"runsc",
             "model_generated_diagnostic":True,"unseen_oracle_matched":True}
    print("LIVE PRODUCTION END-TO-END",json.dumps(summary,sort_keys=True),flush=True)
    return summary


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--origin",default="https://80.240.30.92")
    p.add_argument("--expected-revision",required=True)
    args=p.parse_args()
    run(args.origin,args.expected_revision)
