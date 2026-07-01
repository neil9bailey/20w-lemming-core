# ADR-0001: v1.2 Telemetry and SQLite Persistence

Status: Approved
Date: 2026-07-01
Gate: G1 Architecture
Epic: 20W-v1.2-first-tranche

## Context

The v1.2 tranche approved by the Conductor requires the 20W Lemming substrate to:

- Replace the four Lemming directives with the hardened v1.2 directives.
- Calculate cognitive and drift telemetry during each run.
- Persist run history and strategic bias vectors in a lightweight local store.
- Inject a short Neil Strategic Bias Profile into LEM-01 and LEM-02 startup state.

The current baseline is a single FastAPI and LangGraph service in `main.py` with no persistence
layer and no durable run history.

## Decision

Use a local SQLite database named `20w_memory.db` and a small repository-local memory module for
v1.2 persistence. The FastAPI/LangGraph runtime remains a single-process local service, and the
graph topology remains unchanged.

The database owns two tables for this tranche:

- `runs`: run-level telemetry and outcome history.
- `bias_vectors`: reusable alignment patterns for the Neil Strategic Bias Profile.

Telemetry values are calculated in-process and written into graph state:

- `E_c`: cognitive energy.
- `delta_a`: alignment drift.
- `S_d`: sovereignty drift.

The memory module loads recent successful runs and bias vectors at startup time for each `/run`
request, builds a concise Neil Strategic Bias Profile, and injects it into LEM-01 and LEM-02 state.

## Architecture Constraints

- No new agents are introduced.
- No major graph topology refactor is introduced.
- SQLite is local only and does not add network or cloud dependencies.
- The database file is runtime state and must not be committed.
- Persistence failure must not crash the graph unless the schema cannot be initialized.

## Verification

- Python compile checks for modified modules.
- API smoke test that invokes `/run` through FastAPI test client.
- SQLite inspection confirming `runs` and `bias_vectors` exist and that a run record is stored.
- State inspection confirming `E_c`, `delta_a`, `S_d`, and `bias_profile` are returned.

## Consequences

This creates a small durable state boundary for v1.2 while preserving the current single-service
runtime. Future tranches can extend the persistence schema through new ADRs if they alter data
contracts, add external stores, or introduce new graph topology.
