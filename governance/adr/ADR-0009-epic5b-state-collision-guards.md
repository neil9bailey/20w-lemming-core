# ADR-0009: Epic 5B State Collision Guards

Status: Approved
Date: 2026-07-02
Gate: G1 Architecture
Epic: Epic 5 - Tranche 5B State Collision Guards & Atomic Locking

## Context

The Cockpit can trigger rapid consecutive `/run` requests against a shared LangGraph substrate and
SQLite-backed memory layer. Prior tranches added richer graph state, dynamic history retrieval,
audit trails, and context balancing. Without a single execution boundary, concurrent invocations
could interleave graph state mutation and persistence in ways that are hard to reason about.

The current API returns the final graph state dictionary directly, so lock contention telemetry can
be added to the existing state contract without introducing a second response wrapper.

## Decision

- Instantiate one process-local `asyncio.Lock` after the FastAPI application is created.
- Check `substrate_execution_lock.locked()` before acquiring the lock and carry that result through
  the run as `lock_contention_detected`.
- Keep adversarial override authentication outside the lock so denied requests fail before graph
  execution or persistence.
- Execute state construction, graph invocation, performance timing, final telemetry derivation, and
  `record_run` persistence inside `async with substrate_execution_lock`.
- Return `lock_contention_detected` in the final state payload for Cockpit telemetry.
- Render a yellow Cockpit terminal warning when the response indicates the request queued behind an
  active substrate lock.

## Consequences

- In a single backend worker process, `/run` requests mutate and persist substrate state
  sequentially.
- Contended requests are not rejected; they queue behind the active lock and complete normally.
- The guard is process-local. Multi-worker or horizontally scaled deployments would require a
  distributed lock or queue before this guarantee spans processes.
- Unauthorized adversarial override requests still return HTTP 403 without entering the locked graph
  section.

## Verification

- `python -m compileall main.py`
- `docker compose up -d --build --force-recreate`
- Fire concurrent POST requests to `/run`; confirm HTTP 200 responses, unique run IDs, and at least
  one response with `lock_contention_detected = true`.
- Confirm Cockpit JavaScript includes the yellow `[CONCURRENCY]` warning mapping.
- Confirm no private host paths or credential literals are introduced.
