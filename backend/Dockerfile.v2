# Recommendarr v2 — lightweight API orchestration container
# No AI/GPU dependencies. Pure Python + FastAPI + httpx.
FROM python:3.12-slim

LABEL maintainer="Ray DiRenzo <ray@mydirenzo.ch>"
LABEL description="Recommendarr — personal media recommendation engine (API-first)"
LABEL version="0.2.0"

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ app/

# Non-root user
RUN useradd -m -u 1000 recommendarr
USER recommendarr

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import httpx; r=httpx.get('http://localhost:30800/api/v1/health'); exit(0 if r.status_code==200 else 1)"

EXPOSE 30800

CMD ["uvicorn", "app.main_v2:app", "--host", "0.0.0.0", "--port", "30800", "--log-level", "info"]
