# ADR-0003: Epic 3B Adversarial Routing and Persistence Metrics

Status: Approved
Date: 2026-07-01
Gate: G1 Architecture
Epic: Epic 3 - Tranche 3B Backend Persistence and Routing Overrides

## Context

Epic 3A introduced a cockpit-only adversarial toggle that annotates ingestion requests with
`simulate_radar_failure`. Epic 3B promotes that annotation into a backend runtime contract. The
backend must return authoritative intercept telemetry, route the graph through the degraded radar
path, and persist technical execution metrics for audit and later hardening.

The existing system already starts graph execution at LEM-04 and conditionally routes to either
LEM-01 or LEM-03. The existing SQLite persistence table is `runs`; there is no separate
`cognitive_history` table in the current codebase.

## Decision

- Add `simulate_radar_failure: bool = False` to the `/run` request schema.
- Add `intercept_triggered: bool` and `velocity_ms: float` to the returned run state.
- When `simulate_radar_failure` is true, LEM-04 forces the degraded path and routes directly to
  LEM-03, bypassing LEM-01 and LEM-02.
- The intercepted path returns:
  - `visited_nodes = ["LEM-04", "LEM-03"]`
  - `pruning_percentage = 0.5`
  - `S_d = 0.5`
  - `intercept_triggered = true`
- Use `time.perf_counter()` around the LangGraph invocation to calculate `velocity_ms`.
- Expand the existing `runs` table with migration-safe columns:
  - `velocity_ms REAL`
  - `intercept_triggered INTEGER`
  - `raw_prompt_length INTEGER`

## Consequences

- The frontend can distinguish simulated adversarial backend runs from nominal runs using
  `intercept_triggered`.
- Existing SQLite databases remain usable because columns are added with `ALTER TABLE` when
  missing.
- Existing run history remains intact; legacy rows receive default values for new metrics.
- The backend remains deterministic for the same request payload.

## Verification

- `python -m compileall main.py memory_store.py`
- `docker compose up -d --build`
- POST `/run` with `simulate_radar_failure: true` and confirm direct LEM-04 to LEM-03 traversal,
  `S_d = 0.5`, `pruning_percentage = 0.5`, `intercept_triggered = true`, and `velocity_ms`.
- Inspect SQLite `runs` schema and latest row for `velocity_ms`, `intercept_triggered`, and
  `raw_prompt_length`.
