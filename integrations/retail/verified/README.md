# Verified GLM configuration for the original retail agent

Upstream: https://github.com/sierra-research/tau2-bench
Revision: 033bf082f48e4a3c6a1256208e93cf2ce9c3bb6f

The comparison passed all six original tasks on DeepSeek and GLM. No instruction
repair was needed. The unchanged exported configuration passed a fresh two-task
run in the original framework using real Vultr inference.

Copy agent-config.json and apply_config.py into the approved original checkout.
The helper has no Refit imports. It checks original instructions, policy and
tool-schema fingerprints before configuring the original agent.

Full application and provider instructions:
https://github.com/Davemafy/refit/blob/main/integrations/retail/README.md

Measured evidence and reproduction:
https://github.com/Davemafy/refit/blob/main/docs/original-retail-agent-evidence-2026-11-07.md

The request budget includes both agent and customer-simulator calls. The
completed effort used 241 actual requests of its declared 400-request ceiling.
This configuration is evidence-backed for the declared sample, not a guarantee
for unknown agents or all retail tasks. Hashes detect changes; they are not
authenticated signatures. Do not execute an unreviewed imported agent on a
trusted host; use the documented gVisor entry point.
