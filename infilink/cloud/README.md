# INFILINK Cloud

The first Cloud milestone generates declarative Kubernetes resources; it does not
connect to a cluster, publish images, or deploy workloads.

## Python manifest builder

Use `runtime/python/cloud.py` to define a `CloudService` and call
`render_manifests(service)`. The result is a pair of JSON-compatible Kubernetes
objects: a Deployment and an internal ClusterIP Service.

The builder requires an immutable image reference pinned to a SHA-256 digest,
limits replicas to 1–10, validates ports and environment names, and supports
Kubernetes SecretKeyRef values so secret material need not be embedded in the
deployment descriptor.

Generated containers default to a read-only root filesystem, non-root execution,
no privilege escalation, dropped Linux capabilities, RuntimeDefault seccomp,
bounded CPU/memory resources, HTTP health probes, and disabled automatic service
account token mounting.

## Example

```python
from cloud import CloudService, SecretReference, render_manifests

service = CloudService(
    name="infilink-api",
    image="registry.example/infilink@sha256:" + "a" * 64,
    replicas=2,
    environment={"API_TOKEN": SecretReference("api-secrets", "token")},
)
manifests = render_manifests(service)
```

Replace the example image digest with the digest of an image you have built and
verified. Store secrets in the cluster secret manager; do not commit their values.

## Deployment boundary

Review generated manifests and apply them using your organization-approved
Kubernetes workflow. This module intentionally has no cluster credentials or
deployment side effects. Production deployments still need image provenance,
network policies, ingress TLS, authentication/authorization, secret rotation,
logging, monitoring, backups, vulnerability scanning and operational runbooks.
The generated ClusterIP Service is internal-only; external access requires an
explicitly configured ingress or gateway.
