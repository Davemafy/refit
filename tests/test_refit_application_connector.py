"""Exercise both developer-side connector transports through the shared engine."""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sys
import threading
import unittest
from urllib.request import Request, urlopen

from scripts.application_import import make_snapshot
from scripts.application_run import MODELS, configuration, run_migration


PROGRAM = b"""
import json, os, sys
from urllib.request import Request, urlopen
req = Request(os.environ["OPENAI_BASE_URL"] + "/chat/completions", data=json.dumps({
    "model": os.environ["OPENAI_MODEL"], "messages": [{"role": "user", "content": sys.argv[1]}]
}).encode(), headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]})
print(json.load(urlopen(req))["choices"][0]["message"]["content"])
"""


class EchoBroker:
    max_requests = 8

    def __init__(self):
        self.requests = 0

    def complete(self, model, messages, tools=None, **options):
        self.requests += 1
        return {"role": "assistant", "content": messages[-1]["content"]}


@unittest.skipUnless(sys.platform == "linux", "Linux developer-side connector")
class ApplicationConnectorTests(unittest.TestCase):
    def setUp(self):
        self.cases = [{"name": name, "split": name, "prompt": name, "stdout": name}
                      for name in ("train", "validation", "holdout")]
        self.snapshot = make_snapshot({"agent.py": base64.b64encode(PROGRAM).decode()}, None, None, "", [])

    def check_migration(self, setup, expected_mode, **options):
        broker = EchoBroker()
        events = []
        result = run_migration(self.snapshot, setup, *MODELS, None, broker,
                               lambda name, detail: events.append((name, detail)), lambda: False, **options)
        self.assertEqual(result["status"], "compatible_on_sample")
        self.assertEqual(result["export"]["execution_mode"], expected_mode)
        self.assertTrue(result["verification"][0]["passed"])
        self.assertEqual(broker.requests, 7)
        receipts = [row["receipt"] for name, row in events if name == "local_cleanup"]
        self.assertEqual(len(receipts), 7)
        self.assertTrue(all(row["verified"] and row["isolation"] == "developer_host" for row in receipts))
        self.assertFalse(any(name.startswith("sandbox_") for name, _ in events))
        return result

    def test_local_python_uses_native_runtime_and_no_docker(self):
        setup = configuration(self.snapshot, {"module": "agent", "args": ["{prompt}"], "cases": self.cases})
        result = self.check_migration(setup, "local_connector", local_python=sys.executable)
        self.assertEqual(result["export"]["python"], sys.executable)

    def test_authorized_test_service_brokers_original_requests(self):
        bearer = "test-service-token-not-a-vultr-key"
        seen = []

        class Agent(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.headers.get("Authorization") != "Bearer " + bearer:
                    self.send_error(401)
                    return
                task = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                seen.append(task["prompt"])
                request = Request(task["base_url"] + "/chat/completions", data=json.dumps({
                    "model": task["model"], "messages": [{"role": "user", "content": task["prompt"]}]
                }).encode(), headers={"Authorization": "Bearer " + task["api_key"]})
                with urlopen(request, timeout=5) as response:
                    output = json.load(response)["choices"][0]["message"]["content"]
                body = json.dumps({"output": output}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), Agent) as service:
            thread = threading.Thread(target=service.serve_forever, daemon=True)
            thread.start()
            try:
                setup = {"args": [], "seam": "openai-env", "cases": self.cases}
                url = f"http://127.0.0.1:{service.server_port}/invoke"
                result = self.check_migration(setup, "existing_test_service",
                                              test_service=url, service_bearer=bearer)
                self.assertEqual(result["export"]["test_service"], url)
                self.assertNotIn(bearer, json.dumps(result))
                self.assertEqual(seen, ["train", "train", "validation", "validation",
                                        "holdout", "holdout", "holdout"])
            finally:
                service.shutdown()
                thread.join()

    def test_service_rejects_non_loopback_and_unobservable_state(self):
        setup = {"args": [], "seam": "openai-env", "cases": self.cases}
        options = {"service_bearer": "test-service-token"}
        with self.assertRaisesRegex(ValueError, "loopback"):
            run_migration(self.snapshot, setup, *MODELS, None, EchoBroker(), lambda *_: None,
                          lambda: False, test_service="http://192.0.2.10:443/invoke", **options)
        self.cases[0]["state"] = [{"path": "ledger.json", "op": "changed"}]
        with self.assertRaisesRegex(ValueError, "File-state checks are unavailable"):
            run_migration(self.snapshot, setup, *MODELS, None, EchoBroker(), lambda *_: None,
                          lambda: False, test_service="http://127.0.0.1:1234/invoke", **options)
