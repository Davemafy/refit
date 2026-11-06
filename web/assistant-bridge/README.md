# Refit ↔ assistant-ui integration

This package is a **working integration substrate**, not the final visual design. It uses the established [assistant-ui](https://www.assistant-ui.com/docs/runtimes/custom/local-runtime) LocalRuntime for threads, message editing, cancellation, accessible primitives and lifecycle management. Refit's Python backend retains sole authority over intent, tool calls, model evidence and migration verdicts.

```sh
# Terminal 1: from repository root (no inference credentials required)
python3 -m scripts.refit_http --host 127.0.0.1 --port 8097 --runs-dir ./var/runs

# Terminal 2: from web/assistant-bridge
npm ci
npm test
npm run build
npm run dev

# Open http://127.0.0.1:3007
```

The Vite dev server forwards `/api/*` to the real Refit backend. Production builds make **relative same-origin API requests**. Use your normal Nginx routing for `/api/*` when deploying a custom frontend.

## Use with your own React interface

Import `RefitRuntimeProvider` from `src/runtime.tsx` (or `src/index.ts`) and wrap your own thread component. Reuse `createRefitAdapter` from `src/adapter.ts` and the typed `RefitApi` from `src/refit-api.ts`. You can replace **all visual elements** without modifying the adapter.

## Security and product boundaries

- This bridge **never** submits code, executes tools, starts migrations, stores operator tokens or calls Vultr inference.
- It interprets a typed migration, fetches **actual recorded** Refit runs and formats their measured outcomes. It fails visibly when the API is unavailable, a run has invalid evidence, or no matching evaluation exists.
- This is not a general conversational LLM agent. The backend supports only two built-in scenarios. A new UI does not magically provide external-agent import.
- Never put Vultr credentials or a privileged bearer token in the browser. A future live UI should use a trusted server-side BFF with authentication, explicit approval and quota controls.
- We chose LocalRuntime rather than adding CopilotKit/AG-UI to the existing Python API because it directly supports REST with one documented `ChatModelAdapter`; an AG-UI migration can come later if streaming tool state and bidirectional calls become necessary.

## Verified and deployed staging path

The React bridge is built from the pinned `package-lock.json` in CI. The suite typechecks, produces a static production build, verifies the existing API, and runs a real headless Chromium test for the three critical cases: broken target repaired, already-compatible target, and unsupported model pair. The browser check must pass before relying on this as the public interactive bridge.

After CI is green, from the existing Vultr VM as root:

```bash
cd /opt/refit-app && git pull --ff-only && bash deploy/launch-bridge.sh
```

It installs the compiled static client at `/bridge/` and preserves the current `/`, `/demo`, and `/api/*` routes. It does not enable paid inference and must not be presented as a complete agent-import or live migration UI.
