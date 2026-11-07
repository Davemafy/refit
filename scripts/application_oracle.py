"""Trusted, framework-independent outcome checks for imported applications.

Expected outcomes never enter an imported agent's gVisor container.
This deliberately excludes arbitrary Python/JavaScript evaluator code.
"""
import hashlib
import json
import re

REQUIRED = {"name", "split", "prompt"}
OPTIONAL = {"stdout", "json_contains", "tool", "tool_result", "tool_arguments", "forbidden_tools", "state"}
TOOL_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,99}\Z")


def validate_case(case):
    if not isinstance(case, dict) or not REQUIRED <= case.keys() or not case.keys() <= REQUIRED | OPTIONAL:
        raise ValueError("Each case needs a name, split, prompt and supported outcome checks.")
    for key in REQUIRED:
        value = case[key]
        if not isinstance(value, str) or not 1 <= len(value) <= 4096 or "\x00" in value:
            raise ValueError(f"Invalid {key} in evaluation case.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", case["name"]):
        raise ValueError("Invalid evaluation case name.")
    if case["split"] not in {"train", "validation", "holdout"}:
        raise ValueError("Invalid evaluation split.")
    if not ({"stdout", "json_contains", "tool", "state"} & case.keys()):
        raise ValueError("Supply a response, tool, or application state check.")
    if {"tool_result", "tool_arguments"} & case.keys() and "tool" not in case:
        raise ValueError("Tool arguments or results require a named tool.")
    for field in ("stdout", "tool_result"):
        if field in case and (not isinstance(case[field], str) or not 1 <= len(case[field]) <= 4096 or "\x00" in case[field]):
            raise ValueError(f"Invalid {field} expectation.")
    if "tool" in case and (not isinstance(case["tool"], str) or not TOOL_RE.fullmatch(case["tool"])):
        raise ValueError("Invalid required tool name.")
    forbidden = case.get("forbidden_tools", [])
    if (not isinstance(forbidden, list) or len(forbidden) > 16 or
            any(not isinstance(tool, str) or not TOOL_RE.fullmatch(tool) for tool in forbidden) or
            len(forbidden) != len(set(forbidden))):
        raise ValueError("Invalid forbidden tool list.")
    if "tool" in case and case["tool"] in forbidden:
        raise ValueError("The same tool cannot be required and forbidden.")
    for field in ("json_contains", "tool_arguments"):
        if field not in case:
            continue
        expected = case[field]
        if not isinstance(expected, dict) or not expected:
            raise ValueError(f"{field} needs a nonempty object of expected fields.")
        try:
            payload = json.dumps(expected, allow_nan=False, separators=(",", ":"))
        except (TypeError, ValueError, RecursionError):
            raise ValueError(f"{field} must be serializable.") from None
        if len(payload) > 4096:
            raise ValueError(f"{field} exceeds 4096 bytes.")

    if "state" in case:
        checks = case["state"]
        if not isinstance(checks, list) or not 1 <= len(checks) <= 8:
            raise ValueError("Provide between one and eight application state checks.")
        for check in checks:
            if not isinstance(check, dict) or not {"path", "op"} <= check.keys():
                raise ValueError("Each state check needs a path and operation.")
            path, operation = check["path"], check["op"]
            if (not isinstance(path, str) or not 1 <= len(path) <= 180
                    or not all(re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", part) for part in path.split("/"))):
                raise ValueError("State checks require a safe relative path under the application directory.")
            if operation not in ("exists", "absent", "changed", "unchanged", "json_contains"):
                raise ValueError("Unsupported state check operation.")
            if set(check) != ({"path", "op", "expected"} if operation == "json_contains" else {"path", "op"}):
                raise ValueError("Only json_contains accepts an expected value.")
            if operation == "json_contains":
                try:
                    value = json.dumps(check["expected"], allow_nan=False)
                except (TypeError, ValueError, RecursionError):
                    raise ValueError("State expectations must be valid JSON.") from None
                if not isinstance(check["expected"], dict) or not check["expected"] or len(value.encode()) > 4096:
                    raise ValueError("State JSON checks require a nonempty object of up to 4 KiB.")



def _contains(actual, expected):
    if isinstance(expected, dict):
        return (isinstance(actual, dict)
                and all(key in actual and _contains(actual[key], value) for key, value in expected.items()))
    # List and scalar equality is intentional; order and multiplicity matter.
    return type(actual) is type(expected) and actual == expected


def matches_tool_arguments(case, raw):
    if "tool_arguments" not in case:
        return True
    try:
        return _contains(json.loads(raw), case["tool_arguments"])
    except (ValueError, TypeError, RecursionError):
        return False


def evaluate_state(checks, observations):
    evidence = []
    for check in checks:
        path, operation = check["path"], check["op"]
        observation = observations.get(path, {})
        before = observation.get("before", {})
        after = observation.get("after", {})
        passed = False
        if after.get("status") in {"file", "missing"}:
            if operation in {"exists", "absent"}:
                passed = after["status"] == ("file" if operation == "exists" else "missing")
            elif operation in {"changed", "unchanged"} and before.get("status") in {"file", "missing"}:
                passed = (before == after) == (operation == "unchanged")
            elif operation == "json_contains" and after["status"] == "file":
                try:
                    passed = _contains(json.loads(after["text"]), check["expected"])
                except (KeyError, ValueError, TypeError, RecursionError):
                    pass
        def receipt(item):
            status = item.get("status", "unobserved")
            text = item.get("text")
            return {"status": status, **({"sha256": hashlib.sha256(text.encode()).hexdigest()}
                                         if isinstance(text, str) else {})}
        evidence.append({"path": path, "op": operation, "passed": passed,
                         "before": receipt(before), "after": receipt(after)})
    return evidence


def evaluate(case, stdout, tools_called, tool_result_observed, *, tool_arguments_observed=False):
    """Evaluate original runtime output and broker-observed tool calls on the trusted host."""
    stdout_matches = None
    if "stdout" in case:
        stdout_matches = stdout.strip() == case["stdout"].strip()
    json_matches = None
    if "json_contains" in case:
        try:
            json_matches = _contains(json.loads(stdout), case["json_contains"])
        except (ValueError, TypeError, RecursionError):
            json_matches = False
    required_tool_called = None
    if "tool" in case:
        required_tool_called = case["tool"] in tools_called
    required_tool_observed = None
    if "tool_result" in case:
        required_tool_observed = bool(tool_result_observed)
    forbidden_tools_absent = not set(case.get("forbidden_tools", [])).intersection(tools_called)
    tool_arguments_match = tool_arguments_observed if "tool_arguments" in case else None
    checks = (stdout_matches, json_matches, required_tool_called, required_tool_observed,
              forbidden_tools_absent, tool_arguments_match)
    return {"passed": all(x is not False for x in checks),
            "stdout_matches": stdout_matches,
            "json_matches": json_matches,
            "required_tool_called": required_tool_called,
            "required_tool_observed": required_tool_observed,
            "forbidden_tools_absent": forbidden_tools_absent,
            "tool_arguments_match": tool_arguments_match}
