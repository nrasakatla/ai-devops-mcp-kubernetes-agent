.PHONY: cluster-up cluster-down test demo mcp-demo scan

CONTEXT := kind-ai-devops-demo

cluster-up:
	./scripts/cluster_up.sh

cluster-down:
	./scripts/cluster_down.sh

test:
	python -m pytest -q

demo:
	@export KUBECONFIG="$$(kind get kubeconfig --name ai-devops-demo)" ; \
	export AI_DEVOPS_KIND_CONTEXT="$(CONTEXT)" ; \
	python -m agents.diagnose_pod ai-devops-ns crashloop-demo ; \
	python -m agents.diagnose_pod ai-devops-ns oomkilled-demo ; \
	python -m agents.diagnose_pod ai-devops-ns pending-demo

mcp-demo:
	@export KUBECONFIG="$$(kind get kubeconfig --name ai-devops-demo)" ; \
	python scripts/mcp_client_demo.py

scan:
	./scripts/secret_scan.sh
