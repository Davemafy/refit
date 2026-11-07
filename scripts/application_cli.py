"""Import a local project into your own loopback Refit operator service."""
import argparse
import base64
import io
import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

from .application_import import ARCHIVE_LIMIT, EXPANDED_LIMIT, FILE_LIMIT, sensitive
from .application_run import MODELS


def local_zip(path):
    if not path.is_dir():
        raise ValueError("Project must be a directory.")
    buffer = io.BytesIO()
    total = count = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for directory, subdirs, files in os.walk(path):
            root = Path(directory)
            subdirs[:] = [name for name in subdirs if not (root / name).is_symlink()
                          and not sensitive((root / name).relative_to(path))]
            for name in files:
                file = root / name
                relative = file.relative_to(path)
                if file.is_symlink() or sensitive(relative) or not file.is_file():
                    continue
                size = file.stat().st_size
                total += size
                count += 1
                if size > 512 * 1024 or total > EXPANDED_LIMIT or count > FILE_LIMIT:
                    raise ValueError("Select a smaller project directory.")
                archive.write(file, relative.as_posix())
    if buffer.tell() > ARCHIVE_LIMIT:
        raise ValueError("Project ZIP exceeds 4 MiB.")
    return base64.b64encode(buffer.getvalue()).decode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--port", type=int, default=8098)
    parser.add_argument("--source", choices=MODELS, default=MODELS[0])
    parser.add_argument("--target", choices=MODELS, default=MODELS[1])
    parser.add_argument("--setup", type=Path)
    parser.add_argument("--authorize-requests", type=int)
    parser.add_argument("--export", type=Path)
    args = parser.parse_args()
    token = os.environ.get("REFIT_APPLICATION_TOKEN", "")
    if not token:
        parser.error("Set REFIT_APPLICATION_TOKEN for your local service.")

    def api(path, payload=None):
        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(f"http://127.0.0.1:{args.port}/api/application" + path, data=body,
                          headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            raise ValueError(json.load(error)["error"]["message"]) from error

    try:
        imported = api("/imports", {"method": "zip", "archive": local_zip(args.project)})
        print(json.dumps(imported), flush=True)
        if args.authorize_requests is None:
            return
        request = {"import_id": imported["id"], "source": args.source, "target": args.target,
                   "budget": args.authorize_requests, "authorize": True}
        if args.setup:
            request["setup"] = json.loads(args.setup.read_text())
        run = api("/runs", request)
        route = "/runs/" + run["id"]
        print(run["id"], file=sys.stderr, flush=True)
        try:
            while run["status"] in {"running", "cancelling"}:
                time.sleep(1)
                run = api(route)
        except KeyboardInterrupt:
            api(route + "/cancel", {})
            raise SystemExit("Cancellation requested.")
        print(json.dumps(run))
        if not run["export_available"]:
            raise SystemExit(1)
        if args.export:
            with args.export.open("x") as file:
                json.dump(api(route + "/artifact"), file, indent=2)
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
