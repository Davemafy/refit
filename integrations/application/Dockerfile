FROM python:3.11-slim
# Curated runtime dependencies. Project installation hooks are never run.
RUN pip install --no-cache-dir 'llm==0.37.1'
WORKDIR /opt/refit
COPY integrations/application/worker.py ./worker.py
ENTRYPOINT ["python", "-I", "-B", "-u", "/opt/refit/worker.py"]
