"""Zero-inference probes of the same gVisor runner used by imported applications."""
import base64
import json

from .application_run import run_migration


class NoInference:
    requests = 0
    max_requests = 0

    def complete(self, *args, **kwargs):
        raise AssertionError("Containment probes must never request inference")


PROBE = """
import os, pathlib, socket, time
assert os.getuid() == 65534
assert not pathlib.Path('/var/run/docker.sock').exists()
assert not pathlib.Path('/etc/refit/inference.env').exists()
assert not pathlib.Path('/opt/refit/evaluation_cases.json').exists()
assert 'VULTR_INFERENCE_API_KEY' not in os.environ
try:
    pathlib.Path('/opt/refit/boundary-test').touch()
except OSError:
    pass
else:
    raise AssertionError('sandbox root is writable')
try:
    socket.create_connection(('1.1.1.1', 443), 1)
except OSError:
    pass
else:
    raise AssertionError('sandbox has outbound networking')
print('isolated', flush=True)
"""


def main():
    for suffix, expected in (("", "model_boundary_unused"), ("\nwhile True: time.sleep(1)\n", "application_timeout")):
        source = base64.b64encode((PROBE + suffix).encode()).decode()
        snapshot = {"files": {"probe.py": source}}
        setup = {"module": "probe", "args": [], "seam": "openai-env", "cases": [
            {"name": "probe", "split": "train", "prompt": "probe", "stdout": "isolated"}
        ]}
        events = []
        # Keep the production limit intact while shortening the synthetic probe.
        import scripts.application_run as runtime
        runtime.CASE_SECONDS = 3
        result = run_migration(snapshot, setup, "source", "target", "refit-application",
                               NoInference(), lambda kind, details: events.append((kind, details)), lambda: False)
        case = next(details for kind, details in events if kind == "case_completed")
        assert result["status"] == "source_baseline_insufficient" and result["export"] is None
        assert case["error"] == expected and case["runtime"] == "runsc" and case["cleanup"]["verified"], case
        if expected == "model_boundary_unused":
            assert case["verdict"]["stdout_matches"]
        print(json.dumps(case), flush=True)


if __name__ == "__main__":
    main()
