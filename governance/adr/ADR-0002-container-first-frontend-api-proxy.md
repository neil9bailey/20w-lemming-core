# ADR-0002: Container Gateway Backend Base URL

Status: Approved
Date: 2026-07-01
Gate: G1 Architecture
Epic: 20W-container-first-networking-alignment

## Context

The cockpit is served by an Nginx container and the FastAPI backend runs as a separate Docker
Compose service. Browser JavaScript executes in the user's browser, outside the Docker network,
so Docker service DNS names such as `backend` cannot be resolved directly by the page.

Epic 1 now requires the cockpit to resolve API traffic through the standard browser-visible
Docker Desktop gateway port for the backend container. The frontend must not contain hardcoded
loopback targets such as `localhost:8001`, `localhost:8002`, or `127.0.0.1`.

## Decision

The cockpit will derive the backend base URL from the current browser hostname and the standard
exposed API container gateway port:

```javascript
const getBackendBaseUrl = () => {
    const currentHost = window.location.hostname;
    // Resolve cleanly to the standard exposed API container gateway port
    return `http://${currentHost}:8001`;
};
```

The backend service remains a Docker Compose service and publishes container port `8001` to host
port `8001`. The frontend container remains the browser entrypoint for the cockpit UI on port
`8080`.

## Consequences

- Browser UI traffic uses `http://<frontend-host>:8080/`.
- Browser API traffic uses `http://<same-host>:8001/...`.
- The implementation follows Docker Desktop port publishing, not a locally run FastAPI process.
- FastAPI must continue to allow browser CORS from the cockpit origin.
- Any Nginx `/api` proxy may remain as a compatibility route, but it is not the primary API base
  selected by the cockpit UI.

## Verification

- Rebuild and restart the Docker Compose stack.
- Confirm backend container is published as `0.0.0.0:8001->8001/tcp`.
- Confirm frontend container is published as `0.0.0.0:8080->80/tcp`.
- Confirm `GET http://127.0.0.1:8001/health` returns `ONLINE` from the containerized backend.
- Confirm `POST http://127.0.0.1:8001/run` returns mathematical telemetry.
- Confirm the served `index.html` contains the dynamic hostname resolver, telemetry cards, and
  clipboard export path.
- Confirm `index.html` contains no hardcoded `localhost:8001`, `localhost:8002`, or
  `127.0.0.1` API targets.
