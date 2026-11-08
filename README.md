# Refit

Change the model. Keep the behavior.

Refit runs your agent with two models, compares tool use and outcomes, and verifies the configuration in a fresh run before export.

[Live demo](https://refit.davemafy.xyz/app) · [Demo video](https://github.com/Davemafy/refit/releases/download/c1-4k-4e68d190cabb/refit-vultr-challenge1-4k.mp4) · [Documentation](docs/bring-your-agent.md)

## Getting started

Open the [workspace](https://refit.davemafy.xyz/app) and select **Run refund agent**. The demo uses Vultr inference and independently checks changes to sample orders. It requires no account or API key.

For your own agent, [import a GitHub repository or ZIP](https://refit.davemafy.xyz/app/agents/new), choose the replacement model, and define the behavior to verify. See the [supported runtimes and import options](docs/bring-your-agent.md).

## Results

- **Refund repair:** The replacement improved from **13/24 to 24/24** with the exported patch in the original τ-bench runner, with zero unsafe attempts. [Evaluation](docs/framework-evidence-2026-11-06.md)
- **Imported agents:** Refit verified exports for independent [Python applications](docs/bring-your-agent.md#browser-acceptance--november-7-2026), a [TypeScript agent](https://github.com/Davemafy/refit/actions/runs/42416108155), and the [τ-bench retail agent](docs/original-retail-agent-evidence-2026-11-07.md).
- **Blast Radius Zero:** DeepSeek generated a diagnostic that passed a trusted oracle in two fresh gVisor workers on Vultr, including an unseen case. [Recorded run](https://refit.davemafy.xyz/app/runs/demo-diagnostic-2026-11-08?view=evidence&observation=diagnostic) · [Containment checks](https://github.com/Davemafy/refit/actions/runs/42484161419) · [Reproduction](docs/challenge-1-diagnostic.md)

## Development

Run the recorded evidence viewer locally with Python 3.11 or 3.12.

```sh
git clone https://github.com/Davemafy/refit.git
cd refit
python3 -m scripts.refit_http --host 127.0.0.1 --port 8097 --runs-dir ./runs
```

Open [localhost:8097/demo](http://127.0.0.1:8097/demo).

[Architecture](docs/architecture.md) · [Sandbox](docs/sandbox-runtime.md) · [Vultr deployment](docs/public-deployment.md) · [Engineering history](docs/engineering-history.md) · [MIT License](LICENSE)
