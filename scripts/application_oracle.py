"""Trusted, framework-independent outcome checks for imported applications.

Expected outcomes never enter an imported agent's gVisor container.
This deliberately excludes arbitrary Python/JavaScript evaluator code.
"""
import json
import re

REQUIRED = {"name", "split", "prompt"}
OPTIONAL = {"stdout", "json_contains", "tool", "tool_result", "forbidden_tools"}
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
    if not ({"stdout", "json_contains", "tool"} & case.keys()):
        raise ValueError("Supply exact stdout, JSON fields, or an expected tool.")
    if "tool_result" in case and "tool" not in case:
        raise ValueError("A tool result requires an expected tool call.")
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
    if "json_contains" in case:
        expected = case["json_contains"]
        if not isinstance(expected, dict) or not expected:
            raise ValueError("JSON checks need a nonempty object of expected fields.")
        try:
            payload = json.dumps(expected, allow_nan=False, separators=(",", ":"))
        except (TypeError, ValueError, RecursionError):
            raise ValueError("JSON check must be serializable.") from None
        if len(payload) > 4096:
            raise ValueError("JSON expectation exceeds 4096 bytes.")


def _contains(actual, expected):
    if isinstance(expected, dict):
        return (isinstance(actual, dict)
                and all(key in actual and _contains(actual[key], value) for key, value in expected.items()))
    # List and scalar equality is intentional; order and multiplicity matter.
    return type(actual) is type(expected) and actual == expected


def evaluate(case, stdout, tools_called, tool_result_observed):
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
    checks = (stdout_matches, json_matches, required_tool_called, required_tool_observed, forbidden_tools_absent)
    return {"passed": all(x is not False for x in checks),
            "stdout_matches": stdout_matches,
            "json_matches": json_matches,
            "required_tool_called": required_tool_called,
            "required_tool_observed": required_tool_observed,
            "forbidden_tools_absent": forbidden_tools_absent}
