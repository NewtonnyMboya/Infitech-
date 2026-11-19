import io
import json
import unittest

from bridge import AllowlistedHTTPSClient, BridgeError, HTTPJSONGateway, json_to_iilp
from core import MessageRouter, ServiceRegistry


class BridgeTests(unittest.TestCase):
    def test_json_to_iilp(self):
        msg = json_to_iilp("echo", {"type": "echo", "body": {"text": "hello"}}, "req-1")
        self.assertEqual(msg["body"]["target"], "echo")
        self.assertEqual(msg["body"]["text"], "hello")
        injected = json_to_iilp("echo", {"type": "echo", "body": {"target": "admin"}}, "req-2")
        self.assertEqual(injected["body"]["target"], "echo")

    def test_reject_invalid_gateway_payload(self):
        with self.assertRaises(BridgeError):
            json_to_iilp("../admin", {"type": "x", "body": {}}, "id")
        with self.assertRaises(BridgeError):
            json_to_iilp("echo", {"type": "x", "body": []}, "id")

    def test_gateway_health(self):
        gateway = HTTPJSONGateway(MessageRouter(ServiceRegistry()))
        captured = {}
        def start(status, headers):
            captured["status"] = status
            captured["headers"] = dict(headers)
        result = gateway({"REQUEST_METHOD": "GET", "PATH_INFO": "/health"}, start)
        self.assertEqual(captured["status"], "200 OK")
        self.assertTrue(json.loads(result[0])["ok"])
        self.assertEqual(captured["headers"]["Cache-Control"], "no-store")

    def test_gateway_dispatch(self):
        import asyncio
        registry = ServiceRegistry()
        async def echo(message):
            return {"text": message["body"]["text"]}
        asyncio.run(registry.register("echo", echo, {"echo"}))
        gateway = HTTPJSONGateway(MessageRouter(registry))
        raw = json.dumps({"type": "echo", "body": {"text": "hello"}}).encode()
        environ = {"REQUEST_METHOD": "POST",
                   "PATH_INFO": "/v1/services/echo/messages",
                   "CONTENT_LENGTH": str(len(raw)), "wsgi.input": io.BytesIO(raw)}
        captured = {}
        def start(status, headers):
            captured["status"] = status
        result = gateway(environ, start)
        self.assertEqual(captured["status"], "200 OK")
        self.assertEqual(json.loads(result[0])["body"]["result"]["text"], "hello")

    def test_gateway_rejects_oversized_or_wrong_method(self):
        gateway = HTTPJSONGateway(MessageRouter(ServiceRegistry()), max_body_bytes=32)
        captured = {}
        def start(status, headers):
            captured["status"] = status
        environ = {"REQUEST_METHOD": "POST", "PATH_INFO": "/v1/services/echo/messages",
                   "CONTENT_LENGTH": "100", "wsgi.input": io.BytesIO(b"x" * 100)}
        gateway(environ, start)
        self.assertEqual(captured["status"], "400 Bad Request")

    def test_https_client_allowlist_validation(self):
        with self.assertRaises(ValueError):
            AllowlistedHTTPSClient({"http://example.com"})
        client = AllowlistedHTTPSClient({"https://api.example.com"})
        with self.assertRaises(BridgeError):
            client.post_json("https://other.example.com/data", {})


if __name__ == "__main__":
    unittest.main()
