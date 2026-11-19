"""TLS-required asynchronous IILP/1 server."""
from __future__ import annotations

import asyncio
import json
import ssl
import struct
from typing import Any

from core import CoreError, MessageRouter
from iilp import HEADER, MAGIC, VERSION, MAX_PAYLOAD, IILPError, _validate_message


class IILPServer:
    def __init__(
        self, router: MessageRouter, ssl_context: ssl.SSLContext,
        max_connections: int = 100, idle_timeout: float = 30.0
    ) -> None:
        if not isinstance(ssl_context, ssl.SSLContext):
            raise ValueError("a configured TLS SSLContext is mandatory")
        if max_connections < 1 or not 0 < idle_timeout <= 300:
            raise ValueError("invalid connection or timeout limit")
        self.router = router
        self.ssl_context = ssl_context
        self.semaphore = asyncio.Semaphore(max_connections)
        self.idle_timeout = idle_timeout

    async def start(self, host: str = "127.0.0.1", port: int = 9443):
        return await asyncio.start_server(
            self._handle, host, port, ssl=self.ssl_context,
            limit=MAX_PAYLOAD + HEADER.size
        )

    async def _read_message(self, reader: asyncio.StreamReader) -> dict[str, Any]:
        header = await asyncio.wait_for(reader.readexactly(HEADER.size), self.idle_timeout)
        magic, version, flags, length = HEADER.unpack(header)
        if magic != MAGIC or version != VERSION or flags != 0:
            raise IILPError("invalid magic, version, or flags")
        if length > MAX_PAYLOAD:
            raise IILPError("payload exceeds 1 MiB limit")
        payload = await asyncio.wait_for(reader.readexactly(length), self.idle_timeout)
        try:
            obj = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IILPError("invalid UTF-8 JSON payload") from exc
        return _validate_message(obj)

    async def _write_message(self, writer: asyncio.StreamWriter, message: dict) -> None:
        from iilp import encode
        writer.write(encode(message))
        await writer.drain()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        async with self.semaphore:
            try:
                # One request per connection in this first server profile.
                message = await self._read_message(reader)
                body = message.get("body")
                if not isinstance(body, dict) or not isinstance(body.get("target"), str):
                    raise CoreError("body.target service name is required")
                result = await self.router.dispatch(body["target"], message)
                response = {
                    "type": "response",
                    "id": message["id"],
                    "body": {"ok": True, "result": result},
                }
                await self._write_message(writer, response)
            except (IILPError, CoreError, asyncio.IncompleteReadError, asyncio.TimeoutError) as exc:
                # Keep error details deliberately generic at the network boundary.
                try:
                    await self._write_message(writer, {
                        "type": "error", "id": "server-error",
                        "body": {"ok": False, "error": type(exc).__name__},
                    })
                except (ConnectionError, IILPError):
                    pass
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except ConnectionError:
                    pass
