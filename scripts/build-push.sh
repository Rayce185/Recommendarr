#!/bin/bash
# Build and push Recommendarr to Docker Hub
# VAASSEN GmbH / Ray Vaassen
# Usage: ./scripts/build-push.sh [version]
set -euo pipefail

VERSION="${1:-latest}"
REPO="rayce185/recommendarr"

echo "Building Recommendarr v${VERSION}..."
cd "$(dirname "$0")/.."

docker build --build-arg VERSION="${VERSION}" \
    -t "${REPO}:${VERSION}" -t "${REPO}:latest" \
    --no-cache .

echo "Built: ${REPO}:${VERSION} + ${REPO}:latest"
read -p "Push to Docker Hub? (y/N) " confirm
if [[ "${confirm}" =~ ^[Yy]$ ]]; then
    docker push "${REPO}:${VERSION}"
    docker push "${REPO}:latest"
    echo "Pushed successfully!"
else
    echo "Skipped. Manual: docker push ${REPO}:${VERSION} && docker push ${REPO}:latest"
fi
