"""INFILINK Cloud: validated Kubernetes deployment manifest generation.

This module renders declarative JSON-compatible manifests only. It does not
contact clusters, deploy workloads, or read secret values.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any

_NAME = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
_ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DIGEST = re.compile(r"^.+@sha256:[a-f0-9]{64}$")

@dataclass(frozen=True)
class SecretReference:
    name: str
    key: str

    def __post_init__(self) -> None:
        if not _NAME.fullmatch(self.name) or not _NAME.fullmatch(self.key):
            raise ValueError("secret name and key must be DNS-compatible identifiers")

@dataclass(frozen=True)
class CloudService:
    name: str
    image: str
    container_port: int = 8080
    replicas: int = 1
    namespace: str = "default"
    cpu_request: str = "100m"
    cpu_limit: str = "500m"
    memory_request: str = "128Mi"
    memory_limit: str = "512Mi"
    health_path: str = "/health"
    environment: dict[str, str | SecretReference] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _NAME.fullmatch(self.name) or not _NAME.fullmatch(self.namespace):
            raise ValueError("service name and namespace must be DNS-compatible")
        if not _DIGEST.fullmatch(self.image):
            raise ValueError("image must be pinned by a lowercase sha256 digest")
        if not 1 <= self.container_port <= 65535:
            raise ValueError("container_port must be between 1 and 65535")
        if not 1 <= self.replicas <= 10:
            raise ValueError("replicas must be between 1 and 10")
        if not self.health_path.startswith("/") or len(self.health_path) > 256:
            raise ValueError("health_path must be an absolute path of at most 256 chars")
        if len(self.environment) > 64:
            raise ValueError("at most 64 environment variables are allowed")
        for key, value in self.environment.items():
            if not _ENV.fullmatch(key):
                raise ValueError("invalid environment variable name")
            if isinstance(value, str):
                if len(value) > 4096 or "\x00" in value:
                    raise ValueError("environment values must be bounded and contain no NUL")
            elif not isinstance(value, SecretReference):
                raise ValueError("environment values must be strings or SecretReference objects")
        for quantity in (self.cpu_request, self.cpu_limit, self.memory_request, self.memory_limit):
            if not isinstance(quantity, str) or not re.fullmatch(r"[0-9]+(m|Mi|Gi)?", quantity):
                raise ValueError("resource quantities must use simple integer Kubernetes units")

def render_manifests(service: CloudService) -> list[dict[str, Any]]:
    """Return Deployment and ClusterIP Service objects; never performs deployment."""
    env = []
    for key, value in sorted(service.environment.items()):
        if isinstance(value, SecretReference):
            env.append({"name": key, "valueFrom": {"secretKeyRef":
                        {"name": value.name, "key": value.key}}})
        else:
            env.append({"name": key, "value": value})
    labels = {"app.kubernetes.io/name": service.name}
    container = {
        "name": service.name, "image": service.image, "imagePullPolicy": "IfNotPresent",
        "ports": [{"name": "http", "containerPort": service.container_port, "protocol": "TCP"}],
        "env": env,
        "resources": {"requests": {"cpu": service.cpu_request, "memory": service.memory_request},
                      "limits": {"cpu": service.cpu_limit, "memory": service.memory_limit}},
        "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
                            "runAsNonRoot": True, "capabilities": {"drop": ["ALL"]},
                            "seccompProfile": {"type": "RuntimeDefault"}},
        "readinessProbe": {"httpGet": {"path": service.health_path, "port": "http"},
                           "periodSeconds": 10, "timeoutSeconds": 2},
        "livenessProbe": {"httpGet": {"path": service.health_path, "port": "http"},
                          "periodSeconds": 20, "timeoutSeconds": 2},
    }
    deployment = {"apiVersion": "apps/v1", "kind": "Deployment",
                  "metadata": {"name": service.name, "namespace": service.namespace, "labels": labels},
                  "spec": {"replicas": service.replicas,
                           "selector": {"matchLabels": labels},
                           "template": {"metadata": {"labels": labels},
                                        "spec": {"automountServiceAccountToken": False,
                                                 "containers": [container]}}}}
    network_service = {"apiVersion": "v1", "kind": "Service",
                       "metadata": {"name": service.name, "namespace": service.namespace},
                       "spec": {"type": "ClusterIP", "selector": labels,
                                "ports": [{"name": "http", "port": 80,
                                           "targetPort": "http", "protocol": "TCP"}]}}
    return [deployment, network_service]

def manifest_document(service: CloudService) -> dict[str, Any]:
    """Wrap manifests in a JSON-serializable document for tooling and review."""
    return {"apiVersion": "infilink.dev/v1alpha1", "kind": "DeploymentBundle",
            "metadata": {"name": service.name}, "manifests": render_manifests(service)}
