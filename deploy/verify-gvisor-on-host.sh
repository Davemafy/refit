#!/usr/bin/env bash
# Prove actual runsc isolation on the target host; use no inference credentials.
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077

command -v runsc >/dev/null || { echo "runsc missing; install first" >&2; exit 2; }
command -v docker >/dev/null || { echo "Docker missing" >&2; exit 2; }
command -v python3 >/dev/null || { echo "Python missing" >&2; exit 2; }

# Do not modify the system default runtime.
docker info --format '{{json .Runtimes}}' | grep -q '"runsc"' || {
  echo "runsc not registered as Docker runtime" >&2; exit 2;
}

OUT_DIR="${REFIT_EVIDENCE_DIR:-/var/lib/refit/evidence}"
mkdir -p "${OUT_DIR}"
chmod 700 "${OUT_DIR}"
RUN_DATE="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_DIR="${OUT_DIR}/gvisor-${RUN_DATE}"
mkdir -m 700 "${REPORT_DIR}"

{
  echo "timestamp_utc=${RUN_DATE}"
  echo "git_commit=$(git rev-parse HEAD)"
  echo "host_arch=$(uname -m)"
  echo "docker_version=$(docker --version)"
  echo "runsc_version=$(runsc --version | head -n1)"
  echo "registered_docker_runtimes=$(docker info --format '{{json .Runtimes}}')"
} > "${REPORT_DIR}/environment.txt"

docker pull python:3.11-alpine >/dev/null
docker image inspect python:3.11-alpine --format \
  '{"id":{{json .Id}},"repo_digests":{{json .RepoDigests}},"architecture":{{json .Architecture}},"os":{{json .Os}}}' \
  > "${REPORT_DIR}/image.json"
python3 -m scripts.sandbox_runner --fixture safe --runtime runsc   > "${REPORT_DIR}/safe.json"
python3 -m scripts.sandbox_runner --fixture hostile --runtime runsc   > "${REPORT_DIR}/hostile.json"

python3 - "${REPORT_DIR}" <<'PY'
import json
import hashlib
import os
from pathlib import Path
import sys
from scripts.sandbox_runner import verify_chain, SAFE_PROBE, HOSTILE_PROBE
from scripts.docker_cleanup import remove_and_verify

root = Path(sys.argv[1])
verification = {"probes": {}}
for name in ("safe", "hostile"):
    r = json.loads((root / f"{name}.json").read_text())
    assert r["runtime"] == "runsc", r
    assert r["container_created"] and r["container_removed_verified"], r
    assert r["status"] == "passed" and verify_chain(r["ledger"]), r
    expected_code = SAFE_PROBE if name == "safe" else HOSTILE_PROBE
    assert r["code_sha256"] == hashlib.sha256(expected_code.encode()).hexdigest()
    assert r["container_id"] and len(r["container_id"]) == 64
    original_cleanup = r["cleanup_evidence"]
    assert r["ledger"][-1]["event"]["evidence"] == original_cleanup
    # Fresh host-side observation, independent of the report's cached flag.
    recheck = remove_and_verify("docker", original_cleanup["container_name"], env=os.environ.copy())
    (root / f"cleanup-recheck-{name}.json").write_text(json.dumps(recheck, indent=2) + "\n")
    assert recheck["verified"], recheck
    assert recheck["daemon_id"] == original_cleanup["daemon_id"], "Docker daemon identity changed"
    if name == "safe":
        assert json.loads(r["stdout"])["regression_detected"] is True
    else:
        p = json.loads(r["stdout"])
        assert p["key_file"] == "FileNotFoundError", p
        assert p["key_in_env"] is False, p
        assert p["dns"] != "unexpectedly_resolved", p
        assert p["outbound_connection"] != "unexpectedly_connected", p
        assert p["root_write"] != "unexpectedly_writable", p
    print(f"{name}: execution passed on {r['runtime']}, {r['duration_ms']}ms")
    verification["probes"][name] = {"ledger_recomputed": True,
                                    "expected_code_digest_matches": True,
                                    "fresh_cleanup_recheck_passed": True,
                                    "daemon_identity_matches": True}
(root / "verification.json").write_text(json.dumps(verification, indent=2) + "\n")
print("Host containment evidence verified. This does not verify full agent isolation.")
PY

(cd "${REPORT_DIR}" && sha256sum environment.txt image.json safe.json hostile.json \
  cleanup-recheck-safe.json cleanup-recheck-hostile.json verification.json) > "${REPORT_DIR}/sha256sums.txt"
echo "EVIDENCE: ${REPORT_DIR}"
echo "This is Vultr-host evidence only when executed on the actual Vultr VM."
