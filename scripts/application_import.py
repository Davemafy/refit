"""Validate a bounded application snapshot without executing imported code."""
from __future__ import annotations

import base64
import io
import json
from pathlib import PurePosixPath
import re
import stat
import tomllib
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

from .migration_engine import fingerprint

ARCHIVE_LIMIT = 4 * 1024 * 1024
EXPANDED_LIMIT = 12 * 1024 * 1024
FILE_LIMIT = 1500
REPOSITORY = re.compile(r"[a-zA-Z0-9_.-]{1,100}/[a-zA-Z0-9_.-]{1,100}")
REVISION = re.compile(r"[0-9a-f]{40}")
BLOCKED_DIRS = {".git", ".ssh", ".aws", ".venv", "node_modules", "__pycache__"}


class ImportProblem(ValueError):
    pass


class GitHubArchiveRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        if parsed.scheme != "https" or parsed.netloc != "codeload.github.com":
            raise ImportProblem("GitHub returned an unexpected archive redirect.")
        # The signed archive URL is sufficient. Never forward the repository token.
        return Request(newurl, headers={"User-Agent": "Refit application import"})


class NoGitHubApiRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ImportProblem("GitHub revision discovery was redirected unexpectedly.")


def validate_repo_token(repo, token):
    if (not isinstance(repo, str) or not REPOSITORY.fullmatch(repo) or
            any(part in {".", ".."} for part in repo.split("/"))):
        raise ImportProblem("Enter a GitHub repository such as owner/repository.")
    if (not isinstance(token, str) or len(token) > 512 or
            (token and not re.fullmatch(r"[A-Za-z0-9_]+", token))):
        raise ImportProblem("Use a GitHub read token or leave it blank for public source.")


def resolve_default_revision(repo, token=""):
    """Pin the default branch to an immutable SHA using a fixed GitHub API URL."""
    validate_repo_token(repo, token)
    request = Request(
        f"https://api.github.com/repos/{repo}/commits?per_page=1",
        headers={"User-Agent": "Refit application import",
                 "Accept": "application/vnd.github+json"}
    )
    if token:
        request.add_unredirected_header("Authorization", f"Bearer {token}")
    try:
        with build_opener(NoGitHubApiRedirect()).open(request, timeout=12) as response:
            payload = response.read(64 * 1024 + 1)
        if len(payload) > 64 * 1024:
            raise ImportProblem("GitHub returned an unexpectedly large commit response.")
        commits = json.loads(payload)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise ImportProblem(
            "Could not resolve the repository's latest commit. Check the URL and read access."
        ) from exc
    if not isinstance(commits, list) or not commits or not isinstance(commits[0], dict):
        raise ImportProblem("This repository has no accessible default-branch commit.")
    sha = commits[0].get("sha")
    if not isinstance(sha, str) or not REVISION.fullmatch(sha):
        raise ImportProblem("GitHub did not provide a valid pinned commit SHA.")
    return sha


def github_archive(repo, revision, token=""):
    if not isinstance(repo, str) or not REPOSITORY.fullmatch(repo) or any(
        part in {".", ".."} for part in repo.split("/")
    ) or not isinstance(revision, str) or not REVISION.fullmatch(revision):
        raise ImportProblem("Provide owner/repository and the full 40-character commit SHA.")
    if not isinstance(token, str) or len(token) > 512 or (token and not re.fullmatch(r"[A-Za-z0-9_]+", token)):
        raise ImportProblem("Use a GitHub repository read token or leave it blank for public source.")
    req = Request(f"https://api.github.com/repos/{repo}/zipball/{revision}",
                  headers={"User-Agent": "Refit application import"})
    if token:
        req.add_unredirected_header("Authorization", f"Bearer {token}")
    try:
        with build_opener(GitHubArchiveRedirect()).open(req, timeout=15) as response:
            return response.read(ARCHIVE_LIMIT + 1)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ImportProblem("GitHub archive unavailable. Check the pinned revision and repository read access.") from exc


def safe_path(name):
    if not isinstance(name, str) or len(name) > 240 or "\\" in name or "\x00" in name:
        raise ImportProblem("The archive contains an invalid file path.")
    path = PurePosixPath(name)
    if (not path.parts or path.is_absolute() or ".." in path.parts
            or any(not re.fullmatch(r"[\w.@+() -]+", part) for part in path.parts)):
        raise ImportProblem("The archive contains an unsafe file path.")
    return path


def sensitive(path):
    name = path.name.lower()
    return (any(part.lower() in BLOCKED_DIRS for part in path.parts)
            or (name.startswith(".env") and name not in {".env.example", ".env.sample"})
            or name in {"id_rsa", "id_ed25519", "credentials.json", "secrets.json", ".npmrc", ".pypirc"}
            or name.endswith((".key", ".pem", ".p12", ".pfx")))


def unpack(archive, *, github=False):
    if not 1 <= len(archive) <= ARCHIVE_LIMIT:
        raise ImportProblem("Upload a ZIP no larger than 4 MiB, or select a smaller source snapshot.")
    files = {}
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            entries = zipped.infolist()
            if len(entries) > FILE_LIMIT or sum(entry.file_size for entry in entries) > EXPANDED_LIMIT:
                raise ImportProblem("The ZIP exceeds 1,500 entries or 12 MiB expanded.")
            roots = {safe_path(entry.orig_filename).parts[0] for entry in entries}
            if github and len(roots) != 1:
                raise ImportProblem("GitHub archive has an unexpected source layout.")
            for entry in entries:
                path = safe_path(entry.orig_filename)
                mode = stat.S_IFMT(entry.external_attr >> 16)
                if mode not in (0, stat.S_IFREG, stat.S_IFDIR) or entry.flag_bits & 1:
                    raise ImportProblem("Symlinks, special files and encrypted files are not supported.")
                if entry.is_dir():
                    continue
                if github:
                    path = PurePosixPath(*path.parts[1:])
                    if not path.parts:
                        raise ImportProblem("GitHub archive has an unexpected file at its root.")
                if sensitive(path):
                    raise ImportProblem("Remove credentials, private keys and dependency caches from the snapshot.")
                key = path.as_posix()
                if key in files:
                    raise ImportProblem("Duplicate archive paths are not supported.")
                if entry.file_size > 512 * 1024:
                    # Keep source inspection and transport narrow. A required large
                    # asset must be supplied by an explicitly supported runtime.
                    raise ImportProblem("Each source file must be at most 512 KiB.")
                files[key] = base64.b64encode(zipped.read(entry)).decode("ascii")
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError) as exc:
        raise ImportProblem("The uploaded file is not a readable supported ZIP.") from exc
    if not files or any(str(parent) in files for name in files for parent in PurePosixPath(name).parents):
        raise ImportProblem("The archive is empty or has conflicting paths.")
    return files


def inspect(files):
    def read(name):
        return base64.b64decode(files.get(name, "")).decode("utf-8", "replace")
    try:
        project = tomllib.loads(read("pyproject.toml")).get("project", {})
        if not isinstance(project, dict):
            project = {}
    except ValueError:
        project = {}
    python = any(name.endswith(".py") for name in files)
    node_files = [name for name in files if name.endswith((".ts", ".mts", ".js", ".mjs"))
                  and not name.endswith(".d.ts")]
    typescript = any(name.endswith((".ts", ".tsx", ".mts")) for name in files) or (
        "package.json" in files and bool(node_files))
    try:
        package = json.loads(read("package.json"))
        if not isinstance(package, dict):
            package = {}
    except ValueError:
        package = {}
    runtime = "python" if python and not typescript else "typescript" if typescript else "unknown"
    if project.get("name") == "llm" and project.get("version") == "0.37.1" and "llm/__main__.py" in files:
        return {"runtime": "python", "setup": None, "preset": "llm-0.37.1",
                "provider": "OpenAI-compatible Chat Completions",
                "entry": "python -m llm", "tool": "llm_version",
                "evaluation": "Exact stdout and observed original llm_version tool result"}
    evaluation_files = sorted(name for name in files if
        (name.startswith(("test/", "tests/", "__tests__/")) or
         re.search(r"(?:^test_|[.]test[.]|[.]spec[.])", PurePosixPath(name).name))
        and name.endswith((".py", ".ts", ".js", ".mts", ".mjs")))[:12]
    if runtime == "unknown":
        return {"runtime": runtime, "preset": None, "runnable": False, "entry": None,
                "provider": None, "evaluation_files": evaluation_files,
                "setup": "Upload the runnable Python module or Node CLI and its dependency manifest."}
    if runtime == "typescript":
        if "package.json" not in files:
            return {"runtime": "typescript", "setup": "TypeScript execution is unavailable without a package.json declaring its runtime dependencies.",
                    "runnable": False, "preset": None, "entry": None, "provider": None, "dependencies": []}
        dependencies = package.get("dependencies", {})
        dependencies = sorted(dependencies) if isinstance(dependencies, dict) else []
        advertised = package.get("main")
        entry = advertised.removeprefix("./") if isinstance(advertised, str) else None
        if entry not in node_files:
            entry = node_files[0] if len(node_files) == 1 else None
        return {"runtime": "typescript", "setup": (
            "Supply an existing Node CLI entry file, its arguments, and train, validation and holdout cases. "
            "Use OPENAI_BASE_URL and OPENAI_MODEL with non-streaming Chat Completions."),
            "preset": None, "entry": entry, "provider": "Vercel AI SDK" if "ai" in dependencies else None,
            "dependencies": dependencies[:40], "evaluation_files": evaluation_files}
    else:
        setup = "Provide a Python module, its arguments, and train, validation, and holdout cases with exact expected stdout. The agent must use OPENAI_BASE_URL and OPENAI_MODEL, with streaming disabled."
    candidates = []
    if runtime == "python":
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            module = name[:-3].removesuffix("/__main__").replace("/", ".")
            if not all(part.isidentifier() for part in module.split(".")):
                continue
            content = read(name)
            if all(marker in content for marker in ("__main__", "OPENAI_BASE_URL", "OPENAI_MODEL")):
                candidates.append(module)
    entry = f"python -m {candidates[0]}" if len(candidates) == 1 else None
    declared = project.get("dependencies", [])
    dependencies = sorted({match.group() for requirement in declared
        if isinstance(requirement, str) and (match := re.match(r"[A-Za-z0-9_.-]+", requirement))}
        )[:40] if isinstance(declared, list) else []
    return {"runtime": runtime, "setup": setup, "preset": None,
            "provider": "OpenAI environment variables detected" if entry else None,
            "entry": entry, "dependencies": dependencies, "evaluation_files": evaluation_files}



def source_snapshot(archive, repository=None, revision=None):
    files = unpack(archive, github=repository is not None)
    return {"files": files, "source_sha256": fingerprint(files), "repository": repository,
            "revision": revision, "discovery": inspect(files)}
