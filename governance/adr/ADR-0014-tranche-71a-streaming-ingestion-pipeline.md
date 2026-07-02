# ADR-0014: Tranche 7.1A Streaming Ingestion Pipeline

Status: Approved
Date: 2026-07-02
Gate: G1 Architecture
Epic: Tranche 7.1A - Streaming Ingestion Pipeline

## Context

The current `/run` endpoint waits for the compiled LangGraph invocation to finish before returning a
single JSON payload. Epic 7 needs progressive multi-source ingestion observability so callers can
consume node state mutations as each LEM node executes.

## Decision

- Add a streaming run endpoint exposed through the Nginx perimeter as `/api/stream-run`.
- Keep the existing substrate auth guard, adversarial override guard, and global async execution lock.
- Use `app_workflow.astream(initial_state)` to emit each LangGraph node mutation as a server-sent
  event chunk.
- Preserve `/run` as the blocking JSON contract.
- Normalize large or JSON-array-like evidence contexts in `supervisor_node` by splitting them into
  deterministic chunks, compressing linguistic filler concurrently, and rejoining the refined
  context into the state carrier before downstream nodes execute.

## Consequences

- Streaming clients can render node progress without waiting for the final state.
- The lock prevents concurrent graph mutation during the stream lifetime.
- The endpoint remains protected by `X-Substrate-Auth`.
- `/api/stream-run` is served by Nginx and rewritten to the backend route `/stream-run`.

## Verification

- `python -m compileall main.py agent_nodes.py`
- `docker compose up -d --build --force-recreate`
- Trigger `POST http://localhost:8080/api/stream-run` with a valid substrate token and confirm
  multiple `data:` chunks are received.
