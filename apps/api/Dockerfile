# Isengard API Dockerfile

FROM python:3.11-slim

WORKDIR /app

# Install uv for fast dependency installation
RUN pip install --no-cache-dir uv

# Copy shared packages first (for caching)
COPY packages/ /app/packages/

# Copy API requirements and install
COPY apps/api/requirements.txt /app/apps/api/requirements.txt
RUN uv pip install --system -r /app/apps/api/requirements.txt

# Copy API source
COPY apps/api/src/ /app/apps/api/src/

# Set Python path
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health')" || exit 1

# Run with uvicorn
CMD ["uvicorn", "apps.api.src.main:app", "--host", "0.0.0.0", "--port", "8000"]
