"""Zero-inference static visual acceptance: provenance, safety, same-origin routing."""
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
import xml.etree.ElementTree as ET

from scripts.application_http import ApplicationHandler, ApplicationService, ROOT


ASSETS = {
    "folders": "document-folders",
    "servers": "woman-working-servers",
    "programs": "man-working-programs",
    "lock": "password-lock-key",
    "error": "laptop-server-error",
}


class VisualAssetTests(unittest.TestCase):
    def test_svg_license_and_local_asset_provenance(self):
        assets = ROOT / "web/application/illustrations"
        license_text = (assets / "LICENSE-MIT.txt").read_text(encoding="utf-8")
        self.assertIn("MIT License", license_text)
        self.assertIn("Permission is hereby granted", license_text)
        for name in ASSETS.values():
            for suffix in ("", "-dark"):
                path = assets / (name + suffix + ".svg")
                with self.subTest(file=path.name):
                    self.assertTrue(path.is_file())
                    self.assertLess(path.stat().st_size, 48 * 1024,
                                    "Illustration too large for product UI")
                    source = path.read_text(encoding="utf-8")
                    root = ET.fromstring(source)
                    self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
                    self.assertNotIn("<script", source.lower())
                    self.assertNotIn("<foreignobject", source.lower())
                    self.assertNotIn('href="http', source.lower())
                    self.assertNotIn('src="http', source.lower())

    def test_actual_public_routes_and_embedded_license(self):
        with TemporaryDirectory() as tmp:
            service = ApplicationService(
                Path(tmp), "test-operator-token-32-characters", "no-worker",
                public_origin="https://refit.example"
            )
            handler = type("VisualHandler", (ApplicationHandler,), {"service": service})
            try:
                with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
                    thread = Thread(target=server.serve_forever, daemon=True)
                    thread.start()
                    try:
                        def get(route):
                            client = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                            client.request("GET", route, headers={"X-Refit-Public": "1"})
                            response = client.getresponse()
                            payload = response.read()
                            output = (response.status, response.getheader("Content-Type"), payload)
                            client.close()
                            return output

                        status, mime, home = get("/")
                        self.assertEqual((status, mime), (200, "text/html; charset=utf-8"))
                        self.assertIn(b"/assets/marketing.css", home)
                        self.assertIn(b"/assets/marketing.js", home)
                        self.assertIn(b"/api/application/demo", (ROOT / "web/application/marketing.js").read_bytes())
                        for asset in ("marketing.css", "marketing.js", "visual.css"):
                            status, mime, body = get("/assets/" + asset)
                            self.assertEqual(status, 200)
                            self.assertTrue(body)
                            self.assertIn("text/", mime)
                        for name in ASSETS:
                            for variant in ("", "-dark"):
                                status, mime, body = get(f"/assets/illustrations/{name}{variant}.svg")
                                self.assertEqual(status, 200)
                                self.assertEqual(mime, "image/svg+xml")
                                self.assertGreater(len(body), 1000)
                        self.assertIn(get("/assets/illustrations/../../../../etc/passwd")[0], (401, 404))
                    finally:
                        server.shutdown()
                        thread.join()
            finally:
                service.process_lock.close()


if __name__ == "__main__":
    unittest.main()
