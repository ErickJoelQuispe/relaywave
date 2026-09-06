#!/usr/bin/env bash
set -euo pipefail

# Deploys a specific backend image version to the local kind cluster,
# or rolls back the previous deploy.
#
# The image tag matches the short git SHA published by the CI
# "docker-push" job (see .github/workflows/ci.yml) to GHCR. This script
# never deploys "latest" — every deploy is tied to a specific commit.
#
# Usage:
#   scripts/deploy.sh <git-sha>   # pull, load into kind, rollout the given version
#   scripts/deploy.sh rollback    # undo the most recent rollout
#
# Prerequisites:
#   - kind cluster "relaywave" running (kind get clusters)
#   - kubectl context pointing at it
#   - docker logged in to ghcr.io if the package is private:
#       echo <PAT-with-read:packages> | docker login ghcr.io -u <github-username> --password-stdin

NAMESPACE="relaywave"
CLUSTER_NAME="relaywave"
DEPLOYMENT="backend"
CONTAINER="backend"
IMAGE_REPO="ghcr.io/erickjoelquispe/relaywave-backend"

usage() {
  echo "Usage: $0 <git-sha>|rollback" >&2
  exit 1
}

if [[ $# -ne 1 ]]; then
  usage
fi

if [[ "$1" == "rollback" ]]; then
  echo "Rolling back deployment/${DEPLOYMENT} in namespace ${NAMESPACE}..."
  kubectl rollout undo "deployment/${DEPLOYMENT}" -n "${NAMESPACE}"
  kubectl rollout status "deployment/${DEPLOYMENT}" -n "${NAMESPACE}"
  echo "Rollback complete."
  exit 0
fi

SHA="$1"
IMAGE="${IMAGE_REPO}:${SHA}"

echo "Pulling ${IMAGE}..."
if ! docker pull "${IMAGE}"; then
  echo "Failed to pull ${IMAGE}." >&2
  echo "If the GHCR package is private, log in first:" >&2
  echo "  echo <PAT-with-read:packages> | docker login ghcr.io -u <github-username> --password-stdin" >&2
  exit 1
fi

echo "Loading ${IMAGE} into kind cluster '${CLUSTER_NAME}'..."
kind load docker-image "${IMAGE}" --name "${CLUSTER_NAME}"

echo "Rolling out ${IMAGE} to deployment/${DEPLOYMENT}..."
kubectl set image "deployment/${DEPLOYMENT}" "${CONTAINER}=${IMAGE}" -n "${NAMESPACE}"
kubectl rollout status "deployment/${DEPLOYMENT}" -n "${NAMESPACE}"

echo "Deploy complete."
echo "To roll back: scripts/deploy.sh rollback"
