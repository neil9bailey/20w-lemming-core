# ADR-0010: Epic 6A Live Node Realization Matrix

Status: Approved
Date: 2026-07-02
Gate: G1 Architecture
Epic: Epic 6 - Tranche 6A Live Node Realization Matrix

## Context

`main.py` currently owns API routing, context budgeting, graph assembly, node behavior, audit
recording, and telemetry finalization. That makes the runtime difficult to inspect and gives the
appearance that node execution is a gateway-local mock loop instead of a realized LangGraph
state-passing pipeline.

Epic 6A addresses that critique by separating state contracts and node behavior while preserving
the established `/run` response contract used by the Cockpit HUD and markdown export pipeline.

## Decision

- Add `state_schema.py` as the canonical substrate state contract module.
- Add `agent_nodes.py` for four async LEM node functions:
  - `radar_node`
  - `supervisor_node`
  - `rh_core_node`
  - `lh_validator_node`
- Keep `main.py` focused on FastAPI request handling, context-budget construction, secure override
  authorization, LangGraph assembly, async execution locking, performance timing, and persistence.
- Compile the LangGraph workflow once at startup as `app_workflow = workflow.compile()`.
- Make telemetry deterministic inside the node layer:
  - `E_c = 10.0 + (variance_threshold / 10.0) * math.log2(max(1, lookahead_horizon))`
  - `delta_a` is the normalized sycophantic-pattern hit density over processed node strings.
  - `S_d` remains `0.5` for adversarial/intercepted routes and otherwise uses deterministic
    autonomous-decision ratio.
- Keep adversarial override authorization environment-backed with no code default. If the runtime
  environment lacks `ADVERSARIAL_OVERRIDE_KEY`, reject override attempts before graph execution.

## Consequences

- Node behavior becomes independently testable and inspectable.
- `main.py` stops owning LEM persona logic and becomes a clean gateway/graph composition layer.
- Existing Cockpit consumers keep the same JSON keys and HUD mappings.
- The current lock remains process-local; multi-worker deployments would still require a shared
  queue or distributed lock for cross-process serialization.

## Verification

- `python -m compileall state_schema.py agent_nodes.py main.py`
- `docker compose up -d --build --force-recreate`
- POST `/run` through the Docker-exposed API and confirm the returned trace includes:
  - populated `visited_nodes`
  - governance audit hash entries
  - deterministic `E_c`, `delta_a`, and `S_d`
  - response keys consumed by the Cockpit HUD
- Confirm no private paths or credential literals are introduced by this tranche.
