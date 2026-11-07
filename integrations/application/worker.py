"""Run the original application with a loopback-only Chat Completions seam."""
import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import secrets
import signal
import stat
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time


def send(data):
    print(json.dumps(data, separators=(",", ":")), flush=True)


def instruction_environment(cfg):
    if cfg["seam"] != "instruction-env":
        return {}
    import re
    key = cfg["instruction_env"]
    if not isinstance(key, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}_(?:PROMPT|INSTRUCTIONS)", key):
        raise ValueError("Invalid instruction environment key")
    base = cfg["instruction_base"]
    extra = cfg.get("instructions", "")
    if (not isinstance(base, str) or not 1 <= len(base) <= 4096 or
            not isinstance(extra, str) or len(extra) > 4096 or
            "\x00" in base or "\x00" in extra):
        raise ValueError("Invalid native instruction text")
    return {key: base + ("\n\n" + extra if extra else "")}


def observe_state(root_fd, paths):
    """Inspect bounded regular files without following links out of the workspace."""
    observations = {}
    for path in paths:
        fd = os.dup(root_fd)
        try:
            parts = path.split("/")
            for part in parts[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            child = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            with os.fdopen(child, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    observations[path] = {"status": "unsupported"}
                    continue
                value = stream.read(16385)
            observations[path] = ({"status": "file", "text": value.decode("utf-8")}
                                  if len(value) <= 16384 else {"status": "too_large"})
        except FileNotFoundError:
            observations[path] = {"status": "missing"}
        except (OSError, UnicodeDecodeError):
            observations[path] = {"status": "unsupported"}
        finally:
            os.close(fd)
    return observations


def call_test_service(cfg, endpoint, broker_token):
    from urllib.request import HTTPRedirectHandler, Request, build_opener

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    request = Request(cfg["test_service"], method="POST", headers={
        "Authorization": "Bearer " + cfg["service_bearer"], "Content-Type": "application/json",
    }, data=json.dumps({"prompt": cfg["prompt"], "model": cfg["model"],
                       "base_url": endpoint, "api_key": broker_token}).encode())
    try:
        with build_opener(NoRedirect()).open(request, timeout=cfg["timeout"]) as response:
            raw = response.read(16385)
        if len(raw) > 16384:
            raise ValueError("response_limit")
        output = json.loads(raw)
        if not isinstance(output, dict) or set(output) != {"output"} or not isinstance(output["output"], (str, dict)):
            raise ValueError("invalid_response")
    except (OSError, ValueError):
        send({"type": "case", "status": "test_service_failed"})
        return
    value = output["output"]
    send({"type": "case", "status": "completed", "exit_code": 0,
          "stdout": value if isinstance(value, str) else json.dumps(value)})


def main():
    local = sys.argv[1:] == ["--local-connector"]
    broker_token = secrets.token_urlsafe(24) if local else "refit-loopback"
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
                if local and not secrets.compare_digest(
                        self.headers.get("Authorization", "").encode(), f"Bearer {broker_token}".encode()):
                    self.send_error(401)
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
        if local and cfg.get("test_service"):
            call_test_service(cfg, endpoint, broker_token)
            return
        env = {"HOME": str(home), "PATH": "/usr/local/bin:/usr/bin:/bin",
               "PYTHONPATH": str(root), "PYTHONDONTWRITEBYTECODE": "1",
               "OPENAI_BASE_URL": endpoint, "OPENAI_MODEL": cfg["model"],
               "OPENAI_API_KEY": broker_token, "OPENAI_MAX_RETRIES": "0",
               "LLM_USER_PATH": str(home)}
        env.update(instruction_environment(cfg))
        if cfg["seam"] == "llm":
            (home / "extra-openai-models.yaml").write_text(json.dumps([{
                "model_id": cfg["model"], "model_name": cfg["model"],
                "api_base": endpoint, "can_stream": False, "supports_tools": True
            }]))
        argv = [arg.replace("{model}", cfg["model"]).replace("{prompt}", cfg["prompt"])
                for arg in cfg["args"]]
        if cfg.get("entry"):
            (root / "node_modules").symlink_to("/opt/refit/node/node_modules", target_is_directory=True)
            invocation = ["/usr/local/bin/node", "--import", "/opt/refit/node/node_modules/tsx/dist/loader.mjs",
                          "./" + cfg["entry"], *argv]
        else:
            interpreter = cfg["local_python"] if local else sys.executable
            invocation = [interpreter, "-B", "-m", cfg["module"], *argv]
        paths = cfg.get("state_paths", [])
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        initial = observe_state(root_fd, paths)
        # In local mode no container tmpfs protects disk space. Limit per-file
        # output and state growth for the developer-authorized child.
        if local:
            import resource
            resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024,) * 2)
        # The managed runtime also bounds output by its writable tmpfs limit.
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            proc = subprocess.Popen(invocation,
                cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, start_new_session=not local)
            try:
                proc.wait(timeout=cfg["timeout"])
            except subprocess.TimeoutExpired:
                if local:
                    proc.kill()
                else:
                    os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                os.close(root_fd)
                send({"type": "case", "status": "application_timeout"})
                return
            if not local:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            final = observe_state(root_fd, paths)
            os.close(root_fd)
            stdout.seek(0)
            stderr.seek(0)
            output = stdout.read(16385)
            send({"type": "case", "status": "completed" if len(output) <= 16384 else "output_limit",
                  "exit_code": proc.returncode, "state": {path: {"before": initial[path], "after": final[path]}
                                                           for path in paths}, "stdout": output[:16384].decode("utf-8", "replace"),
                  "stderr": stderr.read(2048).decode("utf-8", "replace")})


if __name__ == "__main__":
    main()
