"""Exercise the original TypeScript agent and gVisor transport with a test broker."""
import argparse
import json
from pathlib import Path
import re

from .application_import import source_snapshot
from .application_run import MODELS, configuration, run_migration


def original_turn(messages, options):
    assert "response_format" not in options, "Tool turns must not use provider schema constraints"
    assert messages[-1]["role"] == "system" and "For the final response only" in messages[-1]["content"]
    return messages[-2]


class TestBroker:
    requests = 0
    max_requests = 16

    def complete(self, model, messages, tools, **options):
        self.requests += 1
        assert tools and any(t["function"]["name"] == "read_file" for t in tools)
        last = original_turn(messages, options)
        if last["role"] == "tool":
            result = last["content"]
            try:
                result = json.loads(result)
            except ValueError:
                pass
            return {"role": "assistant", "content": json.dumps({"summary": result, "written": []})}
        path = re.search(r"(order|invoice|receipt)\.txt", last["content"]).group(0)
        return {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_" + str(self.requests), "type": "function",
             "function": {"name": "read_file", "arguments": json.dumps({"path": path})}}]}


class ExtendedReadBroker(TestBroker):
    """Keep the unmodified upstream AI SDK agent active until its fifth step.

    The old four-completion Refit cap killed this valid original loop before
    the fifth, final structured-output response could arrive. This test
    simulates provider behavior, not successful real-model compatibility.
    """
    max_requests = 48

    def complete(self, model, messages, tools, **options):
        self.requests += 1
        assert tools and any(t["function"]["name"] == "read_file" for t in tools)
        last = original_turn(messages, options)
        user_prompt = next(m["content"] for m in messages if m["role"] == "user")
        path = re.search(r"(order|invoice|receipt)\.txt", user_prompt).group(0)
        read_count = sum(m.get("role") == "tool" for m in messages)
        if read_count >= 4:
            result = last["content"]
            try:
                result = json.loads(result)
            except ValueError:
                pass
            return {"role": "assistant", "content": json.dumps({"summary": result, "written": []})}
        return {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_" + str(self.requests), "type": "function",
             "function": {"name": "read_file", "arguments": json.dumps({"path": path})}}]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("setup", type=Path)
    parser.add_argument("--image", default="refit-application")
    parser.add_argument("--extended-read-loop", action="store_true",
                        help="Test four identical reads followed by a valid fifth response")
    args = parser.parse_args()
    snapshot = source_snapshot(args.archive.read_bytes())
    supplied = json.loads(args.setup.read_text())
    for case in supplied["cases"]:
        filename = re.search(r"(order|invoice|receipt)\.txt", case["prompt"]).group(0)
        case["state"] = [
            {"path": f"records/{filename}", "op": "unchanged"},
            {"path": "records/unexpected.txt", "op": "absent"},
        ]
    setup = configuration(snapshot, supplied)
    events = []
    broker = ExtendedReadBroker() if args.extended_read_loop else TestBroker()
    result = run_migration(snapshot, setup, *MODELS, args.image, broker,
                           lambda name, value: events.append((name, value)), lambda: False)
    cases = [value for name, value in events if name == "case_completed"]
    cleanups = [value["receipt"]["verified"] for name, value in events if name == "sandbox_cleanup"]
    print(json.dumps({"mode": "zero_inference_transport_test", "status": result["status"],
                      "cases": [{k: c[k] for k in ("case", "passed", "error", "verdict")} for c in cases],
                      "cleanups": cleanups, "test_broker_requests": broker.requests}))
    assert result["export"] and len(cleanups) == 7 and all(cleanups)
    assert all(case["verdict"]["required_tool_observed"] for case in cases)
    assert all(case["verdict"]["state_checks_passed"] for case in cases)
    if args.extended_read_loop:
        assert broker.requests == 35
        warnings = [value for name, value in events if name == "repeated_read_only_tool_calls"]
        assert len(warnings) == 7 and all(row["consecutive"] == 4 for row in warnings)
        assert all(row["signature_sha256"] for row in warnings)
    else:
        assert broker.requests == 14


if __name__ == "__main__":
    main()
