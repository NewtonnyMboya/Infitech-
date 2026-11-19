"""TLS WebSocket transport for binary IILP/1 frames.

Requires the optional websockets package. The application supplies an
authentication callback; this module does not trust browser-provided roles.
"""
from __future__ import annotations

import asyncio
import inspect
import ssl
from typing import Any, Callable
from urllib.parse import urlsplit

from core import CoreError, MessageRouter
from iilp import IILPError, MAX_PAYLOAD, decode_frame, encode

SUBPROTOCOL = "iilp.v1"
MAX_FRAME_BYTES = MAX_PAYLOAD + 10


class WebSocketTransportError(RuntimeError):
    """WebSocket transport configuration or request failure."""


class IILPWebSocketServer:
    """Serve one binary IILP request per WebSocket message.

    authenticate receives the connection's HTTP headers and must return a
    truthy authenticated principal (or raise). Configure a secure session or
    bearer-token verifier server-side; never trust role/scope headers from the
    client. An explicit origin allowlist is mandatory.
    """

    def __init__(
        self,
        router: MessageRouter,
        ssl_context: ssl.SSLContext,
        *,
        allowed_origins: set[str],
        authenticate: Callable[[Any], Any],
        authorize: Callable[[Any, str, dict[str, Any]], Any],
        max_connections: int = 100,
        idle_timeout: float = 30.0,
    ) -> None:
        if not isinstance(ssl_context, ssl.SSLContext):
            raise ValueError("a configured TLS SSLContext is mandatory")
        if not allowed_origins:
            raise ValueError("an explicit browser origin allowlist is mandatory")
        normalized = set()
        for origin in allowed_origins:
            parsed = urlsplit(origin)
            if (parsed.scheme != "https" or not parsed.hostname or
                parsed.path not in ("",) or parsed.query or parsed.fragment or
                parsed.username or parsed.password):
                raise ValueError("allowed origins must be exact HTTPS origins")
            normalized.add(f"https://{parsed.netloc.lower()}")
        if not callable(authenticate) or not callable(authorize):
            raise ValueError("authentication and authorization callbacks are mandatory")
        if not 1 <= max_connections <= 10_000 or not 0 < idle_timeout <= 300:
            raise ValueError("invalid connection or idle timeout limit")
        self.router = router
        self.ssl_context = ssl_context
        self.allowed_origins = frozenset(normalized)
        self.authenticate = authenticate
        self.authorize = authorize
        self.semaphore = asyncio.Semaphore(max_connections)
        self.idle_timeout = idle_timeout
        self._server = None

    async def _authenticate(self, websocket: Any) -> Any:
        request = getattr(websocket, "request", None)
        headers = getattr(request, "headers", None)
        if headers is None:
            raise WebSocketTransportError("missing handshake headers")
        origin = headers.get("Origin")
        if origin not in self.allowed_origins:
            raise WebSocketTransportError("origin is not allowed")
        principal = self.authenticate(headers)
        if inspect.isawaitable(principal):
            principal = await principal
        if not principal:
            raise WebSocketTransportError("authentication failed")
        return principal

    async def _dispatch_frame(self, frame: bytes, principal: Any) -> bytes:
        if not isinstance(frame, (bytes, bytearray, memoryview)):
            raise WebSocketTransportError("only binary IILP frames are accepted")
        if len(frame) > MAX_FRAME_BYTES:
            raise WebSocketTransportError("frame exceeds configured limit")
        try:
            message = decode_frame(bytes(frame))
            target = message.get("body", {}).get("target")
            if not isinstance(target, str) or not target:
                raise WebSocketTransportError("body.target service name is required")
            allowed = self.authorize(principal, target, message)
            if inspect.isawaitable(allowed):
                allowed = await allowed
            if not allowed:
                raise WebSocketTransportError("authorization denied")
            result = await self.router.dispatch(target, message)
            response = {
                "type": "response",
                "id": message["id"],
                "body": {"ok": True, "result": result},
            }
        except (IILPError, CoreError, WebSocketTransportError) as exc:
            response = {
                "type": "error",
                "id": "request-error",
                "body": {"ok": False, "error": type(exc).__name__},
            }
        return encode(response)

    async def _handler(self, websocket: Any) -> None:
        async with self.semaphore:
            try:
                principal = await self._authenticate(websocket)
                async for frame in websocket:
                    try:
                        response = await asyncio.wait_for(
                            self._dispatch_frame(frame, principal),
                            timeout=self.idle_timeout,
                        )
                        await websocket.send(response)
                    except asyncio.TimeoutError:
                        await websocket.close(code=1013, reason="request timeout")
                        return
                    except WebSocketTransportError:
                        await websocket.close(code=1008, reason="invalid request")
                        return
            except WebSocketTransportError:
                await websocket.close(code=1008, reason="connection rejected")

    async def start(self, host: str = "127.0.0.1", port: int = 9444):
        """Start the WSS listener. Requires websockets >=13,<16."""
        try:
            from websockets.asyncio.server import serve
        except ImportError as exc:
            raise RuntimeError("install optional dependency: pip install 'websockets>=13,<16'") from exc
        if self._server is not None:
            raise RuntimeError("WebSocket server is already started")
        self._server = await serve(
            self._handler,
            host,
            port,
            ssl=self.ssl_context,
            origins=list(self.allowed_origins),
            subprotocols=[SUBPROTOCOL],
            max_size=MAX_FRAME_BYTES,
            max_queue=16,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=10,
            compression=None,
        )
        return self._server

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
