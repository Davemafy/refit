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

Import `RefitRuntimeProvider` from `src/app.tsx` (or copy the provider) and wrap your own thread component. Reuse `createRefitAdapter` from `src/adapter.ts` and the typed `RefitApi` from `src/refit-api.ts`. You can replace **all visual elements** without modifying the adapter.

## Security and product boundaries

- This bridge **never** submits code, executes tools, starts migrations, stores operator tokens or calls Vultr inference.
- It interprets a typed migration, fetches **actual recorded** Refit runs and formats their measured outcomes. It fails visibly when the API is unavailable, a run has invalid evidence, or no matching evaluation exists.
- This is not a general conversational LLM agent. The backend supports only two built-in scenarios. A new UI does not magically provide external-agent import.
- Never put Vultr credentials or a privileged bearer token in the browser. A future live UI should use a trusted server-side BFF with authentication, explicit approval and quota controls.
- We chose LocalRuntime rather than adding CopilotKit/AG-UI to the existing Python API because it directly supports REST with one documented `ChatModelAdapter`; an AG-UI migration can come later if streaming tool state and bidirectional calls become necessary.
