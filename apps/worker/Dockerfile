# Isengard Worker Dockerfile

FROM python:3.11-slim

WORKDIR /app

# Install uv for fast dependency installation
RUN pip install --no-cache-dir uv

# Copy shared packages first (for caching)
COPY packages/ /app/packages/

# Copy worker requirements and install
COPY apps/worker/requirements.txt /app/apps/worker/requirements.txt
RUN uv pip install --system -r /app/apps/worker/requirements.txt

# Copy worker source
COPY apps/worker/src/ /app/apps/worker/src/

# Set Python path
ENV PYTHONPATH=/app

# Run worker
CMD ["python", "-m", "apps.worker.src.main"]
