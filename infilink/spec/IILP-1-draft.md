# IILP/1 — Experimental Wire Protocol Draft

Status: **Experimental proposal**, 2026-11-19. This document does not claim IANA registration, global adoption or standards-body approval.

## 1. Design goals

- Transport-independent message envelope.
- Explicit versioning and message type.
- Bounded parsing to reduce denial-of-service risk.
- Canonical JSON for an initial interoperable control/data representation.
- Extensible metadata without silently changing existing semantics.

IILP is an application protocol. It does not replace IP, TCP, UDP, DNS, TLS, QUIC, HTTP or existing application protocols. Initial deployment should run inside TLS 1.3 over TCP or QUIC. Browser clients should use HTTPS or WebSocket gateways because browser JavaScript cannot open arbitrary raw TCP sockets.

## 2. Frame layout

All integer fields are unsigned big-endian.

| Field | Size | Meaning |
|---|---:|---|
| Magic | 4 bytes | ASCII `IILP` |
| Version | 1 byte | `0x01` |
| Flags | 1 byte | Reserved; MUST be zero in version 1 |
| Payload length | 4 bytes | JSON payload bytes; maximum 1,048,576 |
| Payload | variable | UTF-8 JSON object |

The fixed header is 10 bytes. Receivers MUST reject an incorrect magic, unsupported version, nonzero reserved flags, oversized payload, invalid UTF-8, invalid JSON, or a top-level value other than an object. Implementations MUST read exactly the declared number of bytes and MUST NOT allocate based on an unvalidated length.

## 3. Version 1 message object

Required members:

- `type`: non-empty string, maximum 64 characters.
- `id`: message identifier, non-empty string, maximum 128 characters.
- `body`: JSON value (object recommended).

Optional members:

- `timestamp`: UTC RFC 3339 string.
- `trace_id`: opaque correlation identifier.
- `extensions`: object for namespaced extension data.

Unknown members MUST be ignored unless a negotiated profile says otherwise. Unknown message types MUST produce an explicit unsupported-type error; they must not be executed.

## 4. Security

- Use authenticated TLS 1.3 or QUIC; do not transmit credentials or sensitive payloads over plaintext.
- Authenticate peers and authorize each operation independently.
- Apply connection, frame, rate, concurrency and execution-time limits.
- Avoid automatic code execution, dynamic plugin loading or cross-tenant data access.
- Redact secrets from logs; retain audit events with access controls.
- Cryptographic algorithms and key management MUST use established libraries and standards.

## 5. Transport profiles

- Server-to-server: TLS 1.3 over TCP; optional QUIC profile after interoperability testing.
- Web: HTTPS gateway or WebSocket over TLS.
- Local IPC: explicitly configured Unix domain socket or named pipe with OS permissions.
- Never assume that an arbitrary browser, host or firewall supports a raw IILP socket.

## 6. Error handling

Implementations should return structured errors such as `invalid_frame`, `unsupported_version`, `unsupported_type`, `unauthorized`, `rate_limited` and `internal_error`. Error responses must not disclose secrets or internal stack traces.

## 7. Extensibility and governance

Extensions require a stable namespace, specification, security analysis and conformance tests. A future public specification should define registries, compatibility policy, reference vectors, threat model, privacy requirements and a transparent change process. International adoption requires independent review and participation; it cannot be created by code alone.
