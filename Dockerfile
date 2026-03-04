# ============================================================
# Recommendarr — single-container build
# Stage 1: Build React frontend
# Stage 2: Python backend + nginx reverse proxy
# ============================================================

# ── Stage 1: Frontend build ──────────────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --production=false 2>/dev/null || npm install
COPY frontend/ .
RUN npm run build

# ── Stage 2: Runtime ─────────────────────────────────────────
FROM python:3.12-slim

LABEL maintainer="Ray DiRenzo <ray@mydirenzo.ch>"
LABEL description="Recommendarr — personal media recommendation engine"
LABEL version="0.5.0"

RUN apt-get update && \
    apt-get install -y --no-install-recommends nginx supervisor curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app/ app/
COPY --from=frontend-builder /build/dist /app/static

COPY docker/nginx.conf /etc/nginx/sites-available/default
COPY docker/supervisord.conf /etc/supervisor/conf.d/recommendarr.conf

RUN mkdir -p /app/data && chmod 777 /app/data

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:5055/api/v1/health || exit 1

EXPOSE 5055

CMD ["supervisord", "-c", "/etc/supervisor/supervisord.conf"]
