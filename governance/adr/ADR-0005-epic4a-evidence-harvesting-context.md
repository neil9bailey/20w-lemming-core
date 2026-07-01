# ADR-0005: Epic 4A Evidence Harvesting Context

Status: Approved
Date: 2026-07-01
Gate: G1 Architecture
Epic: Epic 4 - Tranche 4A Evidence Harvesting Modules

## Context

Epic 4 introduces Strategic Asset Injection so the Lemming substrate can reason over operator
provided evidence instead of relying only on the strategic target prompt. Tranche 4A adds an
external text channel, called the Evidence Block, to the Cockpit and the `/run` contract.

The current graph state is implemented as `LemmingState`, a LangGraph `TypedDict`, with
`IngestionRequest` as the Pydantic API schema. There is no separate `SubstrateState` Pydantic model
in the current codebase, so this tranche extends the existing graph state contract directly.

## Decision

- Add `evidence_context: str = ""` to `IngestionRequest`.
- Add `evidence_context: str` to `LemmingState` and preserve it through the initial state passed to
  LangGraph.
- Make LEM-01 include evidence-aware payload metadata when evidence is present, including the
  header `[VERIFIED EVIDENCE ATTACHED: COMPILING BOUNDARIES]`.
- Make LEM-02 generate strategic layers anchored to a compact excerpt of the provided evidence
  context instead of purely generic market hypotheses.
- Add an Evidence Block textarea to the Cockpit directly below the Strategic Target input and send
  its trimmed value as `evidence_context`.
- Prepend a Harvester terminal log when active evidence is sent to the backend.

## Consequences

- Existing clients remain compatible because `evidence_context` defaults to an empty string.
- Evidence text is returned in the graph state and is visible to downstream agents through the
  state object and supervisor payload.
- The Cockpit can drive evidence-backed ingestion without changing container topology.
- Large evidence blocks are not summarized by an external model in this tranche; LEM-02 uses a
  bounded excerpt for deterministic local traces.

## Verification

- `python -m compileall main.py`
- `docker compose up -d --build`
- POST `/run` with both `target_prompt` and `evidence_context`; confirm HTTP 200, the state
  preserves `evidence_context`, LEM-01 emits the evidence header, and LEM-02 layers reference the
  provided evidence.
- Confirm the Nginx-served Cockpit asset contains the Evidence Block textarea and outbound
  `evidence_context` payload binding.
