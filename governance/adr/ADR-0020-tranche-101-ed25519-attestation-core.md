# ADR-0020: Tranche 10.1 Ed25519 Trajectory Attestation Core

## Context & Problem Statement
Epic 10 introduces independently verifiable governance exports for substrate execution traces. The runtime must produce a deterministic Merkle leaf hash and Ed25519 signature for completed atomic trajectories so downstream DIIaC ledger engines can validate strategic state outputs without trusting the cockpit UI.

## Decision Drivers
* Deterministic canonical hashing across prompt, trajectory, terminal payload, and telemetry inputs.
* Ed25519 signatures using a runtime private key supplied through environment configuration.
* Visible development fallback behavior when no production signing key has been provisioned.
* API-level proof fields that can be validated by automated integration tests.

## Decision Outcome
Deploy a dedicated `crypto_signer.py` module for canonical leaf hashing, Ed25519 signing, public key derivation, and signature verification.
* The atomic `/run` response path attaches `diiac_merkle_leaf_hash` and `diiac_attestation_signature` after graph execution and persistence handling.
* The signer uses `DIIAC_SUBSTRATE_KEY_PEM` when present; otherwise, it generates an ephemeral in-process development Ed25519 key and marks the response key source accordingly.
* Tests recompute the canonical leaf hash from response fields and verify the signature using the returned public key.

## Status
APPROVED.
