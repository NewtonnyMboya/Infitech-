"""INFILINK Bridge: bounded HTTP/JSON gateway and allowlisted HTTPS client.

The WSGI gateway is intended to run behind a TLS-terminating reverse proxy.
It does not provide authentication by itself; deploy it only on a trusted network
until an authentication/authorization middleware is configured.
"""
from __future__ import annotations

import asyncio
import json
import re
import ssl
import urllib.error
import urllib.request
from typing import Any, Callable
from urllib.parse import urlsplit

from core import CoreError, MessageRouter
from iilp import IILPError, decode_frame, encode

_MAX_HTTP_BODY = 1_048_576
_SERVICE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")


class BridgeError(RuntimeError):
    """Rejected or failed bridge operation."""


def json_to_iilp(service: str, payload: Any, message_id: str) -> dict[str, Any]:
    """Convert a JSON object into a validated IILP request envelope."""
    if not isinstance(service, str) or not _SERVICE.fullmatch(service):
        raise BridgeError("invalid service name")
    if not isinstance(payload, dict):
        raise BridgeError("HTTP JSON payload must be an object")
    message = {
        "type": payload.get("type"),
        "id": message_id,
        "body": {"target": service, **payload.get("body", {})}
        if isinstance(payload.get("body"), dict) else None,
    }
    if message["body"] is None:
        raise BridgeError("payload.body must be a JSON object")
    try:
        return decode_frame(encode(message))
    except IILPError as exc:
        raise BridgeError("invalid IILP message fields") from exc


def iilp_to_json(message: dict[str, Any]) -> bytes:
    """Serialize a validated response envelope as compact JSON."""
    try:
        return json.dumps(message, ensure_ascii=False, separators=(",", ":"),
                          allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise BridgeError("response is not interoperable JSON") from exc


class HTTPJSONGateway:
    """WSGI gateway mapping POST /v1/services/{name}/messages to Core handlers."""

    def __init__(self, router: MessageRouter, max_body_bytes: int = _MAX_HTTP_BODY) -> None:
        if not 1 <= max_body_bytes <= _MAX_HTTP_BODY:
            raise ValueError("max_body_bytes must be between 1 and 1 MiB")
        self.router = router
        self.max_body_bytes = max_body_bytes

    def __call__(self, environ: dict[str, Any], start_response: Callable):
        method = environ.get("REQUEST_METHOD", "")
        path = environ.get("PATH_INFO", "")
        if method == "GET" and path == "/health":
            return self._respond(start_response, "200 OK", {"ok": True, "service": "infilink-bridge"})
        match = re.fullmatch(r"/v1/services/([A-Za-z][A-Za-z0-9_.-]{0,63})/messages", path)
        if method != "POST" or not match:
            return self._respond(start_response, "404 Not Found", {"error": "not_found"})
        try:
            raw_length = environ.get("CONTENT_LENGTH", "")
            if not raw_length or not str(raw_length).isdigit():
                raise BridgeError("content length required")
            length = int(raw_length)
            if length < 1 or length > self.max_body_bytes:
                raise BridgeError("request body size is invalid")
            stream = environ["wsgi.input"]
            raw = stream.read(length)
            if len(raw) != length:
                raise BridgeError("incomplete request body")
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise BridgeError("request must contain UTF-8 JSON") from exc
            request_id = environ.get("HTTP_X_REQUEST_ID", "http-bridge")
            if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
                raise BridgeError("invalid request id")
            message = json_to_iilp(match.group(1), payload, request_id)
            result = asyncio.run(self.router.dispatch(match.group(1), message))
            response = {"type": "response", "id": request_id,
                        "body": {"ok": True, "result": result}}
            return self._respond(start_response, "200 OK", response)
        except (BridgeError, CoreError, IILPError) as exc:
            return self._respond(start_response, "400 Bad Request",
                                 {"error": "invalid_request", "detail": str(exc)[:160]})
        except Exception:
            return self._respond(start_response, "500 Internal Server Error",
                                 {"error": "internal_error"})

    @staticmethod
    def _respond(start_response: Callable, status: str, value: dict[str, Any]):
        body = iilp_to_json(value)
        start_response(status, [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
        ])
        return [body]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class AllowlistedHTTPSClient:
    """Small outbound JSON client restricted to exact HTTPS origins.

    Redirects are disabled so a permitted host cannot redirect requests elsewhere.
    This client is not a replacement for provider-specific authentication or SDKs.
    """

    def __init__(self, allowed_origins: set[str], timeout: float = 8.0,
                 max_response_bytes: int = _MAX_HTTP_BODY) -> None:
        if not allowed_origins:
            raise ValueError("at least one HTTPS origin must be allowlisted")
        normalized = set()
        for origin in allowed_origins:
            parsed = urlsplit(origin)
            if parsed.scheme != "https" or not parsed.hostname or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
                raise ValueError("allowlist entries must be HTTPS origins only")
            if parsed.username or parsed.password:
                raise ValueError("credentials are not allowed in origin")
            normalized.add(f"https://{parsed.netloc.lower()}")
        if not 0 < timeout <= 30:
            raise ValueError("timeout must be in (0, 30]")
        if not 1 <= max_response_bytes <= _MAX_HTTP_BODY:
            raise ValueError("max_response_bytes must be between 1 and 1 MiB")
        self.allowed_origins = normalized
        self.timeout = timeout
        self.max_response_bytes = max_response_bytes
        self._opener = urllib.request.build_opener(_NoRedirect())

    def post_json(self, url: str, payload: dict[str, Any],
                  headers: dict[str, str] | None = None) -> dict[str, Any]:
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}".lower()
        if parsed.scheme != "https" or origin not in self.allowed_origins:
            raise BridgeError("destination is not an allowlisted HTTPS origin")
        if parsed.username or parsed.password or not parsed.hostname:
            raise BridgeError("invalid destination URL")
        try:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"),
                              allow_nan=False).encode("utf-8")
        except (TypeError, ValueError, UnicodeError) as exc:
            raise BridgeError("request payload is not JSON serializable") from exc
        if len(body) > _MAX_HTTP_BODY:
            raise BridgeError("request exceeds 1 MiB limit")
        request_headers = {"Content-Type": "application/json", "Accept": "application/json"}
        for key, value in (headers or {}).items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise BridgeError("headers must contain string keys and values")
            if key.lower() in {"host", "content-length", "connection", "transfer-encoding"}:
                raise BridgeError("restricted HTTP header")
            request_headers[key] = value
        request = urllib.request.Request(url, data=body, headers=request_headers, method="POST")
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                data = response.read(self.max_response_bytes + 1)
                if len(data) > self.max_response_bytes:
                    raise BridgeError("external response exceeds configured limit")
                if response.status < 200 or response.status >= 300:
                    raise BridgeError(f"external service returned HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            raise BridgeError(f"external service returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, ssl.SSLError) as exc:
            raise BridgeError("external HTTPS request failed") from exc
        try:
            result = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BridgeError("external service did not return UTF-8 JSON") from exc
        if not isinstance(result, dict):
            raise BridgeError("external service response must be a JSON object")
        return result


def create_wsgi_app(router: MessageRouter) -> HTTPJSONGateway:
    """Convenience factory for WSGI servers such as wsgiref or gunicorn."""
    return HTTPJSONGateway(router)
