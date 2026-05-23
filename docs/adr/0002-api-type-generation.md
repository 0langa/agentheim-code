# ADR 0002: API Type Generation

## Status

Accepted

## Context

The backend is FastAPI-first and exposes an OpenAPI schema at `/openapi.json`. The
frontend is TypeScript and currently maintains hand-written types in
`apps/web/src/types.ts`. Keeping these in sync manually is error-prone as the API
surface grows.

## Decision

Adopt `openapi-typescript` as the generation tool. The workflow is:

1. Start the local backend.
2. Run `npm --prefix apps/web run types:api`.
3. The tool fetches `http://127.0.0.1:8765/openapi.json` and emits
   `apps/web/src/generated/api-types.ts`.

Generated types are reproducible: any developer with a running backend can
regenerate them. Hand-written types in `apps/web/src/types.ts` remain the
fallback for UI-only types (e.g. component props) and for areas where the
OpenAPI schema is not yet expressive enough.

## Consequences

- The frontend can rely on strongly typed API contracts without manual drift.
- CI does not need to run generation on every build; the checked-in generated
  file is the source of truth until it is intentionally refreshed.
- Backend changes that alter the OpenAPI schema should be followed by a
  regeneration commit.
