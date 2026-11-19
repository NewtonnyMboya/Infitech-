"""INFILINK Runtime: explicit, bounded in-process language adapters.

Only handlers registered by trusted application code are invoked. This module
never evaluates source text, launches shells, or dynamically imports user code.
"""
from __future__ import annotations
import asyncio
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

MAX_DOCUMENT_BYTES = 1_048_576
Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

class RuntimeErrorBase(RuntimeError):
    """Base error for runtime registry and invocation failures."""

class RuntimeUnavailable(RuntimeErrorBase):
    pass

def _bounded_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False,
                             separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(f"{label} must contain interoperable JSON values") from exc
    if len(encoded) > MAX_DOCUMENT_BYTES:
        raise ValueError(f"{label} exceeds the 1 MiB limit")
    return json.loads(encoded.decode("utf-8"))

@dataclass(frozen=True)
class RuntimeDescriptor:
    runtime_id: str
    language: str
    capabilities: frozenset[str]

class RegisteredHandlerAdapter:
    """Adapter for explicitly supplied trusted handlers; not a code interpreter."""
    def __init__(self, language: str, handlers: dict[str, Handler]) -> None:
        if not isinstance(language, str) or not (1 <= len(language) <= 32):
            raise ValueError("language must contain 1..32 characters")
        if not isinstance(handlers, dict) or not handlers or len(handlers) > 128:
            raise ValueError("handlers must contain 1..128 capabilities")
        for name, handler in handlers.items():
            if not isinstance(name, str) or not (1 <= len(name) <= 64):
                raise ValueError("capability names must contain 1..64 characters")
            if not callable(handler):
                raise TypeError("each capability handler must be callable")
        self.language = language
        self._handlers = dict(handlers)

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset(self._handlers)

    async def invoke(self, capability: str, payload: dict[str, Any]) -> dict[str, Any]:
        handler = self._handlers.get(capability)
        if handler is None:
            raise RuntimeUnavailable("runtime capability not found")
        return _bounded_object(await handler(_bounded_object(payload, "input")), "output")

class RuntimeRegistry:
    """Bounded registry with explicit capability checks and per-call deadlines."""
    def __init__(self, max_runtimes: int = 32, timeout_seconds: float = 5.0) -> None:
        if not 1 <= max_runtimes <= 256:
            raise ValueError("max_runtimes must be between 1 and 256")
        if not 0 < timeout_seconds <= 60:
            raise ValueError("timeout_seconds must be in (0, 60]")
        self._max_runtimes = max_runtimes
        self.timeout_seconds = timeout_seconds
        self._adapters: dict[str, RegisteredHandlerAdapter] = {}
        self._lock = asyncio.Lock()

    async def register(self, runtime_id: str, adapter: RegisteredHandlerAdapter) -> None:
        if not isinstance(runtime_id, str) or not (1 <= len(runtime_id) <= 64):
            raise ValueError("runtime_id must contain 1..64 characters")
        if not isinstance(adapter, RegisteredHandlerAdapter):
            raise TypeError("adapter must be a RegisteredHandlerAdapter")
        async with self._lock:
            if runtime_id not in self._adapters and len(self._adapters) >= self._max_runtimes:
                raise RuntimeErrorBase("runtime registry capacity reached")
            self._adapters[runtime_id] = adapter

    async def unregister(self, runtime_id: str) -> bool:
        async with self._lock:
            return self._adapters.pop(runtime_id, None) is not None

    async def discover(self) -> list[dict[str, Any]]:
        async with self._lock:
            return [{"runtime_id": key, "language": adapter.language,
                     "capabilities": sorted(adapter.capabilities)}
                    for key, adapter in sorted(self._adapters.items())]

    async def invoke(self, runtime_id: str, capability: str,
                     payload: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            adapter = self._adapters.get(runtime_id)
        if adapter is None or capability not in adapter.capabilities:
            raise RuntimeUnavailable("runtime or capability not found")
        safe_input = _bounded_object(payload, "input")
        try:
            result = await asyncio.wait_for(
                adapter.invoke(capability, safe_input), timeout=self.timeout_seconds)
        except asyncio.TimeoutError as exc:
            raise RuntimeErrorBase("runtime invocation timed out") from exc
        return _bounded_object(result, "output")
