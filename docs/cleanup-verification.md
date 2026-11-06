# Container cleanup evidence

Both generated-code execution and tool-worker sessions use one shared Docker
cleanup verifier. A failed `docker inspect` is not evidence of removal.

Approval requires all three observations:

1. Forced removal succeeds, or Docker explicitly identifies that exact owned
   container as already absent (the expected race with `--rm`).
2. `docker container inspect` returns the specific missing-container response
   for the same name. Generic errors, a different container name, permission
   failures, unexpected output and timeouts remain unverified.
3. A subsequent `docker info` succeeds and returns a valid daemon identity.

The launch and cleanup commands use the same environment, preserving their
Docker connection settings. Each operation has an eight-second timeout. There
are no automatic retries, runtime changes or daemon-context fallbacks. A removal
timeout is conservatively unverified even if a later inspection reports absence.

Generated-code results carry the removal, inspection and daemon-health evidence
inside their hash-chained ledger. Failed cleanup changes the execution status to
`cleanup_unverified`. Creation requires Docker's 64-character container ID
receipt, rather than inferring creation from a host process exit code.

Tool workers record the same cleanup evidence. A failure raises and blocks
migration approval; repeated `close()` cannot silently clear that failure.
Even a failed host-side process shutdown still attempts container removal.

Tool exchanges have one eight-second deadline covering request writes and the
entire newline-terminated reply. Nonblocking pipe I/O prevents a partial line,
continuous byte trickle, or a worker that stops reading from holding the
operator indefinitely. The same deadline is capped by the session lifetime.
Transport failure follows the existing worker cleanup path; it cannot approve
a migration.

## Verify on the actual Vultr host

From the existing authorized host session, use the current `main` checkout:

```bash
cd /opt/refit-app
git pull --ff-only
bash deploy/verify-gvisor-on-host.sh
```

This makes no inference calls. It executes safe and hostile probes through
`runsc`, records the image digest, independently recomputes the event chain and
expected code digests, and makes fresh Docker cleanup observations. The report
includes environment information, both execution reports, separate cleanup
rechecks, a verification manifest and checksums.

Capture that host's resulting report directory before claiming host-specific
containment. Passing the same tests on GitHub establishes runner containment
only. Checksums detect modification; they are not authenticated host attestation
or a cryptographic signature proving report origin.
