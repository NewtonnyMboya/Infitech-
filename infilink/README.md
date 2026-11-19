# INFILINK

**International InfiLink Protocol (IILP)** is a proposed, open, versioned interoperability layer for applications and services. This repository starts with a deliberately small, testable foundation rather than claiming universal compatibility prematurely.

## Architecture

- **IILP wire format** — bounded, versioned messages with canonical JSON payloads.
- **IIL Runtime** — language adapters and execution backends (planned).
- **IIL DataCore** — storage connectors, schemas, indexes, replication and retrieval (planned).
- **IIL Bridge** — protocol, markup, language and API adapters (planned).
- **IIL Cloud** — deployable services and hosting adapters (planned).
- **IIL Security** — TLS/QUIC transport profiles, identity, authorization, audit and key management (planned).
- **IIL Browser** — standards-based web integration; browsers remain compatible through HTTPS, WebSocket and Web APIs (planned).

## Compatibility strategy

Do not reimplement every language, server, browser, operating system or Internet protocol. Integrate through documented adapters and existing standards: HTTP(S), DNS, TLS, TCP, QUIC, WebSocket, OAuth/OIDC, SQL, object storage and language-specific runtimes. Unsupported features must fail explicitly and safely.

## Current implementation

`runtime/python/iilp.py` provides a cross-platform Python reference codec for the IILP/1 frame format. `runtime/python/core.py` provides a bounded service registry and message router; `runtime/python/server.py` provides a TLS-context-required reference server. `runtime/python/datacore.py` provides a SQLite-backed document store with schema validation, indexes, backup and integrity checks. Node.js has a matching IILP codec under `runtime/javascript/`.

Run:

```sh
python3 runtime/python/iilp.py --self-test
```

## Engineering rules

1. No unbounded "infinite loop": background reconciliation must be bounded, observable, cancellable and rate-limited.
2. Validate every frame, schema, identity and authorization decision at trust boundaries.
3. Use TLS 1.3 or QUIC security; never invent cryptography.
4. Make schemas versioned and migrations reversible where possible.
5. Test conformance across operating systems and language implementations.
6. Treat IILP as an experimental protocol until reviewed, published, interoperably implemented and assigned any necessary protocol identifiers.

## Status

Early draft / experimental. The DataCore SQLite adapter is a local reference implementation; remote adapters, replication and production security operations remain unimplemented. IILP is not an Internet standard and is not yet suitable for production or sensitive data.
