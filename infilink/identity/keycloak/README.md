# INFILINK Keycloak identity service

This directory provides a **local development-only** Keycloak deployment. It is not a production deployment.

## Components

- Keycloak `26.8.2`, pinned to a release rather than `latest`.
- PostgreSQL `17.6` with a persistent named volume.
- Keycloak is bound to `127.0.0.1:8081`; PostgreSQL is not published to the host.
- The Docker network is internal to these services.

## Start locally

From this directory:

```bash
cp .env.example .env
```

Edit `.env` and replace all three placeholder passwords with unique random values. Then start Docker Compose:

```bash
docker compose up -d
docker compose ps
docker compose logs -f keycloak
```

Open the local administration console:

```
http://127.0.0.1:8081
```

Sign in with the bootstrap admin username and password from `.env`. Keep these credentials private. To stop the services:

```bash
docker compose down
```

To stop and **delete the persistent Keycloak database volume** (destructive):

```bash
docker compose down -v
```

## Configure the INFILINK realm

After Keycloak starts, create a realm named `infilink`. In that realm:

1. Create an OIDC client named `infilink-web`.
2. Use Authorization Code Flow (Standard Flow) with PKCE using `S256`.
3. Keep Direct Access Grants and Implicit Flow disabled.
4. Configure exact redirect URIs and web origins for the eventual INFILINK HTTPS application. Do not use broad wildcards.
5. Configure the access-token audience so the access token contains the audience expected by the INFILINK API verifier.
6. Create only the roles needed by the application, and map those roles explicitly to INFILINK scopes.
7. Keep client credentials and service-account privileges disabled unless a separately reviewed server-to-server use case requires them.

The current INFILINK verifier requires the access token's `azp` claim to equal the configured client ID (`infilink-web`), validates issuer/audience/signature/expiry, and maps only explicitly configured roles.

## Important HTTPS boundary

This compose file intentionally uses Keycloak's `start-dev` mode and plain HTTP on loopback. It is for local administration and integration development only. Do not expose port 8081 to a LAN or the public Internet, and do not point the production INFILINK verifier at this HTTP issuer.

Before live INFILINK authentication is enabled, deploy Keycloak behind a correctly configured HTTPS reverse proxy with a fixed public hostname, trusted proxy headers, and a supported production database configuration. The issuer and JWKS URLs used by INFILINK must be HTTPS and must exactly match Keycloak's OIDC discovery metadata. The reverse proxy must overwrite forwarded headers and prevent direct untrusted access to the Keycloak backend.

For production, follow the official [Keycloak container guide](https://www.keycloak.org/server/containers), [hostname configuration](https://www.keycloak.org/server/hostname), and [production configuration guide](https://www.keycloak.org/server/configuration-production). Do not reuse the local development compose file as a production template.

## Current integration boundary

INFILINK currently contains a Keycloak OIDC token-verification adapter. It does not yet implement the browser Authorization Code + PKCE redirect/callback flow, state/nonce storage, code exchange, production session persistence, or end-to-end logout/revocation. Those are separate milestones and must be tested against a real HTTPS Keycloak realm before production use.
