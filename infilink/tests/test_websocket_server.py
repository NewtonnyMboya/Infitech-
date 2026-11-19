import ssl
import unittest
from types import SimpleNamespace

from core import MessageRouter, ServiceRegistry
from iilp import decode_frame, encode
from websocket_server import IILPWebSocketServer, WebSocketTransportError, MAX_FRAME_BYTES


class FakeWebSocket:
    def __init__(self, origin="https://app.example.test"):
        self.request = SimpleNamespace(headers={"Origin": origin, "Cookie": "session=opaque"})
        self.closed = None
        self.subprotocol = "iilp.v1"
        self.sent = []
    async def close(self, code=1000, reason=""):
        self.closed = (code, reason)
    async def send(self, data):
        self.sent.append(data)


class WebSocketServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        registry = ServiceRegistry()
        async def echo(message):
            return {"echo": message["body"].get("value")}
        await registry.register("echo", echo, {"echo"})
        self.router = MessageRouter(registry)
        self.server = IILPWebSocketServer(
            self.router,
            ssl.create_default_context(ssl.Purpose.CLIENT_AUTH),
            allowed_origins={"https://app.example.test"},
            authenticate=lambda headers: {"subject": "browser-session"},
            authorize=lambda principal, service, message: (
                principal["subject"] == "browser-session" and service == "echo"
            ),
        )

    async def test_valid_binary_frame_dispatches_and_preserves_id(self):
        frame = encode({"type": "echo", "id": "browser-123", "body": {
            "target": "echo", "value": "hello"
        }})
        response = decode_frame(await self.server._dispatch_frame(
            frame, {"subject": "browser-session"}
        ))
        self.assertEqual(response["type"], "response")
        self.assertEqual(response["id"], "browser-123")
        self.assertEqual(response["body"]["result"], {"echo": "hello"})

    async def test_authorization_denial_returns_generic_error(self):
        frame = encode({"type": "echo", "id": "browser-124", "body": {
            "target": "echo", "value": "hello"
        }})
        response = decode_frame(await self.server._dispatch_frame(frame, {"subject": "other"}))
        self.assertEqual(response["type"], "error")
        self.assertEqual(response["id"], "browser-124")
        self.assertEqual(response["body"]["error"], "WebSocketTransportError")

    async def test_text_frames_are_rejected(self):
        with self.assertRaises(WebSocketTransportError):
            await self.server._dispatch_frame('not binary', {"subject": "browser-session"})

    async def test_handshake_checks_origin_and_authentication(self):
        ws = FakeWebSocket()
        principal = await self.server._authenticate(ws)
        self.assertEqual(principal["subject"], "browser-session")
        bad_origin = FakeWebSocket("https://attacker.example")
        with self.assertRaises(WebSocketTransportError):
            await self.server._authenticate(bad_origin)

    async def test_handler_closes_unauthenticated_connection(self):
        ws = FakeWebSocket("https://attacker.example")
        await self.server._handler(ws)
        self.assertEqual(ws.closed[0], 1008)


    async def test_missing_principal_is_rejected(self):
        server = IILPWebSocketServer(
            self.router,
            ssl.create_default_context(ssl.Purpose.CLIENT_AUTH),
            allowed_origins={"https://app.example.test"},
            authenticate=lambda headers: None,
            authorize=lambda principal, service, message: True,
        )
        with self.assertRaises(WebSocketTransportError):
            await server._authenticate(FakeWebSocket())

    async def test_async_authentication_callback_is_supported(self):
        async def authenticate(headers):
            return {"subject": "async-session"}
        server = IILPWebSocketServer(
            self.router,
            ssl.create_default_context(ssl.Purpose.CLIENT_AUTH),
            allowed_origins={"https://app.example.test"},
            authenticate=authenticate,
            authorize=lambda principal, service, message: True,
        )
        principal = await server._authenticate(FakeWebSocket())
        self.assertEqual(principal["subject"], "async-session")

    async def test_malformed_binary_frame_returns_protocol_error(self):
        response = decode_frame(await self.server._dispatch_frame(
            b"not-an-iilp-frame", {"subject": "browser-session"}
        ))
        self.assertEqual(response["type"], "error")
        self.assertFalse(response["body"]["ok"])

    async def test_oversized_frame_is_rejected_before_decode(self):
        with self.assertRaises(WebSocketTransportError):
            await self.server._dispatch_frame(
                b"x" * (MAX_FRAME_BYTES + 1), {"subject": "browser-session"}
            )

    async def test_missing_service_target_returns_error(self):
        frame = encode({"type": "echo", "id": "browser-125", "body": {"value": "hello"}})
        response = decode_frame(await self.server._dispatch_frame(
            frame, {"subject": "browser-session"}
        ))
        self.assertEqual(response["type"], "error")
        self.assertFalse(response["body"]["ok"])


if __name__ == "__main__":
    unittest.main()
