# ADR-0008: Epic 5A Context Budget Balancer

Status: Approved
Date: 2026-07-02
Gate: G1 Architecture
Epic: Epic 5 - Tranche 5A Token-Budget Balancing Engine

## Context

Epic 5 starts the optimization phase for the 20W Lemming substrate. Prior tranches added evidence
blocks, dynamically ranked history, and governance audit trails. Those inputs can grow until they
threaten the local graph's effective context window and produce unstable payload sizes.

The current API returns the LangGraph state dictionary directly, so context-budget telemetry is
added to the existing graph state and response.

## Decision

- Define `MAX_CONTEXT_CHARS = 12000` in `main.py`.
- Before graph invocation, calculate the combined size of `target_prompt`, `evidence_context`, and
  serialized `historical_context`.
- If the combined payload exceeds `MAX_CONTEXT_CHARS`, apply a defensive sliding budget:
  - reserve 40% of total budget for the primary target prompt;
  - cap evidence context to 40% of the remaining budget;
  - cap historical context to the final 20% of the total budget by trimming oldest rows first.
- Append `... [CONTEXT TRUNCATED BY SUBSTRATE BUDGET GUARD]` to truncated text fields.
- Return `context_utilization_ratio` and `total_payload_chars` in the state response.
- Add a Cockpit HUD context-load metric and include budget telemetry in markdown exports.

## Consequences

- Oversized evidence/history payloads remain bounded before node execution.
- Standard smaller requests remain unchanged except for added telemetry.
- Truncation metadata is visible in the response, logs, and export packet.
- The budget guard avoids adding external tokenizer dependencies and stays deterministic.

## Verification

- `python -m compileall main.py`
- `docker compose up -d --build`
- POST `/run` with a massive Evidence Block; confirm HTTP 200, truncation flag, and
  `context_utilization_ratio = 1.0`.
- Confirm Nginx-served Cockpit includes `#hud-context-load` and export budget telemetry.
- Confirm no private host paths or credential literals are introduced.
