#!/usr/bin/env bash
# deploy.sh — Build and redeploy Recommendarr container on unRAID
# Copyright (c) 2026 VAASSEN GmbH / Ray Vaassen
set -euo pipefail

CONTAINER="Recommendarr"
IMAGE="recommendarr:latest"
PORT="30800:5055"
DATA_VOL="/mnt/user/system/appdata/recommendarr:/app/data:rw"
REPO_DIR="/mnt/user/system/recommendarr-repo"

cd "${REPO_DIR}"

echo "=== Building ${IMAGE} (multi-stage: frontend + backend) ==="
docker build -t "${IMAGE}" . 2>&1 | tail -5

echo "=== Stopping ${CONTAINER} ==="
docker stop "${CONTAINER}" 2>/dev/null || true
docker rm "${CONTAINER}" 2>/dev/null || true

echo "=== Starting ${CONTAINER} ==="
docker run -d \
  --name "${CONTAINER}" \
  --restart unless-stopped \
  -p "${PORT}" \
  -v "${DATA_VOL}" \
  --env-file "${REPO_DIR}/deploy.env" \
  "${IMAGE}"

echo "=== Waiting for health check ==="
for i in $(seq 1 30); do
  if curl -sf "http://localhost:30800/api/v1/health" > /dev/null 2>&1; then
    echo "=== ${CONTAINER} healthy ==="
    curl -s "http://localhost:30800/api/v1/health" | python3 -c "
import json,sys
d=json.load(sys.stdin)
svc=len(d.get('services',{}))
print(f'  Status: {d[\"status\"]}, Services: {svc}/6, Users: {d[\"users_loaded\"]}')
" 2>/dev/null || echo "  (health details unavailable)"
    exit 0
  fi
  sleep 2
done
echo "=== WARNING: Health check timed out after 60s ==="
docker logs "${CONTAINER}" --tail 10
exit 1
