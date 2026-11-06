# Refit MVP execution

The MVP accepts a supported tool-using agent, compares a model replacement,
proposes a bounded configuration adaptation, evaluates it independently, and
exports configuration that can be applied by the originating agent runner.
Work lands directly on `main`. UI work is deferred.

## Implemented in the evaluation version 2 pass

- Source baseline checks now cover training, validation and holdout. A source
  failure on either independent split blocks both compatibility and repair.
- Repair compares source, unchanged target and adapted target on validation
  and holdout, reusing each materialized split's resettable environment factories.
  Factories must return equivalent fresh initial state on every call; a request
  fingerprint alone does not prove fixture-state equivalence.
- Reports preserve successful and unsuccessful evaluations, assistant responses,
  tool results, final answers, verifier results, request attempts and elapsed time.
  These are private evaluation artifacts; use synthetic or sanitized fixtures.
- Each phase records its model and profile fingerprint. Reports include a contract
  fingerprint and per-split case names and request fingerprints. Fingerprints
  detect changes; they do not authenticate reports or snapshot arbitrary code.
- Diagnoses distinguish observed execution errors, prohibited attempts, stopping
  without tools and unmet outcomes. These are symptoms, not proven root causes.
- Candidate variants are deduplicated and tested in ascending inserted/deleted
  character count. The first training-passing candidate advances. This is the
  smallest edit among the generated passing variants, not a global minimum or a
  claim that character count measures semantic risk.
- Version 2 exports require passing source verification on all splits, equal
  paired sample sizes and the existing independent repair gates. They include
  the full report digest and split manifests. Archived version 1 reports retain
  their original evidence requirements and are not relabeled as paired evidence.

## Next acceptance gates

1. **Second-domain repair:** run the deployment adapter on real models and repair
   an observed regression using the shared engine. Compatibility or unsuccessful
   repair remains a valid result; never weaken the baseline to create a failure.
2. **Repeatability:** predeclare seeds and workflow variations. Evaluate a frozen
   patch independently from repeated fresh repair searches. Preserve every result
   and compare source, baseline target and patched target on equal workloads.
3. **External agent:** adapt one independently authored agent, document its
   fixtures and assertions, and apply the exported profile in its own runner.
4. **Vultr delivery:** verify installation, isolation, cleanup, durable execution,
   CLI/API export and the externally reachable deployed service.

Live inference credentials and Docker are not available in the local development
environment used for this pass. Offline responders verify harness behavior only.
No new live repair evidence is established by these changes.

Paired evaluation requires more calls than the earlier protocol. Existing request
caps are unchanged; a run may exhaust its budget before reaching a verdict. Budget
exhaustion cannot justify reducing verification or exporting a patch. Plan the
request budget explicitly before executing billable evaluations.
