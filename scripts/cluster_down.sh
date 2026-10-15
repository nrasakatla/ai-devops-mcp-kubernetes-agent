#!/usr/bin/env bash
# Tear down the local kind cluster.
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-ai-devops-demo}"

echo "[*] Deleting kind cluster '${CLUSTER_NAME}' ..."
kind delete cluster --name "${CLUSTER_NAME}"

echo "[*] Done."
