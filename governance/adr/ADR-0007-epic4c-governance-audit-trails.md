# ADR-0007: Epic 4C Governance Audit Trails

Status: Approved
Date: 2026-07-02
Gate: G1 Architecture
Epic: Epic 4 - Tranche 4C Compliance-Tracking Governance Audit Trails

## Context

Epic 4C requires a unified execution audit trail that records every node transition and provides a
tamper-evident signature for boardroom review. The current API returns the LangGraph state
dictionary directly, so response expansion is implemented by adding `governance_audit_trail` to the
existing graph state.

The audit trail must avoid copying raw prompts, evidence blocks, credentials, supervisor payloads,
or generated node responses. It records only metadata needed to validate execution ordering.

## Decision

- Add `governance_audit_trail: Dict[str, Any]` to `LemmingState`.
- Initialize the audit trail with the current `run_id`, `transition_count`, and a `steps` list.
- Each executed node appends one audit step containing:
  - `step_index`
  - `node_id`
  - `timestamp`
  - `payload_length_chars`
  - `node_signature_hash`
- Generate `node_signature_hash` as SHA-256 over the node id, generated response length, and run id.
- Do not store raw node response strings in the audit trail.
- Render the audit trail in a collapsible Cockpit compliance panel and include it in markdown
  export packets.

## Consequences

- Standard full-route runs expose four ordered audit steps.
- Intercepted routes expose only the executed node path, preserving the actual traversal.
- The audit trail is deterministic with respect to node id, response length, and run id, while the
  timestamp captures runtime sequencing.
- Existing clients remain compatible if they ignore the new response field.

## Verification

- `python -m compileall main.py`
- `docker compose up -d --build`
- POST a standard `/run` request and confirm `governance_audit_trail.steps` contains ordered node
  entries with 64-character lowercase hex SHA-256 signatures.
- Confirm the Nginx-served Cockpit includes `#compliance-audit-panel` and export markdown captures
  the governance audit trail.
- Confirm the audit trail contains no raw credentials or private payload arrays.
