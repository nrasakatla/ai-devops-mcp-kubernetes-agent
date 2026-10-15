# Incident Report: ai-devops-ns/oomkilled-demo-5dbd8d9588-7hvdq

- **Generated:** 2026-10-15 19:06 UTC
- **Pod:** `oomkilled-demo-5dbd8d9588-7hvdq` (namespace `ai-devops-ns`)
- **Failure class:** `OOMKilled`
- **Analysis source:** `ollama/qwen3.5:9b`
- **Confidence:** high

## Suspected root cause

The container is consuming more memory than its hard limit (64Mi), causing the kernel to terminate it with exit code 137. The application likely has a memory leak or requires more memory than allocated, leading to a continuous restart loop.

## Supporting evidence

- Container lastState.reason: 'OOMKilled'
- Container lastState.exitCode: 137
- Container resources.limits.memory: '64Mi' vs container_statuses.allocatedResources.memory: '32Mi' (Note: The pod is requesting 32Mi but the limit is 64Mi; however, the OOM killer triggers when usage exceeds the limit of 64Mi)
- Container state.waiting.reason: 'CrashLoopBackOff'
- Events count for 'BackOff': 23
- Pod Ready condition status: False with reason 'ContainersNotReady' and message 'containers with unready status: [oom]'

## Pod status

```
Phase:     Running
Reason:    None
Message:   None
Node:      ai-devops-demo-control-plane
```

## Kubernetes events

| Type | Reason | Message | Count |
|------|--------|---------|-------|
| Normal | Scheduled | Successfully assigned ai-devops-ns/oomkilled-demo-5dbd8d9588-7hvdq to ai-devops-demo-control-plane | 1 |
| Normal | Pulling | Pulling image "python:3.12-alpine" | 1 |
| Normal | Pulled | Successfully pulled image "python:3.12-alpine" in 6.802s (6.802s including waiting). Image size: 21423636 bytes. | 1 |
| Normal | Created | Container created | 9 |
| Normal | Started | Container started | 9 |
| Normal | Pulled | Container image "python:3.12-alpine" already present on machine and can be accessed by the pod | 9 |
| Warning | BackOff | Back-off restarting failed container oom in pod oomkilled-demo-5dbd8d9588-7hvdq_ai-devops-ns(f2eb5bfe-4a80-4de9-ab6b-09f | 23 |

## Node resources

- Node: `ai-devops-demo-control-plane`
- Allocatable: cpu=10, memory=8126480Ki
- Capacity:    cpu=10, memory=8126480Ki

## Recent container logs (excerpt)

## Recommended remediation

- Increase the memory limit for the container (e.g., from 64Mi to 128Mi or higher) using 'resources.limits.memory'.
- Increase the memory request if necessary to ensure fair scheduling.
- Review the application code for potential memory leaks.
- Check application logs for out-of-memory warnings before the kill signal.

---

_Advisory report only. No remediation was applied automatically._
