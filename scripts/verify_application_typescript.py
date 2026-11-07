"""Exercise the original TypeScript agent and gVisor transport with a test broker."""
import argparse
import json
from pathlib import Path
import re

from .application_import import source_snapshot
from .application_run import MODELS, configuration, run_migration


class TestBroker:
    requests = 0
    max_requests = 16

    def complete(self, model, messages, tools, **options):
        self.requests += 1
        assert tools and any(t["function"]["name"] == "read_file" for t in tools)
        if messages[-1]["role"] == "tool":
            result = messages[-1]["content"]
            try:
                result = json.loads(result)
            except ValueError:
                pass
            return {"role": "assistant", "content": json.dumps({"summary": result, "written": []})}
        path = re.search(r"(order|invoice|receipt)\.txt", messages[-1]["content"]).group(0)
        return {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_" + str(self.requests), "type": "function",
             "function": {"name": "read_file", "arguments": json.dumps({"path": path})}}]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("setup", type=Path)
    parser.add_argument("--image", default="refit-application")
    args = parser.parse_args()
    snapshot = source_snapshot(args.archive.read_bytes())
    setup = configuration(snapshot, json.loads(args.setup.read_text()))
    events = []
    broker = TestBroker()
    result = run_migration(snapshot, setup, *MODELS, args.image, broker,
                           lambda name, value: events.append((name, value)), lambda: False)
    cases = [value for name, value in events if name == "case_completed"]
    cleanups = [value["receipt"]["verified"] for name, value in events if name == "sandbox_cleanup"]
    print(json.dumps({"mode": "zero_inference_transport_test", "status": result["status"],
                      "cases": [{k: c[k] for k in ("case", "passed", "error", "verdict")} for c in cases],
                      "cleanups": cleanups, "test_broker_requests": broker.requests}))
    assert result["export"] and len(cleanups) == 7 and all(cleanups)
    assert all(case["verdict"]["required_tool_observed"] for case in cases)
    assert broker.requests == 14


if __name__ == "__main__":
    main()
