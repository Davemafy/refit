"""SaaS route and authentication smoke through the real HTTP handler, no inference."""
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from scripts.application_http import ApplicationHandler, ApplicationService


class SaaSRoutes(unittest.TestCase):
    def test_public_routes_authentication_and_operator_compatibility(self):
        with TemporaryDirectory() as directory:
            service = ApplicationService(
                Path(directory), "refit-operator-test-token-32characters", "image",
                public_origin="https://refit.example"
            )
            handler = type("Handler", (ApplicationHandler,), {"service": service})
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()

            def call(method, path, data=None, cookie="", public=True):
                connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                headers = {"Origin": "https://refit.example"}
                if public:
                    headers["X-Refit-Public"] = "1"
                if cookie:
                    headers["Cookie"] = cookie
                if data is not None:
                    headers["Content-Type"] = "application/json"
                    data = json.dumps(data)
                try:
                    connection.request(method, path, data, headers)
                    response = connection.getresponse()
                    return response.status, response.getheader("Location"), response.getheader("Set-Cookie"), response.read().decode()
                finally:
                    connection.close()

            try:
                status, _, _, body = call("GET", "/")
                self.assertEqual(status, 200)
                self.assertIn("Change the model", body)
                status, _, _, body = call("GET", "/docs")
                self.assertEqual(status, 200)
                self.assertIn("Documentation", body)
                status, location, _, _ = call("GET", "/bring")
                self.assertEqual((status, location), (302, "/app/agents/new"))
                status, location, _, body = call("GET", "/app/agents/new")
                self.assertEqual(status, 200)
                self.assertIn('id="page"', body)
                status, location, _, body = call("GET", "/app")
                self.assertEqual(status, 200)
                self.assertIn('id="page"', body)
                status, _, _, demo_text = call("GET", "/api/application/demo")
                self.assertEqual(status, 200)
                demo = json.loads(demo_text)
                self.assertTrue(demo["public_sample"])
                self.assertEqual(demo["run"]["id"], "demo-python-2026-11-07")
                self.assertEqual(demo["run"]["source"], "deepseek-v4.1-flash-1017")
                self.assertEqual(demo["run"]["target"], "glm-5.2")
                self.assertGreaterEqual(len(demo["events"]), 7)
                self.assertNotIn("files", demo["run"].get("import", {}))
                self.assertNotIn("trace", demo_text)
                self.assertEqual(call("GET", "/api/application/projects")[0], 401)
                self.assertEqual(call("GET", "/api/application/runs")[0], 401)
                self.assertEqual(call("POST", "/api/application/runs", {})[0], 401)
                for route in ("/login", "/signup"):
                    status, _, _, body = call("GET", route)
                    self.assertEqual(status, 200)
                    self.assertIn('id="authForm"', body)
                    self.assertNotIn('id="invite"', body)
                for route in ("/assets/ui.css", "/assets/app.js", "/assets/run-outcome.js", "/assets/auth.js"):
                    status, _, _, body = call("GET", route)
                    self.assertEqual(status, 200)
                    self.assertGreater(len(body), 100)

                status, _, cookie, _ = call("POST", "/api/application/register", {
                    "username": "ui-test", "password": "test-long-secret-12345"
                })
                self.assertEqual(status, 201)
                self.assertIn("__Host-refit-session=", cookie)
                cookie = cookie.split(";", 1)[0]

                for route in ("/app", "/app/agents", "/app/agents/new", "/app/runs",
                              "/app/evidence", "/app/settings", "/app/runs/app-1234567890abcdef"):
                    status, _, _, body = call("GET", route, cookie=cookie)
                    self.assertEqual(status, 200, route)
                    self.assertIn('id="page"', body)

                status, _, _, body = call("GET", "/app/runs/app-1234567890abcdef")
                self.assertEqual(status, 200)
                status, _, _, body = call("GET", "/app/runs/demo-python-2026-11-07")
                self.assertEqual(status, 200)
                status, _, _, body = call("GET", "/assets/private.env")
                self.assertEqual(status, 401)  # Unauthorized route, never a file response.

                status, _, _, body = call("GET", "/bring", public=False)
                self.assertEqual(status, 200)
                self.assertIn('id="operatorAccess"', body)
            finally:
                server.shutdown()
                thread.join()
                server.server_close()
                service.process_lock.close()


if __name__ == "__main__":
    unittest.main()
