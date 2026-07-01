# ADR-0004: Epic 3C Adversarial Override Authentication Gate

Status: Approved
Date: 2026-07-01
Gate: G1 Architecture
Epic: Epic 3 - Tranche 3C Override Authentication Gate

## Context

Epic 3B promoted `simulate_radar_failure` into a backend runtime contract. That override can
short-circuit normal graph traversal and force an adversarial route through LEM-04 and LEM-03.
Because the route intentionally changes execution shape and telemetry, Epic 3C must ensure it is
only available when the caller presents an environment-validated authorization token.

Nominal ingestion must remain frictionless. The hardening gate applies only when a request asks the
backend to simulate radar failure.

## Decision

- Add `ADVERSARIAL_OVERRIDE_KEY` to the backend container environment.
- Add `override_passphrase: str = ""` to the `/run` request schema.
- When `simulate_radar_failure` is true, compare `override_passphrase` against
  `os.getenv("ADVERSARIAL_OVERRIDE_KEY")`.
- Reject unauthorized override attempts with:
  `HTTPException(status_code=403, detail="ADVERSARIAL_DENIED: Invalid override passphrase verification token.")`.
- Perform the rejection before graph invocation, telemetry finalization, or SQLite persistence.
- Keep nominal `simulate_radar_failure: false` ingestion behavior unchanged.
- Add a masked Cockpit passphrase input that appears only when the adversarial override toggle is
  enabled and is sent as `override_passphrase`.

## Consequences

- Operators can still execute Epic 3B adversarial diagnostics, but only with the configured token.
- Failed override attempts leave no graph trace or run history row.
- The frontend carries the passphrase only in the transient request body and does not render it into
  telemetry export or state JSON.
- The compose file contains the local development token required by the current tranche directive.

## Verification

- `python -m compileall main.py`
- `docker compose up -d --build`
- POST `/run` with `simulate_radar_failure: true` and an empty or incorrect
  `override_passphrase`; confirm HTTP 403 and no new SQLite run row.
- POST `/run` with `simulate_radar_failure: true` and `override_passphrase:
  LEMMING_SECRET_422`; confirm the authorized LEM-04 to LEM-03 traversal, `S_d = 0.5`,
  `pruning_percentage = 0.5`, `intercept_triggered = true`, and persistence.
- Run a nominal request with `simulate_radar_failure: false` to confirm no passphrase is required.
