#!/usr/bin/env bash
# Bootstrap the local kind cluster and load synthetic failure fixtures.
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-ai-devops-demo}"
KUBECONFIG_DIR="${KUBECONFIG_DIR:-$HOME/.kube/ai-devops}"
CONTEXT_NAME="kind-${CLUSTER_NAME}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# IMPORTANT: isolate kubeconfig so we NEVER touch the user's default ~/.kube/config
# or any production context. All kind/kubectl commands below use this file.
mkdir -p "${KUBECONFIG_DIR}"
export KUBECONFIG="${KUBECONFIG_DIR}/config"

echo "[*] Ensuring kind cluster '${CLUSTER_NAME}' exists ..."
if ! kind get clusters 2>/dev/null | grep -qx "${CLUSTER_NAME}"; then
  # KUBECONFIG is set above, so kind writes only to the isolated file.
  kind create cluster --name "${CLUSTER_NAME}"
else
  echo "[*] cluster '${CLUSTER_NAME}' already exists"
fi

echo "[*] Writing isolated kubeconfig to ${KUBECONFIG_DIR}/config"
kind get kubeconfig --name "${CLUSTER_NAME}" > "${KUBECONFIG_DIR}/config"

echo "[*] Verifying active context is local (${CONTEXT_NAME}) ..."
CURRENT="$(kubectl config current-context)"
if [[ "${CURRENT}" != "${CONTEXT_NAME}" ]]; then
  echo "[!] SAFETY ABORT: current context '${CURRENT}' != '${CONTEXT_NAME}'" >&2
  exit 1
fi

echo "[*] Waiting for control plane ..."
kubectl wait --for=condition=Ready node --all --timeout=180s

echo "[*] Applying synthetic fixtures ..."
kubectl apply -f "${ROOT}/fixtures/namespace.yaml"
kubectl apply -f "${ROOT}/fixtures/crashloop.yaml"
kubectl apply -f "${ROOT}/fixtures/oomkilled.yaml"
kubectl apply -f "${ROOT}/fixtures/pending.yaml"

echo "[*] Done. Export KUBECONFIG to use it:"
echo "    export KUBECONFIG=${KUBECONFIG_DIR}/config"
