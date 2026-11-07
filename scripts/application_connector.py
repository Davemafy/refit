"""Run a developer-authorized Python agent and broker its model calls locally."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid

from .application_cli import write_local_zip
from .application_import import unpack_zip
from .application_run import BUDGET_LIMIT, MODELS, RunStopped, configuration, run_migration, validate_application_cases
from .migration_engine import fingerprint
from .refit_vultr_probe import VultrInference


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, nargs="?")
    parser.add_argument("--test-service", help="Authorized loopback HTTP endpoint in an isolated test environment")
    parser.add_argument("--service-revision", help="Developer-declared identity of the running test service")
    parser.add_argument("--allow-isolated-test-service", action="store_true",
                        help="Authorize calls and confirm the endpoint starts each invocation with fresh test state")
    parser.add_argument("--setup", type=Path, required=True)
    parser.add_argument("--source", choices=MODELS, default=MODELS[0])
    parser.add_argument("--target", choices=MODELS, default=MODELS[1])
    parser.add_argument("--python", type=Path, default=Path(sys.executable),
                        help="Absolute interpreter path, including a prepared virtual environment")
    parser.add_argument("--allow-local-execution", action="store_true",
                        help="Authorize trusted project code to execute on this machine without gVisor")
    parser.add_argument("--authorize-requests", type=int, choices=range(1, BUDGET_LIMIT + 1), required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "linux" or bool(args.test_service) == bool(args.project):
        parser.error("Choose either a Linux local project or an isolated loopback test service.")
    if args.test_service:
        if not args.allow_isolated_test_service or not args.service_revision or len(args.service_revision) > 128:
            parser.error("Confirm fresh test state with --allow-isolated-test-service and supply --service-revision.")
    elif not args.allow_local_execution:
        parser.error("Authorize trusted project code with --allow-local-execution.")
    if args.source == args.target:
        parser.error("Choose distinct source and target models.")
    key = os.environ.get("VULTR_INFERENCE_API_KEY")
    if not key:
        parser.error("Set VULTR_INFERENCE_API_KEY for the local broker.")
    supplied = json.loads(args.setup.read_text())
    if args.test_service:
        if not isinstance(supplied, dict) or set(supplied) != {"cases"}:
            parser.error("Service setup contains only cases.")
        validate_application_cases(supplied["cases"])
        identity = fingerprint({"test_service": args.test_service, "revision": args.service_revision})
        snapshot = {"source_sha256": identity, "snapshot_sha256": identity, "revision": args.service_revision,
                    "repository": None, "files": {}}
        setup = {**supplied, "args": [], "seam": "openai-env"}
        mode = "existing_test_service"
    else:
        with tempfile.TemporaryFile() as archive:
            write_local_zip(archive, args.project, args.setup.resolve())
            archive.seek(0)
            snapshot = unpack_zip(archive)
        setup = configuration(snapshot, supplied)
        mode = "local_connector"
    broker = VultrInference(key, max_requests=args.authorize_requests)
    evidence = {"id": "local-" + uuid.uuid4().hex, "execution_mode": mode,
                "isolation": "developer_host", "source": args.source, "target": args.target,
                "snapshot_sha256": snapshot["snapshot_sha256"], "request_ceiling": broker.max_requests,
                "events": []}

    def record(event, detail):
        evidence["events"].append({"type": event, "details": detail})

    descriptor = os.open(args.evidence, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        try:
            evidence.update(run_migration(snapshot, setup, args.source, args.target, None, broker,
                                          record, lambda: False,
                                          local_python=None if args.test_service else str(args.python),
                                          test_service=args.test_service,
                                          service_bearer=os.environ.get("REFIT_SERVICE_BEARER")))
        except KeyboardInterrupt:
            evidence.update(status="cancelled", export=None)
        except (RunStopped, RuntimeError, ValueError, OSError) as exc:
            evidence.update(status="execution_stopped", error=str(exc)[:240], export=None)
        evidence["model_requests"] = broker.requests
        json.dump(evidence, output, indent=2)
        output.write("\n")
    print(json.dumps({key: evidence[key] for key in ("id", "status", "model_requests")}))
    return 0 if evidence.get("export") else 1


if __name__ == "__main__":
    sys.exit(main())
