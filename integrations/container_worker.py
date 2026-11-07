"""Container-only adapter loader. No inference key or network is required."""
import importlib
import json
import os
import sys
import traceback

from scripts.migration_engine import migrate
from scripts.compatibility_artifact import create_receipt, digest, profile_details

WIRE = sys.stdout


def emit(value):
    data = (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    sent = 0
    # Unbuffered TextIO can lose the unwritten suffix when the runtime's
    # stdout pipe accepts only part of a large write (observed at 65,536 bytes).
    while sent < len(data):
        try:
            written = os.write(WIRE.fileno(), data[sent:sent + 16384])
        except InterruptedError:
            continue
        if written <= 0:
            raise RuntimeError('Worker output pipe closed')
        sent += written
    if value.get('type') == 'result':
        # Keep the container's attached stream alive until the host has read
        # the complete final frame, including large native transcripts.
        acknowledgment = json.loads(sys.stdin.readline())
        if acknowledgment.get('type') != 'result_ack':
            raise RuntimeError('Host did not acknowledge complete result')


class BrokerClient:
    def __init__(self):
        self.requests = 0

    def complete(self, model, messages, tools=None, **kwargs):
        emit({"type": "completion", "model": model, "messages": messages, "tools": tools})
        reply = json.loads(sys.stdin.readline())
        if reply.get("type") != "completion_result":
            raise RuntimeError("host rejected completion request")
        self.requests += 1
        if reply.get("error"):
            raise RuntimeError(reply["error"])
        return reply["message"]

    def evaluate_patch(self, partition, patch):
        emit({"type": "evaluate_patch", "partition": partition, "patch": patch})
        reply = json.loads(sys.stdin.readline())
        if reply.get("type") != "patch_evaluation":
            raise RuntimeError("host rejected patch evaluation")
        return reply["evaluation"]

    def record_case(self, result):
        emit({"type": "case_result", "case": result})


def main():
    config = json.loads(sys.stdin.readline())
    # Imported repositories and adapter modules are loaded ONLY here, inside
    # the networkless container. stdout is reserved for bounded host RPC.
    sys.stdout = sys.stderr
    adapter = importlib.import_module(config["adapter"])
    contract, baseline, metadata = adapter.describe(config)
    emit({"type": "description", "contract": contract.name, "metadata": metadata,
          "baseline": profile_details(baseline), "tools": contract.tools})
    if config.get("inspect_only"):
        emit({"type": "result", "status": "inspected", "metadata": metadata})
        return
    client = BrokerClient()
    if config.get('verify_export') is not None:
        exported = config['verify_export']
        verification = adapter.verify_export(client, config, exported)
        emit({'type': 'result', 'status': ('export_verified_original_runner' if verification['passed']
                                         else 'export_failed_original_runner_verification'),
              'verified': verification['passed'], 'report': {'evaluations': {}},
              'export': exported if verification['passed'] else None,
              'original_runner_verification': verification, 'metadata': metadata,
              'model_requests': client.requests})
        return
    report = migrate(
        client, contract, config["source"], config["target"], config["source"], baseline,
        adapter.cases(config, "train"),
        lambda: adapter.cases(config, "validation"),
        lambda: adapter.cases(config, "holdout"),
        progress=lambda event, details: emit({"type": "progress", "event": event, "details": details}),
    )
    status = report["status"]
    accepted = status in ("verified_adaptation", "compatible_on_sample")
    export = None
    original_runner = None
    if accepted:
        if status == "verified_adaptation":
            receipt = create_receipt(report, contract, baseline, config["source"], config["target"])
            profile = receipt["target_profile"]
        else:
            receipt = None
            profile = profile_details(baseline)
        export = {"format": "refit.native-config.v1", "repository": config["repository"],
                  "revision": config["revision"], "adapter": config["adapter"],
                  "domain": config["domain"], "model": config["target"],
                  "baseline_sha256": digest(profile_details(baseline)),
                  "contract_sha256": report["contract_sha256"],
                  "target_profile": profile, "migration_status": status,
                  "compatibility_receipt": receipt}
        export["integrity_sha256"] = digest(export)
        # Load the exact exported bytes through the deployment helper and run
        # the complete original runner again. No optimization occurs here.
        original_runner = adapter.verify_export(client, config, json.loads(json.dumps(export)))
        if not original_runner["passed"]:
            accepted = False
            export = None
            status = "export_failed_original_runner_verification"
    emit({"type": "result", "status": status, "report": report,
          "metadata": metadata, "export": export,
          "original_runner_verification": original_runner,
          "model_requests": client.requests, "verified": accepted})


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        traceback.print_exc(file=sys.stderr)
        emit({"type": "result", "status": "execution_error", "verified": False,
              "error_type": type(error).__name__})
        sys.exit(1)
