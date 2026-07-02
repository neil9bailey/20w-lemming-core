# ADR-0013: Tranche 1.6A Automated Integration Harness and Perimeter Auth

Status: Approved
Date: 2026-07-02
Gate: G1 Architecture
Epic: Tranche 1.6A - Automated Integration Harness

## Context

Tranche 1.3B added client-side `X-Substrate-Auth` header transport and Tranche 1.3C isolated the
backend behind the Nginx `/api` route. The live gateway still accepts corrupt or empty
`X-Substrate-Auth` values, which prevents an integration harness from truthfully validating the
required `401 Unauthorized` perimeter failure case.

## Decision

- Add an environment-backed `SUBSTRATE_AUTH_TOKEN` gateway token.
- Validate `X-Substrate-Auth` inside the FastAPI `/run` route before graph execution or database
  persistence.
- Return `401 Unauthorized` for missing or mismatched substrate auth headers.
- Keep the adversarial override passphrase guard as a distinct `403 Forbidden` check.
- Add `test_suite.py` with exactly three pytest tests using `httpx.AsyncClient` against
  `http://localhost:8080/api`.

## Consequences

- Standard and adversarial test traffic must include the configured header.
- Cockpit browser sessions must set `localStorage.SUBSTRATE_AUTH_TOKEN` to the configured runtime
  value before invoking protected runs.
- The automated harness can now assert standard topology, radar short-circuit topology, and 401/403
  perimeter failures against the live Nginx path.

## Verification

- `python -m compileall main.py test_suite.py`
- `docker compose up -d --build --force-recreate`
- `pytest test_suite.py -v`
