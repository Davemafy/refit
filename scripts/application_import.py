"""Validate a bounded application snapshot without executing imported code."""
from __future__ import annotations

import base64
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import PurePosixPath
import re
import stat
import tomllib
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

from .migration_engine import fingerprint

ARCHIVE_LIMIT = 4 * 1024 * 1024
ZIP_UPLOAD_LIMIT = 32 * 1024 * 1024
TREE_BYTES = 8 * 1024 * 1024
TREE_LIMIT = 10000
SOURCE_FILE_LIMIT = 512 * 1024
EXPANDED_LIMIT = 12 * 1024 * 1024
FILE_LIMIT = 1500
REPOSITORY = re.compile(r"[a-zA-Z0-9_.-]{1,100}/[a-zA-Z0-9_.-]{1,100}")
REVISION = re.compile(r"[0-9a-f]{40}")
# Next.js uses these literal directory names for dynamic route segments.
ROUTE_SEGMENT = re.compile(r"\[(?:\.\.\.)?[A-Za-z0-9_-]+\]|\[\[\.\.\.[A-Za-z0-9_-]+\]\]")
BLOCKED_DIRS = {".git", ".ssh", ".aws", ".venv", "node_modules", "__pycache__"}


class ImportProblem(ValueError):
    pass


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


def github_read(url, token, limit, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ImportProblem("GitHub inspection timed out. Select an application subdirectory or fewer source files.")
    req = Request(url, headers={"User-Agent": "Refit application import"})
    if token:
        req.add_unredirected_header("Authorization", f"Bearer {token}")
    try:
        with build_opener(NoGitHubApiRedirect()).open(req, timeout=min(10, remaining)) as response:
            result = bytearray()
            while len(result) <= limit:
                if time.monotonic() >= deadline:
                    raise ImportProblem("GitHub inspection timed out. Select a smaller application scope.")
                chunk = response.read1(min(65536, limit + 1 - len(result)))
                if not chunk:
                    return bytes(result)
                result.extend(chunk)
        raise ImportProblem("GitHub returned more data than the inspection budget allows.")
    except HTTPError as exc:
        if exc.code in {403, 429}:
            raise ImportProblem("GitHub denied access or rate limited the import. Check the repository token or retry later.") from exc
        raise ImportProblem("GitHub source unavailable. Check the pinned revision and repository read access.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ImportProblem("GitHub source could not be read in time. Retry or select fewer source files.") from exc


def github_snapshot(repo, revision, token="", directory="", selected=None):
    """Read metadata first, then fetch and verify only selected Git blobs."""
    validate_repo_token(repo, token)
    if not isinstance(revision, str) or not REVISION.fullmatch(revision):
        raise ImportProblem("Provide the full 40-character GitHub commit SHA.")
    if not isinstance(directory, str):
        raise ImportProblem("Provide a repository-relative application directory.")
    if directory:
        directory = safe_path(directory).as_posix()
    if selected is not None:
        if not isinstance(selected, list) or not 1 <= len(selected) <= FILE_LIMIT:
            raise ImportProblem("Choose between 1 and 1,500 files relative to the application directory.")
        chosen = {safe_path(path).as_posix() for path in selected}
    else:
        chosen = None
    deadline = time.monotonic() + 90
    api = f"https://api.github.com/repos/{repo}/git"

    def tree(ref, recursive=False):
        # GitHub's public tree endpoint can briefly return an incomplete body.
        # Retry malformed responses only, with the original 90s deadline and
        # exact SHA/blob verification still enforced. Never accept fallback data.
        for attempt in range(3):
            try:
                result = json.loads(github_read(
                    f"{api}/trees/{ref}" + ("?recursive=1" if recursive else ""),
                    token, TREE_BYTES, deadline))
                rows = result["tree"]
                if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                    raise ValueError("invalid tree rows")
            except (TypeError, KeyError, ValueError) as exc:
                if attempt == 2 or deadline - time.monotonic() < 2:
                    raise ImportProblem("GitHub returned an invalid tree.") from exc
                time.sleep(0.25 * (attempt + 1))
                continue
            if result.get("truncated") or len(rows) > TREE_LIMIT:
                raise ImportProblem("The GitHub tree exceeds the inspection budget. Select an application subdirectory.")
            return rows

    try:
        commit = json.loads(github_read(f"{api}/commits/{revision}", token, 512 * 1024, deadline))
        ref = commit["tree"]["sha"]
        if commit["sha"] != revision or not isinstance(ref, str) or not REVISION.fullmatch(ref):
            raise ValueError
    except (TypeError, KeyError, ValueError) as exc:
        raise ImportProblem("GitHub did not return the requested pinned commit.") from exc
    if directory:
        for part in PurePosixPath(directory).parts:
            ref = next((row.get("sha") for row in tree(ref)
                        if row.get("path") == part and row.get("type") == "tree"), None)
            if not isinstance(ref, str) or not REVISION.fullmatch(ref):
                raise ImportProblem("The application directory does not exist at this commit.")
    rows = tree(ref, recursive=True)
    report = []
    blobs = {}
    seen = set()
    for row in rows:
        if row.get("type") == "tree":
            continue
        raw = row.get("path")
        try:
            path = safe_path(raw)
        except ImportProblem:
            if isinstance(raw, str):
                report.append(file_record(raw[:240], "unsupported", "Unsafe or unsupported path"))
            continue
        name = path.as_posix()
        if name in seen:
            raise ImportProblem("GitHub returned duplicate source paths.")
        seen.add(name)
        size = row.get("size")
        reason = None
        status = "excluded"
        if sensitive(path):
            reason = "Credentials or dependency cache"
        elif row.get("type") != "blob" or row.get("mode") not in {"100644", "100755"}:
            status, reason = "unsupported", "Symlink, submodule or special file"
        elif type(size) is not int or size < 0 or not REVISION.fullmatch(str(row.get("sha"))):
            raise ImportProblem("GitHub returned invalid source metadata.")
        elif chosen is None and (excluded := default_exclusion(path)):
            reason = excluded
        elif size > SOURCE_FILE_LIMIT:
            status, reason = "unsupported", "File exceeds the 512 KiB execution limit"
        elif chosen is not None and name not in chosen:
            reason = "Outside the explicit file selection"
        if reason:
            report.append(file_record(name, status, reason))
        else:
            blobs[name] = (size, row["sha"])
    if chosen is not None and (missing := sorted(chosen - blobs.keys())):
        reasons = {item["path"]: item["reason"] for item in report}
        first = missing[0]
        raise ImportProblem(f"Cannot import {first}: {reasons.get(first, 'not found at this commit')}.")
    check_source_budget(size for size, _ in blobs.values())

    def fetch(item):
        name, (size, sha) = item
        if token:
            try:
                data = json.loads(github_read(f"{api}/blobs/{sha}", token, size * 2 + 4096, deadline))
                if data["encoding"] != "base64":
                    raise ValueError
                content = base64.b64decode(data["content"])
            except (ValueError, KeyError, TypeError) as exc:
                raise ImportProblem(f"GitHub returned an unreadable blob for {name}.") from exc
        else:
            prefix = f"{directory}/" if directory else ""
            content = github_read(f"https://raw.githubusercontent.com/{repo}/{revision}/{quote(prefix + name)}",
                                  "", size, deadline)
        actual = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
        if len(content) != size or actual != sha:
            raise ImportProblem(f"GitHub content for {name} does not match the pinned tree.")
        return name, content

    files = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        items = sorted(blobs.items())
        for start in range(0, len(items), 6):
            for name, content in pool.map(fetch, items[start:start + 6]):
                if content.startswith(b"version https://git-lfs.github.com/spec/v1\n"):
                    if chosen is not None:
                        raise ImportProblem(f"Cannot import {name}: Git LFS content is unsupported.")
                    report.append(file_record(name, "unsupported", "Git LFS pointer"))
                    continue
                files[name] = base64.b64encode(content).decode("ascii")
                report.append(file_record(name, "included", "Selected explicitly" if chosen else "Application source"))
    return make_snapshot(files, repo, revision, directory, report)


def safe_path(name):
    if not isinstance(name, str) or len(name) > 240 or "\\" in name or "\x00" in name:
        raise ImportProblem("The archive contains an invalid file path.")
    path = PurePosixPath(name)
    if (not path.parts or len(path.parts) > 24 or path.is_absolute() or ".." in path.parts
            or any(not re.fullmatch(r"[\w.@+() -]+", part) and not ROUTE_SEGMENT.fullmatch(part)
                   for part in path.parts)):
        raise ImportProblem("The archive contains an unsafe file path.")
    return path


def sensitive(path):
    name = path.name.lower()
    return (any(part.lower() in BLOCKED_DIRS for part in path.parts)
            or (name.startswith(".env") and name not in {".env.example", ".env.sample"})
            or name in {"id_rsa", "id_ed25519", "credentials.json", "secrets.json", ".npmrc", ".pypirc"}
            or name.endswith((".key", ".pem", ".p12", ".pfx")))


def default_exclusion(path):
    folders = {part.lower() for part in path.parts[:-1]}
    if folders & {"build", "dist", "out", "target", "coverage", ".next", ".nuxt", ".cache",
                  ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", "vendor"}:
        return "Build output, cache or vendored dependencies"
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".mp4", ".mov",
                               ".mp3", ".wav", ".pdf", ".zip", ".gz", ".tar", ".jar", ".woff",
                               ".woff2", ".ttf", ".otf", ".exe", ".dll", ".so", ".dylib", ".pyc",
                               ".wasm", ".safetensors", ".onnx", ".pkl"}:
        return "Asset or binary excluded by default"
    return None


def file_record(path, status, reason):
    return {"path": path, "status": status, "reason": reason}


def check_source_budget(sizes):
    sizes = list(sizes)
    if not sizes:
        raise ImportProblem("No runnable source was selected. Choose an application directory or its source files.")
    if len(sizes) > FILE_LIMIT or sum(sizes) > EXPANDED_LIMIT:
        raise ImportProblem("The selected source exceeds 1,500 files or 12 MiB. Choose an application directory or select the files it needs.")


def unpack_zip(archive):
    """Read only eligible members from a seekable, bounded ZIP spool."""
    files = {}
    report = []
    try:
        # Bound the central directory before ZipFile allocates one object per member.
        end = zipfile._EndRecData(archive)
        if end and (end[zipfile._ECD_SIZE] > 4 * 1024 * 1024 or end[zipfile._ECD_ENTRIES_TOTAL] > TREE_LIMIT):
            raise ImportProblem("The ZIP directory exceeds the inspection budget. Upload the application directory.")
        with zipfile.ZipFile(archive) as zipped:
            entries = zipped.infolist()
            if len(entries) > TREE_LIMIT:
                raise ImportProblem("The ZIP contains more than 10,000 entries. Upload the application directory.")
            candidates = {}
            seen = set()
            for entry in entries:
                path = safe_path(entry.orig_filename)
                mode = stat.S_IFMT(entry.external_attr >> 16)
                if mode not in (0, stat.S_IFREG, stat.S_IFDIR) or entry.flag_bits & 1:
                    raise ImportProblem("Symlinks, special files and encrypted files are not supported.")
                if entry.is_dir():
                    continue
                name = path.as_posix()
                if name in seen:
                    raise ImportProblem("Duplicate archive paths are not supported.")
                seen.add(name)
                if any(part.lower() in {"node_modules", ".venv", "__pycache__"} for part in path.parts[:-1]):
                    report.append(file_record(name, "excluded", "Dependency directory or cache"))
                    continue
                if sensitive(path):
                    raise ImportProblem("Remove credentials, private keys and dependency caches from the snapshot.")
                reason = default_exclusion(path)
                if reason:
                    report.append(file_record(name, "excluded", reason))
                    continue
                if entry.file_size > SOURCE_FILE_LIMIT:
                    if path.suffix.lower() in {".md", ".rst"}:
                        report.append(file_record(name, "unsupported", "Documentation exceeds 512 KiB"))
                        continue
                    raise ImportProblem(f"{name} exceeds the 512 KiB per-source-file limit.")
                candidates[name] = entry
            check_source_budget(entry.file_size for entry in candidates.values())
            for name, entry in sorted(candidates.items()):
                with zipped.open(entry) as stream:
                    content = stream.read(entry.file_size + 1)
                if len(content) != entry.file_size:
                    raise ImportProblem("The ZIP contains inconsistent file sizes.")
                files[name] = base64.b64encode(content).decode("ascii")
                report.append(file_record(name, "included", "Application source"))
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError) as exc:
        raise ImportProblem("The uploaded file is not a readable supported ZIP.") from exc
    return make_snapshot(files, None, None, "", report)


def inspect(files):
    def read(name):
        return base64.b64decode(files.get(name, "")).decode("utf-8", "replace")

    manifests = {}
    for name in sorted(files):
        path = PurePosixPath(name)
        if path.name not in {"package.json", "pyproject.toml", "requirements.txt"}:
            continue
        runtime = "typescript" if path.name == "package.json" else "python"
        try:
            if path.name == "package.json":
                metadata = json.loads(read(name))
                dependencies = sorted(metadata.get("dependencies", {}))
            elif path.name == "pyproject.toml":
                metadata = tomllib.loads(read(name)).get("project", {})
                dependencies = metadata.get("dependencies", [])
            else:
                metadata = {}
                dependencies = read(name).splitlines()
            dependencies = sorted({match.group() for item in dependencies if isinstance(item, str)
                                   and (match := re.match(r"[@a-zA-Z0-9_][@a-zA-Z0-9_./-]*", item))})
        except (ValueError, AttributeError, TypeError):
            metadata, dependencies = {}, []
        key = (path.parent, runtime)
        if key in manifests:
            prior_name, prior_metadata, prior_dependencies = manifests[key]
            manifests[key] = (prior_name, prior_metadata, sorted(set(prior_dependencies + dependencies)))
        else:
            manifests[key] = (name, metadata, dependencies)
    _, project, _ = manifests.get((PurePosixPath("."), "python"), (None, {}, []))
    if project.get("name") == "llm" and project.get("version") == "0.37.1" and "llm/__main__.py" in files:
        return {"runtime": "python", "setup": None, "preset": "llm-0.37.1",
                "provider": "OpenAI-compatible Chat Completions",
                "entry": "python -m llm", "tool": "llm_version",
                "evaluation": "Exact stdout and observed original llm_version tool result"}

    evaluation_files = [name for name in sorted(files) if name.endswith((".py", ".ts", ".js", ".mts", ".mjs"))
                        and (set(PurePosixPath(name).parts[:-1]) & {"test", "tests", "__tests__"}
                             or re.search(r"(?:^test_|[.]test[.]|[.]spec[.])", PurePosixPath(name).name))]
    evaluation_inputs = [name for name in sorted(files)
                         if set(PurePosixPath(name).parts[:-1]) & {"eval", "evals", "evaluation"}
                         and PurePosixPath(name).suffix in {".json", ".jsonl"}]
    service_entries = []
    candidates = []
    observed_runtimes = set()
    for name in sorted(files):
        path = PurePosixPath(name)
        if path.suffix == ".py":
            runtime = "python"
        elif path.suffix in {".ts", ".mts", ".js", ".mjs", ".tsx"} and not name.endswith(".d.ts"):
            runtime = "typescript"
        else:
            continue
        observed_runtimes.add(runtime)
        if name in evaluation_files:
            continue
        scope = next((parent for parent in path.parents if (parent, runtime) in manifests), PurePosixPath("."))
        manifest, metadata, dependencies = manifests.get((scope, runtime), (None, {}, []))
        content = read(name)
        if runtime == "typescript" and "next" in dependencies:
            relative = path.relative_to(scope).parts
            offset = 2 if relative[:2] == ("src", "app") else 1 if relative[:1] == ("app",) else 0
            if (offset and len(relative) > offset + 1 and path.stem == "route"
                    and re.search(r"\bexport\s+(?:(?:async\s+)?function|const)\s+POST\b", content)):
                route = "/" + "/".join(part for part in relative[offset:-1]
                                       if not (part.startswith("(") and part.endswith(")")))
                service_entries.append({"path": name, "route": route, "method": "POST", "manifest": manifest})
        provider = None
        if "OPENAI_BASE_URL" in content and "OPENAI_MODEL" in content:
            provider = "OpenAI environment variables detected"
        elif runtime == "typescript" and "ai" in dependencies:
            provider = "Vercel AI SDK"
        elif "litellm" in dependencies:
            provider = "LiteLLM dependency detected"
        elif "anthropic" in dependencies:
            provider = "Anthropic SDK detected"
        elif "openai" in dependencies or "@ai-sdk/openai" in dependencies:
            provider = "OpenAI SDK detected"
        evidence = []
        if runtime == "python":
            if path.name != "__main__.py" and not re.search(r"""__name__\s*==\s*["']__main__["']""", content):
                continue
            module = name[:-3].removesuffix("/__main__").replace("/", ".")
            if not all(part.isidentifier() for part in module.split(".")):
                continue
            entry = f"python -m {module}"
            evidence.append("Python main guard or package entry")
            if any(marker in content for marker in ("argparse", "sys.argv", "click", "typer")):
                evidence.append("CLI input detected")
        else:
            if not manifest or path.suffix == ".tsx":
                continue
            entry = name
            declared = [metadata.get("main"), metadata.get("bin")]
            if isinstance(metadata.get("bin"), dict):
                declared.extend(metadata["bin"].values())
            if any(isinstance(item, str) and scope / item == path for item in declared):
                evidence.append("Package declares this entry")
            elif "process.argv" in content:
                evidence.append("CLI input detected")
            elif path.stem in {"agent", "cli", "invoke", "main"} and provider:
                evidence.append("Agent entry filename and provider dependency")
            else:
                continue
        if provider:
            evidence.append(provider)
        confidence = "high" if provider and any("CLI input" in item or "declares" in item for item in evidence) else "possible"
        candidates.append({"path": name, "entry": entry, "runtime": runtime,
                           "directory": "" if str(scope) == "." else str(scope),
                           "manifest": manifest, "dependencies": dependencies[:40],
                           "provider": provider, "confidence": confidence, "evidence": evidence})
    service_manifests = {entry["manifest"] for entry in service_entries}
    candidates = [candidate for candidate in candidates if candidate["manifest"] not in service_manifests]
    service_entries.sort(key=lambda entry: (
        entry["route"].rsplit("/", 1)[-1] not in {"turn", "chat", "agent", "invoke", "run"},
        entry["route"], entry["path"]))
    evaluation_files.sort(key=lambda name: (
        not re.search(r"eval(?:uation)?", PurePosixPath(name).name, re.I),
        bool(set(PurePosixPath(name).parts) & {"browser", "e2e"}) or ".e2e." in name,
        name))
    likely = [candidate for candidate in candidates if candidate["confidence"] == "high"]
    chosen = likely[0] if len(likely) == 1 else candidates[0] if len(candidates) == 1 else None
    runtime = chosen["runtime"] if chosen else (
        next(iter(observed_runtimes)) if len(observed_runtimes) == 1 else "mixed" if observed_runtimes else "unknown")
    result = {"runtime": runtime, "preset": None, "entry": chosen["entry"] if chosen else None,
              "provider": chosen["provider"] if chosen else None,
              "dependencies": chosen["dependencies"] if chosen else [],
              "applications": candidates[:40], "evaluation_files": evaluation_files[:12],
              "setup": "Choose the original entry point and configure non-streaming Chat Completions and independent cases."}
    if service_entries:
        result["service_entries"] = service_entries[:8]
    if evaluation_inputs:
        result["evaluation_inputs"] = evaluation_inputs[:8]
    if service_entries and not candidates:
        _, metadata, dependencies = manifests[(PurePosixPath(service_entries[0]["manifest"]).parent, "typescript")]
        result.update(
            runtime="typescript", framework="Next.js", runnable=False, dependencies=dependencies[:40],
            setup="This source exposes a Next.js HTTP service. Managed execution needs a standalone Node "
                  "entry with a supported Chat Completions boundary. Import a standalone adapter with "
                  "supported dependencies, or expose a compatible isolated test endpoint for the local connector.")
        node = metadata.get("engines")
        if isinstance(node, dict) and isinstance(node.get("node"), str):
            result["node_requirement"] = node["node"][:80]
        return result
    if runtime == "unknown" or (runtime == "typescript" and not any(lang == runtime for _, lang in manifests)):
        result["runnable"] = False
        result["setup"] = ("TypeScript execution is unavailable without a package.json declaring runtime dependencies."
                           if runtime == "typescript" else "Import a runnable Python module or Node CLI.")
    if runtime == "typescript" and not chosen:
        node = [name for name in files if name.endswith((".ts", ".mts", ".js", ".mjs")) and not name.endswith(".d.ts")]
        if len(node) == 1:
            result["entry"] = node[0]
            result["dependencies"] = manifests.get((PurePosixPath("."), runtime), (None, {}, []))[2][:40]
            if "ai" in result["dependencies"]:
                result["provider"] = "Vercel AI SDK"
    return result


def discover_source_signals(files):
    imports = set()
    providers = set()
    entry_points = []
    configs = []
    for name, encoded in sorted(files.items()):
        path = PurePosixPath(name)
        if path.name in {"package.json", "pyproject.toml", "requirements.txt", "poetry.lock",
                         "uv.lock", "package-lock.json", "tsconfig.json", ".env.example", ".env.sample"}:
            configs.append(name)
        if path.suffix not in {".py", ".ts", ".mts", ".js", ".mjs"}:
            continue
        source = base64.b64decode(encoded).decode("utf-8", "replace")
        for name_hint in ("OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                          "GOOGLE_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "GROK_API_KEY", "LLM_API_KEY"):
            if name_hint in source:
                providers.add(name_hint)
        if path.suffix == ".py":
            imports.update(re.findall(r"^[ \t]*(?:from|import)[ \t]+([.\w]+)", source, re.MULTILINE))
            if path.name == "__main__.py" or re.search(r"""__name__\s*==\s*["']__main__["']""", source):
                entry_points.append(name)
        else:
            imports.update(re.findall(r"""(?:from\s+|import\s*\(\s*|require\s*\(\s*)["']([^"'\n]{1,160})["']""", source))
            if path.stem in {"main", "cli", "agent", "index"}:
                entry_points.append(name)
    return {"imports": sorted(imports)[:40], "provider_signals": sorted(providers),
            "entry_candidates": entry_points[:30], "configuration_files": configs[:30]}


def make_snapshot(files, repository, revision, directory, report):
    if not files or any(str(parent) in files for name in files for parent in PurePosixPath(name).parents):
        raise ImportProblem("The selected source is empty or has conflicting paths.")
    content_id = fingerprint(files)
    identity = {"source_sha256": content_id, "repository": repository,
                "revision": revision, "directory": directory}
    discovery = inspect(files)
    discovery.update(discover_source_signals(files))
    return {**identity, "snapshot_sha256": fingerprint(identity), "discovery": discovery,
            "files": files, "selection_counts": dict(Counter(row["status"] for row in report)),
            "source_report": sorted(report, key=lambda row: (row["status"], row["path"]))}


def source_snapshot(archive):
    """Compatibility entry point for older clients and existing fixtures."""
    if not archive:
        raise ImportProblem("The uploaded ZIP is empty.")
    if len(archive) > ARCHIVE_LIMIT:
        raise ImportProblem("The uploaded ZIP is larger than 4 MiB. Use the streaming ZIP upload for larger files.")
    return unpack_zip(io.BytesIO(archive))
