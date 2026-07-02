# ADR-0011: Tranche 1.3C Container Perimeter Hardening

Status: Approved
Date: 2026-07-02
Gate: G1 Architecture
Epic: Tranche 1.3C - Operational Hosting Hardening

## Context

The backend API has been exposed directly on host port `8001`, while the Cockpit is served by
Nginx on port `8080`. Tranche 1.3B added client-side perimeter headers, but direct host access to
the backend still allows callers to bypass the Nginx perimeter route. The local Docker runtime also
lacks explicit resource ceilings and active health probes, increasing the blast radius of parallel
lookahead workloads.

## Decision

- Remove the backend host port mapping and keep backend traffic private on the `lemming_net` bridge.
- Keep Nginx as the sole host-exposed service on port `8080`.
- Route browser API calls through `/api/`, rewriting to the internal backend container on port
  `8001`.
- Add backend and cockpit resource limits of `1.0` CPU and `1G` memory.
- Add a backend `/health` Docker healthcheck.
- Update the Cockpit API base URL to use the current origin plus `/api`.

## Consequences

- External local clients can no longer bypass Nginx by calling host port `8001`.
- The Cockpit and backend communicate through the private Compose network.
- The UI must call `/api` instead of direct backend host ports.
- Resource ceilings constrain runaway workloads but may throttle intentionally heavy local probes.

## Verification

- `docker compose config`
- `docker compose up -d --build --force-recreate`
- `docker compose ps`
- `GET http://localhost:8080/api/health`
- `POST http://localhost:8080/api/run`
- Confirm host port `8001` is no longer published.
