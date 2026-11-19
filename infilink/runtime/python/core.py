"""INFILINK Core: bounded service registry and explicit message routing.

This module deliberately does not execute arbitrary code or load plugins dynamically.
Applications register trusted async handlers in-process.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class CoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class Service:
    name: str
    handler: Handler
    message_types: frozenset[str]
    registered_at: float


class ServiceRegistry:
    """In-memory registry with bounded names and explicit message capabilities."""

    def __init__(self, max_services: int = 256) -> None:
        if not 1 <= max_services <= 100_000:
            raise ValueError("max_services must be between 1 and 100000")
        self._services: dict[str, Service] = {}
        self._max_services = max_services
        self._lock = asyncio.Lock()

    async def register(
        self, name: str, handler: Handler, message_types: set[str] | frozenset[str]
    ) -> None:
        if not isinstance(name, str) or not (1 <= len(name) <= 64):
            raise ValueError("service name must contain 1..64 characters")
        if not callable(handler):
            raise TypeError("handler must be callable")
        types = frozenset(message_types)
        if not types or any(not isinstance(t, str) or not (1 <= len(t) <= 64) for t in types):
            raise ValueError("at least one valid message type is required")
        async with self._lock:
            if name not in self._services and len(self._services) >= self._max_services:
                raise CoreError("service registry capacity reached")
            self._services[name] = Service(name, handler, types, time.monotonic())

    async def unregister(self, name: str) -> bool:
        async with self._lock:
            return self._services.pop(name, None) is not None

    async def discover(self) -> list[dict[str, Any]]:
        async with self._lock:
            return [
                {"name": s.name, "message_types": sorted(s.message_types)}
                for s in sorted(self._services.values(), key=lambda item: item.name)
            ]

    async def resolve(self, name: str, message_type: str) -> Service:
        async with self._lock:
            service = self._services.get(name)
        if service is None or message_type not in service.message_types:
            raise CoreError("service or message capability not found")
        return service


class MessageRouter:
    """Routes only to explicitly registered services and declared message types."""

    def __init__(self, registry: ServiceRegistry, timeout_seconds: float = 5.0) -> None:
        if not 0 < timeout_seconds <= 60:
            raise ValueError("timeout_seconds must be in (0, 60]")
        self.registry = registry
        self.timeout_seconds = timeout_seconds

    async def dispatch(self, target: str, message: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(message, dict):
            raise CoreError("message must be an object")
        msg_type = message.get("type")
        if not isinstance(msg_type, str):
            raise CoreError("message type is required")
        service = await self.registry.resolve(target, msg_type)
        try:
            result = await asyncio.wait_for(
                service.handler(message), timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError as exc:
            raise CoreError("handler timed out") from exc
        if not isinstance(result, dict):
            raise CoreError("handler must return an object")
        return result
