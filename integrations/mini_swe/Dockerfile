FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN git init /opt/upstream && git -C /opt/upstream remote add origin https://github.com/SWE-agent/mini-swe-agent && \
    git -C /opt/upstream fetch --depth 1 origin 04d809ceab9df28f9adaed044884180159172930 && git -C /opt/upstream checkout --detach FETCH_HEAD
RUN pip install --no-cache-dir --no-deps /opt/upstream && \
    pip install --no-cache-dir 'litellm>=1.80.15,<1.82.7' pyyaml jinja2 'pydantic>=2' tenacity rich python-dotenv platformdirs
RUN git init /opt/task-base && git -C /opt/task-base remote add origin https://github.com/psf/requests && \
    git -C /opt/task-base fetch --depth 1 origin 091991be0da19de9108dbe5e3752917fea3d7fdc && git -C /opt/task-base checkout --detach FETCH_HEAD
WORKDIR /opt/refit
COPY scripts /opt/refit/scripts
COPY integrations/container_worker.py /opt/refit/integrations/container_worker.py
COPY integrations/mini_swe/adapter.py integrations/mini_swe/apply_config.py integrations/mini_swe/sitecustomize.py integrations/mini_swe/verify.py integrations/mini_swe/evaluate.py /opt/refit/integrations/mini_swe/
ENV HOME=/tmp PYTHONDONTWRITEBYTECODE=1 LITELLM_LOCAL_MODEL_COST_MAP=true MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT=1 MSWEA_SILENT_STARTUP=1
ENTRYPOINT ["python", "-B", "-u", "-m", "integrations.container_worker"]
