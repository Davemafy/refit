"""Run the original application with a loopback-only Chat Completions seam."""
import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time


def send(data):
    print(json.dumps(data, separators=(",", ":")), flush=True)


def main():
    cfg = json.loads(sys.stdin.buffer.readline(20 * 1024 * 1024))
    with tempfile.TemporaryDirectory(prefix="application-") as tmp:
        root = Path(tmp) / "source"
        root.mkdir()
        home = Path(tmp) / "home"
        home.mkdir()
        for name, value in cfg["files"].items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base64.b64decode(value))
        class Chat(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path != "/v1/chat/completions":
                    self.send_error(404)
                    return
                try:
                    length = int(self.headers["Content-Length"])
                    if not 1 <= length <= 512 * 1024:
                        raise ValueError("invalid request length")
                    body = json.loads(self.rfile.read(length))
                    send({"type": "completion", "body": body})
                    reply = json.loads(sys.stdin.readline())
                    if "message" not in reply:
                        self.send_error(400, "Refit broker stopped this case")
                        return
                    message = reply["message"]
                    payload = json.dumps({"id": "chatcmpl-refit", "object": "chat.completion",
                        "created": int(time.time()), "model": body["model"],
                        "choices": [{"index": 0, "message": message,
                            "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}]}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except (ValueError, KeyError, TypeError):
                    self.send_error(400, "Invalid Chat Completions request")

            def log_message(self, *_):
                pass

            def setup(self):
                self.request.settimeout(15)
                super().setup()

        server = HTTPServer(("127.0.0.1", 0), Chat)
        endpoint = f"http://127.0.0.1:{server.server_port}/v1"
        threading.Thread(target=server.serve_forever, daemon=True).start()
        env = {"HOME": str(home), "PATH": "/usr/local/bin:/usr/bin:/bin",
               "PYTHONPATH": str(root), "PYTHONDONTWRITEBYTECODE": "1",
               "OPENAI_BASE_URL": endpoint, "OPENAI_MODEL": cfg["model"],
               "OPENAI_API_KEY": "refit-loopback", "OPENAI_MAX_RETRIES": "0",
               "LLM_USER_PATH": str(home)}
        if cfg["seam"] == "llm":
            (home / "extra-openai-models.yaml").write_text(json.dumps([{
                "model_id": cfg["model"], "model_name": cfg["model"],
                "api_base": endpoint, "can_stream": False, "supports_tools": True
            }]))
        argv = [arg.replace("{model}", cfg["model"]).replace("{prompt}", cfg["prompt"])
                for arg in cfg["args"]]
        # Files bound output growth by the container's writable tmpfs limit.
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            proc = subprocess.Popen([sys.executable, "-B", "-m", cfg["module"], *argv],
                cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
            try:
                proc.wait(timeout=cfg["timeout"])
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                send({"type": "case", "status": "application_timeout"})
                return
            stdout.seek(0)
            stderr.seek(0)
            output = stdout.read(16385)
            send({"type": "case", "status": "completed" if len(output) <= 16384 else "output_limit",
                  "exit_code": proc.returncode, "stdout": output[:16384].decode("utf-8", "replace"),
                  "stderr": stderr.read(2048).decode("utf-8", "replace")})


if __name__ == "__main__":
    main()
