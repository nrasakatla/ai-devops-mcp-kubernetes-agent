# Incident Report: ai-devops-ns/pending-demo-6444845f74-4gsnd

- **Generated:** 2026-10-15 19:06 UTC
- **Pod:** `pending-demo-6444845f74-4gsnd` (namespace `ai-devops-ns`)
- **Failure class:** `Pending`
- **Analysis source:** `ollama/qwen3.5:9b`
- **Confidence:** high

## Suspected root cause

The pod is stuck in a Pending state because the scheduler cannot place it on any available node due to node affinity or selector constraints. The single node in the cluster does not match the requirements defined in the pod's spec.

## Supporting evidence

- Pod phase is 'Pending' with condition type 'PodScheduled' status 'False'.
- Condition message explicitly states: '0/1 nodes are available: 1 node(s) didn't match Pod's node affinity/selector.'
- Events log shows repeated 'FailedScheduling' warnings citing the same affinity mismatch.
- Preemption is not helpful because there is only one node in the cluster.

## Pod status

```
Phase:     Pending
Reason:    None
Message:   None
Node:      None
```

## Kubernetes events

| Type | Reason | Message | Count |
|------|--------|---------|-------|
| Warning | FailedScheduling | 0/1 nodes are available: 1 node(s) didn't match Pod's node affinity/selector. preemption: 0/1 nodes are available: 1 Pre | 6 |

## Recommended remediation

- Inspect the pod specification (kubectl get pod <pod-name> -o yaml) to identify the nodeAffinity or nodeSelector labels.
- Verify that the labels exist on the available node using 'kubectl get nodes --show-labels'.
- If the affinity is intentional, ensure the target node has the correct labels; if not, remove or correct the affinity/selector constraints in the pod definition.
- Alternatively, add the missing label to the existing node or create a new node with the required labels.

---

_Advisory report only. No remediation was applied automatically._
