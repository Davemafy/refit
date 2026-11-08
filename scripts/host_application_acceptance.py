"""Zero-inference Vultr-host acceptance of the REAL imported application path.

Uses the same source snapshot, orchestration, Docker broker, gVisor agent worker,
case evaluation, holdout, and fresh exported configuration as customer migrations.
Only the model's remote reply is replaced by a deterministic EchoBroker.
"""
from __future__ import annotations
import argparse
import base64
import json
from scripts.application_import import make_snapshot
from scripts.application_run import MODELS, configuration, run_migration


AGENT = b"""
import json, os, sys
from urllib.request import Request, urlopen
req = Request(os.environ["OPENAI_BASE_URL"] + "/chat/completions", data=json.dumps({
    "model": os.environ["OPENAI_MODEL"],
    "messages": [{"role": "user", "content": sys.argv[1]}]
}).encode(), headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]})
with urlopen(req, timeout=40) as response:
    print(json.load(response)["choices"][0]["message"]["content"])
"""


class EchoBroker:
    max_requests = 8

    def __init__(self):
        self.requests = 0

    def complete(self, model, messages, tools=None, **options):
        self.requests += 1
        return {"role": "assistant", "content": messages[-1]["content"]}


def accept(image: str) -> dict:
    if not image.startswith("sha256:") or len(image) != 71:
        raise ValueError("Application image must be an immutable content digest")
    snapshot = make_snapshot({"agent.py": base64.b64encode(AGENT).decode()},
                             None, None, "", [])
    cases = [
        {"name": name, "split": name, "prompt": name, "stdout": name}
        for name in ("train", "validation", "holdout")
    ]
    setup = configuration(snapshot, {
        "module": "agent", "args": ["{prompt}"], "cases": cases,
    })
    broker = EchoBroker()
    events = []
    result = run_migration(
        snapshot, setup, *MODELS, image, broker,
        lambda event, details: events.append((event, details)),
        lambda: False,
    )
    cleanup = [
        detail["receipt"] for event, detail in events
        if event == "sandbox_cleanup"
    ]
    evaluated = [
        detail for event, detail in events if event == "case_completed"
    ]
    if not (
        result["status"] == "compatible_on_sample"
        and result.get("export") is not None
        and result["export"]["model"] == MODELS[1]
        and all(case["passed"] for case in result["verification"])
        and len(evaluated) == 7
        and all(case["passed"] and case["runtime"] == "runsc" for case in evaluated)
        and len(cleanup) == 7
        and all(receipt["verified"] for receipt in cleanup)
        and broker.requests == 7
    ):
        raise AssertionError(json.dumps({
            "status": result["status"],
            "export_present": result.get("export") is not None,
            "cases": [
                {"name": item["case"], "passed": item["passed"],
                 "error": item["error"], "runtime": item.get("runtime"),
                 "transport_exit": item.get("worker_transport_exit_code"),
                 "application_exit": item.get("exit_code"),
                 "oom_killed": item.get("oom_killed")}
                for item in evaluated
            ],
            "cleanup_count": len(cleanup),
            "cleanup_verified": all(x["verified"] for x in cleanup),
            "requests": broker.requests,
        }))
    return {
        "verified": True, "actual_gvisor_workers": len(evaluated),
        "worker_cleanup_receipts": len(cleanup),
        "broker_responses": broker.requests,
        "source_model": MODELS[0], "target_model": MODELS[1],
        "verified_export": True,
        "provider": "deterministic local EchoBroker, NO PAID INFERENCE",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    print(json.dumps(accept(args.image), sort_keys=True), flush=True)
