# ADR-0021: Tranche 10.2 Merkle Root Ledger Export

## Context & Problem Statement
Tranche 10.1 introduced independently signed DIIaC trajectory leaves. Tranche 10.2 requires those isolated leaves to be accumulated into a verifiable batch root so external audit engines can validate a sequence of multi-agent decisions through one governance export.

## Decision Drivers
* Deterministic binary Merkle reduction over lowercase SHA-256 leaf hashes.
* Proof-path generation for every exported transaction.
* Bounded runtime ledger tracking for newly completed attested trajectories.
* A protected compliance endpoint that exports root, manifest, signatures, and audit paths without exposing private signing material.

## Decision Outcome
Add `hash_node_pair()` and `compute_diiac_merkle_root()` to `crypto_signer.py`.
* Pair hashing validates strict 64-character lowercase SHA-256 hex strings and sorts siblings before hashing.
* Odd layers duplicate the final node in the working reduction layer to preserve binary adjacency.
* `main.py` maintains a bounded in-process ledger registry populated from completed attested payloads.
* `GET /api/governance/export-ledger-pack` returns a ledger pack containing the calculated root, sorted manifest entries, signature proofs, and per-transaction verification paths.

## Status
APPROVED.
