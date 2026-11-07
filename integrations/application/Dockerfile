FROM node:22-bookworm-slim AS node-runtime
WORKDIR /opt/refit/node
COPY integrations/application/node/package*.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund --omit=dev

FROM python:3.11-slim
# Curated runtime dependencies. Project installation hooks are never run.
RUN pip install --no-cache-dir 'llm==0.37.1'
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /opt/refit/node/node_modules /opt/refit/node/node_modules
RUN node --version
WORKDIR /opt/refit
COPY integrations/application/worker.py ./worker.py
ENTRYPOINT ["python", "-I", "-B", "-u", "/opt/refit/worker.py"]
