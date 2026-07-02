# ADR-0012: Tranche 1.4 Bias Matrix Adaptation

Status: Approved
Date: 2026-07-02
Gate: G1 Architecture
Epic: Tranche 1.4A/1.4B - Dynamic Bias Matrix Adaptation

## Context

The persistence layer stores bias vectors as textual descriptors and scalar strengths, while the
runtime graph uses a static bias profile string. Tranche 1.4 introduces operator-scored adaptive
weights that must survive across runs and influence node instructions.

## Decision

- Add four numeric bias columns to `bias_vectors`:
  - `supervisor_bias`
  - `validator_bias`
  - `creative_bias`
  - `radar_bias`
- Add an async `update_bias_profile(profile_name, score_adjustment)` mutator.
- Positive score adjustments increase `validator_bias` and `supervisor_bias` by `0.02`, capped at
  `1.00`.
- Negative score adjustments increase `creative_bias` and `radar_bias` by `0.03`, capped at `1.00`.
- Add safe database fallback boundaries around memory reads/writes so disk access exceptions do not
  crash the graph.
- Load the active bias row during `/run` initialization and inject it into `initial_state` as
  `active_bias_profile`.
- Append `[BIAS ENFORCEMENT FACTOR: X]` instructions inside supervisor and RH-core node outputs.

## Consequences

- Existing databases migrate additively without dropping historical runs.
- Bias mutations become persistent and parameterized.
- Node behavior can surface active numeric bias weights without changing the public `/run` request
  payload.
- Database failures degrade to baseline bias defaults instead of collapsing graph execution.

## Verification

- `python -m compileall memory_store.py main.py agent_nodes.py state_schema.py`
- Exercise `update_bias_profile(...)` against SQLite.
- Rebuild Docker and execute `POST /api/run`.
- Confirm response contains `active_bias_profile` and node messages include bias enforcement
  factors.
