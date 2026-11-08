#!/usr/bin/python3
"""Privileged but tightly bounded Docker broker; never forwards arbitrary Docker API.

A publicly exposed Refit account can never access this socket directly.
Only the unprivileged application service can use its group-readable socket.
The broker authenticates access via Unix peer credentials, validates full
Docker argument sequences and immutable image IDs, and relays framed stdio.
No Docker socket, controller root credential or unrestricted Docker CLI is
provided to the public application process or the generated worker.
"""
from __future__ import annotations
import grp
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import stat
import struct
import subprocess
import sys
import threading

SOCKET = "/run/refit-docker-guard/docker.sock"
CONFIG = "/etc/refit/docker-guard.json"
DOCKER = "/usr/bin/docker"
APP_NAME = re.compile(r"refit-app-[a-f0-9]{20}")
DIAG_NAME = re.compile(r"refit-[a-f0-9]{20}")
STAGE_NAME = re.compile(r"refit-sandbox-[A-Za-z0-9_-]{6,32}")
MAX_HEADER = 4096
MAX_CHUNK = 65536


def approved_images():
    values = json.loads(Path(CONFIG).read_text())
    if set(values) != {"application", "diagnostic"} or any(
            not isinstance(value, str)
            or not re.fullmatch(r"sha256:[a-f0-9]{64}", value)
            for value in values.values()):
        raise ValueError("Broker has no approved content-addressed runtime images")
    return values


def valid_name(name):
    return isinstance(name, str) and bool(APP_NAME.fullmatch(name) or DIAG_NAME.fullmatch(name))


def diagnostic_mount(src, cid):
    """Daemon mounts are confined to exactly one caller-owned staging payload."""
    root = Path("/var/lib/refit-application/sandbox-staging")
    try:
        folder = Path(src)
        cidfile = Path(cid)
        if not folder.is_absolute() or not cidfile.is_absolute():
            return False
        if folder.name != "payload" or not STAGE_NAME.fullmatch(folder.parent.name):
            return False
        if cidfile != folder.parent / "container.id":
            return False
        if folder.parent.parent != root:
            return False
        if folder.is_symlink() or folder.parent.is_symlink():
            return False
        if folder.resolve(strict=True) != folder or folder.parent.resolve(strict=True) != folder.parent:
            return False
        if not folder.is_dir():
            return False
        for filename in ("program.py", "input.json"):
            file = folder / filename
            if file.is_symlink() or not file.is_file() or not stat.S_ISREG(file.stat().st_mode):
                return False
            if file.stat().st_size > (20000 if filename == "program.py" else 65536):
                return False
        return True
    except (OSError, ValueError, RuntimeError):
        return False


def permitted(args, images):
    if not isinstance(args, list) or len(args) > 70 or any(
            not isinstance(a, str) or len(a) > 1000 or "\x00" in a for a in args):
        return False
    if args in (["info", "--format", "{{json .ID}}"],
                ["info", "--format", "{{json .Runtimes}}"]):
        return True
    if args == ["image", "inspect", "--format={{.Id}}", images["application"]]:
        return True
    if len(args) == 2 and args[0] == "inspect" and APP_NAME.fullmatch(args[1]):
        return True
    if len(args) == 3 and args[:2] == ["container", "inspect"] and valid_name(args[2]):
        return True
    if len(args) == 3 and args[:2] == ["rm", "-f"] and valid_name(args[2]):
        return True
    if len(args) < 4 or args[0] != "run":
        return False
    if args[1] == "-i" and len(args) >= 4:
        name = args[3]
        if not APP_NAME.fullmatch(name):
            return False
        expected = [
            "run", "-i", "--name", name, "--runtime", "runsc",
            "--network", "none", "--read-only", "--user", "65534:65534",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
            "--pids-limit", "128", "--memory", "4g", "--memory-swap", "4g",
            "--cpus", "2", "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=128m",
            "--log-driver", "none", images["application"],
        ]
        return args == expected
    if args[1] == "--rm" and len(args) == 39:
        # Exact fixed diagnostic options; only the unpredictable container
        # name and staging paths may vary.
        try:
            name = args[3]
            cidfile = args[5]
            mount = args[30]
            if not DIAG_NAME.fullmatch(name):
                return False
            prefix, suffix = "type=bind,src=", ",dst=/refit-input,readonly"
            if not (mount.startswith(prefix) and mount.endswith(suffix)):
                return False
            src = mount[len(prefix):-len(suffix)]
            expected = [
                "run", "--rm", "--name", name, "--cidfile", cidfile,
                "--runtime", "runsc", "--network", "none",
                "--user", "65534:65534", "--read-only",
                "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges:true",
                "--pids-limit", "32", "--memory", "128m", "--memory-swap", "128m",
                "--cpus", "0.5", "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=16m",
                "--log-driver", "none", "--mount", mount, "--workdir", "/tmp",
                images["diagnostic"], "python", "-I", "-S", "-B", "/refit-input/program.py",
            ]
            return args == expected and diagnostic_mount(src, cidfile)
        except (IndexError, ValueError, TypeError):
            return False
    return False


def recv_exact(sock, size):
    pieces = []
    while size:
        part = sock.recv(size)
        if not part:
            raise EOFError("broker disconnected")
        pieces.append(part)
        size -= len(part)
    return b"".join(pieces)


def send(sock, kind, payload, lock):
    if len(payload) > MAX_CHUNK:
        raise ValueError("oversized broker packet")
    with lock:
        sock.sendall(kind + struct.pack(">I", len(payload)) + payload)


def receive(sock):
    header = recv_exact(sock, 5)
    size = struct.unpack(">I", header[1:])[0]
    if size > MAX_CHUNK:
        raise ValueError("oversized broker packet")
    return header[:1], recv_exact(sock, size)


class Guard(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = False
    request_queue_size = 12


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        sock = self.request
        try:
            # Linux peer credential check is independent of socket permissions.
            creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            _, uid, _ = struct.unpack("3i", creds)
            import pwd
            if uid != pwd.getpwnam("refit-application").pw_uid:
                return
            size = struct.unpack(">I", recv_exact(sock, 4))[0]
            if not 1 <= size <= MAX_HEADER:
                return
            req = json.loads(recv_exact(sock, size))
            args = req.get("argv") if isinstance(req, dict) and set(req) == {"argv"} else None
            images = approved_images()
            if not permitted(args, images):
                send(sock, b"R", b"Refit Docker broker rejected an unapproved operation.\n", threading.Lock())
                send(sock, b"X", struct.pack(">I", 126), threading.Lock())
                return
        except (OSError, EOFError, ValueError, KeyError, TypeError):
            return

        # Root executes only a validated command vector using approved immutable
        # images and a fixed Docker binary. Never a shell or caller environment.
        try:
            proc = subprocess.Popen([DOCKER, *args],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, env={"PATH": "/usr/bin:/bin"},
                                    bufsize=0)
        except OSError:
            lock = threading.Lock()
            send(sock, b"X", struct.pack(">I", 125), lock)
            return
        lock = threading.Lock()

        def uplink():
            try:
                while proc.poll() is None:
                    kind, payload = receive(sock)
                    if kind == b"E":
                        proc.stdin.close()
                        return
                    if kind != b"I":
                        raise ValueError("unexpected client stream")
                    if payload:
                        proc.stdin.write(payload)
            except (OSError, EOFError, ValueError, BrokenPipeError):
                try:
                    proc.stdin.close()
                except OSError:
                    pass

        def downlink(stream, marker):
            try:
                while True:
                    chunk = stream.read(MAX_CHUNK)
                    if not chunk:
                        return
                    send(sock, marker, chunk, lock)
            except (BrokenPipeError, ConnectionError, OSError):
                pass

        inbound = threading.Thread(target=uplink, daemon=True)
        stdout = threading.Thread(target=downlink, args=(proc.stdout, b"O"), daemon=True)
        stderr = threading.Thread(target=downlink, args=(proc.stderr, b"R"), daemon=True)
        inbound.start()
        stdout.start()
        stderr.start()
        try:
            status = proc.wait(timeout=1150)
        except subprocess.TimeoutExpired:
            proc.kill()
            status = 124
        stdout.join(timeout=3)
        stderr.join(timeout=3)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            try:
                stream.close()
            except OSError:
                pass
        # The trusted root-side Docker CLI creates the cidfile. Transfer only
        # that small receipt back to the unprivileged owner so the controller
        # can independently verify actual container creation.
        if args[:2] == ["run", "--rm"]:
            try:
                cidfile = Path(args[5])
                if cidfile.is_file() and not cidfile.is_symlink():
                    import pwd
                    owner = pwd.getpwnam("refit-application")
                    os.chown(cidfile, owner.pw_uid, owner.pw_gid)
                    os.chmod(cidfile, 0o600)
            except OSError:
                # No silently verified container if this receipt is unavailable.
                pass
        try:
            send(sock, b"X", struct.pack(">I", max(0, status) if status >= 0 else 128 - status), lock)
        except (BrokenPipeError, ConnectionError, OSError):
            pass
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


def server():
    # Daemon must have the authority; the application service must not.
    if os.geteuid() != 0:
        raise RuntimeError("Docker broker must be root-owned")
    approved_images()
    path = Path(SOCKET)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        # Never unlink a real socket owned by another process.
        raise RuntimeError("Broker socket already exists")
    with Guard(str(path), Handler) as service:
        os.chown(path, 0, grp.getgrnam("refit-application").gr_gid)
        os.chmod(path, 0o660)
        service.serve_forever(poll_interval=0.2)


def client(args):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(None)
            sock.connect(SOCKET)
            body = json.dumps({"argv": args}, separators=(",", ":")).encode()
            if len(body) > MAX_HEADER:
                return 125
            sock.sendall(struct.pack(">I", len(body)) + body)

            def stdin_pump():
                try:
                    while True:
                        # A raw pipe read forwards available bytes immediately
                        # without holding BufferedReader's interpreter-shutdown
                        # lock. The worker may exit while parent stdin stays open.
                        data = os.read(sys.stdin.fileno(), MAX_CHUNK)
                        if not data:
                            send(sock, b"E", b"", threading.Lock())
                            return
                        send(sock, b"I", data, threading.Lock())
                except (OSError, EOFError, BrokenPipeError):
                    pass

            threading.Thread(target=stdin_pump, daemon=True).start()
            while True:
                kind, payload = receive(sock)
                if kind == b"O":
                    sys.stdout.buffer.write(payload)
                    sys.stdout.buffer.flush()
                elif kind == b"R":
                    sys.stderr.buffer.write(payload)
                    sys.stderr.buffer.flush()
                elif kind == b"X":
                    if len(payload) != 4:
                        return 125
                    return struct.unpack(">I", payload)[0]
                else:
                    return 125
    except (OSError, EOFError, ValueError) as error:
        sys.stderr.write("Refit Docker broker unavailable: " + type(error).__name__ + "\n")
        return 125


if __name__ == "__main__":
    if sys.argv[1:] == ["--server"]:
        server()
    else:
        raise SystemExit(client(sys.argv[1:]))
