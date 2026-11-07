# Engineering architecture

Refit migrates existing tool-using agents between language models and verifies supported behavioral outcomes before releasing an export. **Generality is the architectural goal, not the current compatibility claim.** The production-verified self-service path is managed Python 3.11 with non-streaming OpenAI-compatible Chat Completions. The reviewed Node runtime passed a paid migration of the pinned AI SDK 7 file agent.

Specialized refund and retail integrations run their original tools and stateful evaluators. The general imported-application pipeline has a narrower trusted evaluation contract. Details and evidence: [README](../README.md), [Bring Your Agent](bring-your-agent.md), and [framework verification](framework-evidence-2026-11-06.md).

## Runtime components

| Component | Responsibility and boundary |
| --- | --- |
| HTTPS ingress | Nginx terminates TLS and applies login limits. The account-backed Python service listens on loopback. The separate public HTTP evidence site serves read-only published results. |
| Account and evidence store | SQLite-backed accounts, sessions and imported project snapshots; durable run records, quotas and owner-scoped events/evidence/exports. |
| Trusted controller | Chooses models, invokes the Vultr Serverless Inference API, schedules gVisor workers, records trace and cleanup evidence, and holds credentials outside untrusted execution. |
| Original application worker | Executes selected source under Docker's `runsc` (gVisor) runtime with no external network, a read-only root, non-root UID, dropped capabilities, resource limits and constrained temporary storage. Its loopback model proxy forwards requests to the trusted controller. |
| Trusted evaluator | Checks declared outcomes outside the imported source container and gates exports on independent verification. Specialized agent integrations additionally check stateful business invariants. |
| Export verifier | Restarts an original-runtime process with the exported model configuration and independently rechecks protected cases. A failed check withholds export. |

The application API process runs as a dedicated non-root Linux account **with Docker-group membership**. Docker control is privileged even from a non-root account. Thus the trusted control plane is **not** itself contained by gVisor. Separating its HTTP and container-management privileges is a remaining security objective.

## Ingestion and execution

1. Resolve the requested GitHub revision to a full commit SHA, inspect its tree, select application files and verify their Git blob IDs. Alternatively, stream a bounded ZIP and inspect eligible source members.
2. Exclude known credentials, unsafe paths, symlinks, build products and large irrelevant assets. Preserve selected-source provenance and inclusion/exclusion reports.
3. Discover candidate agent boundaries from source and dependency metadata. A developer confirms the entry point, model seam and independent evaluation cases.
4. Execute the original program in a fresh gVisor container, routing approved model requests through the host Vultr broker. Re-run source and replacement models under comparable declared inputs.
5. Check outputs, JSON fields, tool-use observations and applicable sandbox-local file-state effects. The source does not receive the expected outcomes or protected holdout definitions.
6. Where the replacement fails, propose a bounded adaptation **only** through an original-application model-facing seam that has been explicitly declared and authorized. Reject unsupported patches.
7. Re-run validation and holdout. Export only after fresh original-runtime verification succeeds. Distinguish an unchanged compatible model switch from a genuine verified repair.

## Evaluation is not universal state attestation

The general importer can check exact stdout, JSON field subsets, model-requested tool names and arguments, subsequent tool responses, forbidden calls and bounded local-file outcomes such as file existence, change and JSON content.

A model-requested tool call by itself **does not prove** that a remote API succeeded, a refund was committed or an external database changed. The specialized refund and retail integrations have independent stateful oracles, but those oracles are not yet a generic capability for arbitrary imported SaaS agents. No unrestricted external-service execution is granted.

Protected train/validation/holdout evaluations provide evidence for tested behaviors, not universal reliability. The [live repair evidence](live-evidence-2026-11-06.md) notes known sample and holdout limitations.

## Vultr and operational constraints

- **Vultr Cloud Compute** hosts the current HTTP/HTTPS services, trusted control plane, evidence storage and sandbox runtime.
- **Vultr Serverless Inference** serves selected source/replacement model calls and supported repair generation. The API key is host-held, never mounted into imported-agent containers.
- The current public service has bounded per-account and global request allowances, limits concurrent execution to one migration, and avoids automatic paid retries.
- Imported source stays subject to file, expanded-size, total-entry and time limits even when the full GitHub repository or streamed ZIP is larger.
- Every worker should produce verifiable cleanup receipts; those are operational host observations, **not** a complete syscall audit.
- Public revision identity and external read-only acceptance verify deployed provenance separately from source-code CI. Authenticated, paid end-to-end acceptance remains a distinct check.

## Supported and future integration boundaries

**Implemented:** managed Python application execution; curated Node/TypeScript with paid verification for the pinned AI SDK agent; pinned GitHub/ZIP import; the operator-side local CLI; specialized original-agent integration runners; sandboxed inference, evidence, bounded adaptations and verified exports in supported cases.

**Not a general self-service capability yet:** arbitrary framework/SDK runtimes, arbitrary remote HTTP-service invocation, unrestricted streaming, arbitrary external tools and production database verification.

The shared evaluator also runs from the developer-side CLI against trusted local Python or explicitly authorized loopback HTTP test services. The CLI labels these runs as developer-host execution. Hosted runs continue to require gVisor.

For prior architecture milestones and historical experiment descriptions, see [engineering history](engineering-history.md).
