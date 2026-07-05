from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Tuple

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
SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _validate_sha256_hex(hash_value: str, field_name: str = "hash") -> str:
    normalized_hash = str(hash_value or "")
    if not SHA256_HEX_PATTERN.fullmatch(normalized_hash):
        raise ValueError(f"DIIAC_INVALID_SHA256_HEX: {field_name} must be 64 lowercase hex characters.")
    return normalized_hash


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


def hash_node_pair(left_hash: str, right_hash: str) -> str:
    """Reduce two SHA-256 hex nodes into a deterministic parent node."""
    left = _validate_sha256_hex(left_hash, "left_hash")
    right = _validate_sha256_hex(right_hash, "right_hash")
    combined = f"{min(left, right)}{max(left, right)}".encode("utf-8")
    return hashlib.sha256(combined).hexdigest()


def compute_diiac_merkle_root(leaf_hashes: List[str]) -> Tuple[str, dict]:
    """Compile a deterministic DIIaC Merkle root and per-leaf audit paths."""
    if not leaf_hashes:
        raise ValueError("DIIAC_MERKLE_EMPTY_LEAF_SET: At least one leaf hash is required.")

    original_leaves = [
        _validate_sha256_hex(leaf_hash, f"leaf_hashes[{index}]")
        for index, leaf_hash in enumerate(leaf_hashes)
    ]
    proof_paths: Dict[int, List[str]] = {index: [] for index in range(len(original_leaves))}
    active_nodes = [
        {"hash": leaf_hash, "indices": [index]}
        for index, leaf_hash in enumerate(original_leaves)
    ]
    layers: List[Dict[str, Any]] = [{"level": 0, "hashes": list(original_leaves)}]

    while len(active_nodes) > 1:
        working_nodes = list(active_nodes)
        if len(working_nodes) % 2 == 1:
            working_nodes.append({"hash": working_nodes[-1]["hash"], "indices": []})

        next_layer = []
        parent_hashes: List[str] = []
        for index in range(0, len(working_nodes), 2):
            left_node = working_nodes[index]
            right_node = working_nodes[index + 1]
            left_hash = str(left_node["hash"])
            right_hash = str(right_node["hash"])
            parent_hash = hash_node_pair(left_hash, right_hash)

            for leaf_index in left_node["indices"]:
                proof_paths[leaf_index].append(right_hash)
            for leaf_index in right_node["indices"]:
                proof_paths[leaf_index].append(left_hash)

            combined_indices = [*left_node["indices"], *right_node["indices"]]
            next_layer.append({"hash": parent_hash, "indices": combined_indices})
            parent_hashes.append(parent_hash)

        active_nodes = next_layer
        layers.append({"level": len(layers), "hashes": parent_hashes})

    root_hash = str(active_nodes[0]["hash"])
    audit_tree = {
        "leaf_count": len(original_leaves),
        "layers": layers,
        "proof_paths": {str(index): path for index, path in proof_paths.items()},
        "leaves": [
            {
                "computed_index": index,
                "leaf_hash": leaf_hash,
                "verification_path": proof_paths[index],
            }
            for index, leaf_hash in enumerate(original_leaves)
        ],
    }
    return root_hash, audit_tree


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
