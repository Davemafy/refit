FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/sierra-research/tau2-bench /opt/upstream && \
    git -C /opt/upstream checkout --detach 033bf082f48e4a3c6a1256208e93cf2ce9c3bb6f && \
    pip install --no-cache-dir /opt/upstream
WORKDIR /opt/refit
COPY scripts /opt/refit/scripts
COPY integrations/retail /opt/refit/integrations/retail
COPY integrations/container_worker.py /opt/refit/integrations/container_worker.py
ENV TAU2_DATA_DIR=/opt/upstream/data LITELLM_LOCAL_MODEL_COST_MAP=true PYTHONDONTWRITEBYTECODE=1 HOME=/tmp
ENTRYPOINT ["python", "-B", "-u", "-m", "integrations.container_worker"]
