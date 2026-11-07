"""Paid original-agent acceptance for the two developer-side connector transports."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading

from .application_cli import write_local_zip
from .application_import import unpack_zip
from .application_run import MODELS, RunStopped, configuration, run_migration
from .refit_vultr_probe import VultrInference

REPOSITORY = "rma67274-boop/wulianwang_zuoye_mrp"
REVISION = "78e234c09412cabf6a1d6f901329c5b66360d946"
CASES = [
    {"name": "gauss", "split": "train",
     "prompt": "请从知识库逐字复制高斯定律的积分公式（不要添加 Markdown 或解释）。第一行只写公式，第二行只写来源页标题，格式 [[页面标题]]。",
     "stdout": "∮ E · dS = Q_enc / epsilon_0\n[[高斯定律与电通量]]"},
    {"name": "magnetic-divergence", "split": "validation",
     "prompt": "请从麦克斯韦方程组页面逐字复制磁场无源的公式，不改记号。第一行只写原文公式，第二行只写来源页标题，格式 [[页面标题]]。不要添加其他内容。",
     "stdout": "nabla · B = 0\n[[麦克斯韦方程组与统一图景]]"},
    {"name": "line-current", "split": "holdout",
     "prompt": "请逐字复制知识库中传输线电流 I 沿 x 变化的偏微分方程。第一行只写原文公式，第二行只写来源页标题，格式 [[页面标题]]。不要使用 LaTeX 或添加解释。",
     "stdout": "partial I / partial x = -G V - C partial V / partial t\n[[传输线、驻波与波导]]"},
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authorize-requests", type=int, choices=[16], required=True)
    args = parser.parse_args()
    key = os.environ.get("VULTR_INFERENCE_API_KEY")
    if not key:
        parser.error("Missing Vultr credential. No paid request was made.")
    with tempfile.TemporaryDirectory(prefix="refit-connector-test-") as directory:
        root = Path(directory)
        checkout = root / "upstream"
        checkout.mkdir()
        subprocess.run(["git", "init", "-q", str(checkout)], check=True)
        subprocess.run(["git", "-C", str(checkout), "fetch", "-q", "--depth=1",
                        f"https://github.com/{REPOSITORY}.git", REVISION], check=True, timeout=30)
        revision = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "FETCH_HEAD"],
                                           text=True).strip()
        if revision != REVISION:
            raise RuntimeError("Unexpected source revision.")
        subprocess.run(["git", "-C", str(checkout), "checkout", "--detach", "--quiet", REVISION], check=True)
        with tempfile.TemporaryFile() as archive:
            write_local_zip(archive, checkout)
            archive.seek(0)
            snapshot = unpack_zip(archive)
        snapshot.update(repository=REPOSITORY, revision=REVISION)
        setup = configuration(snapshot, {"module": "src.qa", "args": ["{prompt}"], "cases": CASES})
        bearer = secrets.token_urlsafe(24)

        class TestAgent(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path != "/invoke" or self.headers.get("Authorization") != "Bearer " + bearer:
                    self.send_error(403)
                    return
                call = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                # This pinned QA app is read-only. Each request starts a new original process.
                env = {"PATH": os.environ["PATH"], "PYTHONDONTWRITEBYTECODE": "1",
                       "OPENAI_MODEL": call["model"], "OPENAI_BASE_URL": call["base_url"],
                       "OPENAI_API_KEY": call["api_key"]}
                result = subprocess.run([sys.executable, "-B", "-m", "src.qa", call["prompt"]],
                                        cwd=checkout, env=env, capture_output=True, text=True, timeout=35)
                if result.returncode:
                    self.send_error(502)
                    return
                body = json.dumps({"output": result.stdout}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass

        receipts = []
        with ThreadingHTTPServer(("127.0.0.1", 0), TestAgent) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                modes = [
                    ("local_connector", setup, {"local_python": sys.executable}),
                    ("existing_test_service", {"args": [], "seam": "openai-env", "cases": CASES},
                     {"test_service": f"http://127.0.0.1:{server.server_port}/invoke", "service_bearer": bearer}),
                ]
                for mode, config, options in modes:
                    broker = VultrInference(key, max_requests=8)
                    events = []
                    try:
                        result = run_migration(snapshot, config, *MODELS, None, broker,
                                               lambda kind, data: events.append((kind, data)), lambda: False, **options)
                    except RunStopped as exc:
                        result = {"status": str(exc), "export": None}
                    receipts.append({"mode": mode, "isolation": "developer_host", "source": MODELS[0],
                                     "target": MODELS[1], "repository": REPOSITORY, "revision": REVISION,
                                     "invocation": "python -B -m src.qa <prompt>", "paid_requests": broker.requests,
                                     "result": result, "events": events})
            finally:
                server.shutdown()
                thread.join()
    args.output.write_text(json.dumps(receipts, indent=2) + "\n")
    for receipt in receipts:
        result = receipt["result"]
        cleanup = [details["receipt"]["verified"] for kind, details in receipt["events"] if kind == "local_cleanup"]
        print(json.dumps({"mode": receipt["mode"], "revision": receipt["revision"], "status": result["status"],
                          "paid_requests": receipt["paid_requests"], "fresh_export": bool(result["export"]),
                          "verified_cleanups": sum(cleanup)}))
    return 0 if all(receipt["result"]["export"] for receipt in receipts) else 1


if __name__ == "__main__":
    sys.exit(main())
