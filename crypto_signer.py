from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


DIIAC_LEAF_KEYS = [
    "active_metrics",
    "intent_prompt",
    "terminal_payload",
    "trajectory_path",
]


def canonicalize_diiac_leaf(
    target_prompt: str,
    visited_nodes: List[str],
    final_output: str,
    telemetry_metrics: dict,
) -> bytes:
    """Builds the canonical DIIaC execution leaf and returns its SHA-256 hash bytes."""
    leaf_payload: Dict[str, Any] = {
        "active_metrics": telemetry_metrics or {},
        "intent_prompt": str(target_prompt or ""),
        "terminal_payload": str(final_output or ""),
        "trajectory_path": [str(node) for node in (visited_nodes or [])],
    }
    canonical_payload = json.dumps(
        leaf_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical_payload).digest()


def _load_ed25519_private_key(ed25519_private_key_pem: str) -> Ed25519PrivateKey:
    private_key = serialization.load_pem_private_key(
        ed25519_private_key_pem.encode("utf-8"),
        password=None,
    )
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("DIIAC_SIGNER_INVALID_KEY: Expected an Ed25519 private key.")
    return private_key


def _load_ed25519_public_key(ed25519_public_key_pem: str) -> Ed25519PublicKey:
    public_key = serialization.load_pem_public_key(ed25519_public_key_pem.encode("utf-8"))
    if not isinstance(public_key, Ed25519PublicKey):
        raise TypeError("DIIAC_SIGNER_INVALID_KEY: Expected an Ed25519 public key.")
    return public_key


def generate_development_ed25519_private_key_pem() -> str:
    """Generates a high-entropy in-process development key when no runtime key is provided."""
    private_key = Ed25519PrivateKey.generate()
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def derive_public_key_pem(ed25519_private_key_pem: str) -> str:
    private_key = _load_ed25519_private_key(ed25519_private_key_pem)
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")


def sign_trajectory_leaf(leaf_hash: bytes, ed25519_private_key_pem: str) -> str:
    private_key = _load_ed25519_private_key(ed25519_private_key_pem)
    return private_key.sign(leaf_hash).hex()


def verify_trajectory_leaf_signature(
    leaf_hash: bytes,
    signature_hex: str,
    ed25519_public_key_pem: str,
) -> bool:
    public_key = _load_ed25519_public_key(ed25519_public_key_pem)
    try:
        public_key.verify(bytes.fromhex(signature_hex), leaf_hash)
    except (InvalidSignature, ValueError):
        return False
    return True
