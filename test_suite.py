from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
import re
import time
import uuid
from typing import Any, Dict

import httpx
import pytest

from crypto_signer import (
    canonicalize_diiac_leaf,
    compute_diiac_merkle_root,
    hash_node_pair,
    verify_trajectory_leaf_signature,
)


API_BASE_URL = os.environ.get("SUBSTRATE_API_BASE_URL", "http://localhost:8080/api").rstrip("/")
SUBSTRATE_AUTH_TOKEN = os.environ.get("SUBSTRATE_AUTH_TOKEN", "LEMMING_GATEWAY_8080")
SUBSTRATE_ENV = os.environ.get("SUBSTRATE_ENV", "development").strip().lower()
ADVERSARIAL_OVERRIDE_KEY = os.environ.get("ADVERSARIAL_OVERRIDE_KEY", "LEMMING_SECRET_422")
REQUEST_TIMEOUT = httpx.Timeout(30.0, connect=5.0)
DIGEST_SNAPSHOT_PATH = Path(__file__).resolve().with_name("core_knowledge_digest.json")
SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ED25519_SIGNATURE_HEX_PATTERN = re.compile(r"^[0-9a-f]{128}$")


def _authorized_headers(token: str = SUBSTRATE_AUTH_TOKEN) -> Dict[str, str]:
    return {"X-Substrate-Auth": token}


def _base_payload(**overrides: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "target_prompt": (
            "Audit multi-sourced enterprise IT services RACI accountability bottlenecks "
            "and delivery transition failure modes."
        ),
        "evidence_context": (
            "Evidence: vendor accountability transitions, RACI ambiguity, and shared "
            "infrastructure ownership gaps create hidden control-plane bottlenecks."
        ),
        "variance_threshold": 75.0,
        "lookahead_horizon": 4,
        "ai_provider": "openai",
        "ai_model": "gpt-4.1",
        "api_key": "",
        "simulate_radar_failure": False,
        "override_passphrase": "",
    }
    payload.update(overrides)
    return payload


async def _post_run(
    payload: Dict[str, Any],
    headers: Dict[str, str] | None = None,
) -> httpx.Response:
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=REQUEST_TIMEOUT) as client:
        try:
            return await client.post("/run", json=payload, headers=headers or _authorized_headers())
        except httpx.HTTPError as exc:
            pytest.fail(f"Unable to reach substrate gateway at {API_BASE_URL}: {exc}")


async def _post_run_with_client(
    client: httpx.AsyncClient,
    payload: Dict[str, Any],
    headers: Dict[str, str] | None = None,
) -> httpx.Response:
    try:
        return await client.post("/run", json=payload, headers=headers or _authorized_headers())
    except httpx.HTTPError as exc:
        pytest.fail(f"Unable to reach substrate gateway at {API_BASE_URL}: {exc}")


async def _post_admin_consolidate(headers: Dict[str, str] | None = None) -> httpx.Response:
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=REQUEST_TIMEOUT) as client:
        try:
            return await client.post(
                "/admin/consolidate-memory",
                headers=headers or _authorized_headers(),
            )
        except httpx.HTTPError as exc:
            pytest.fail(f"Unable to reach substrate gateway at {API_BASE_URL}: {exc}")


async def _get_ledger_pack(headers: Dict[str, str] | None = None) -> httpx.Response:
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=REQUEST_TIMEOUT) as client:
        try:
            return await client.get(
                "/governance/export-ledger-pack",
                headers=headers or _authorized_headers(),
            )
        except httpx.HTTPError as exc:
            pytest.fail(f"Unable to reach substrate gateway at {API_BASE_URL}: {exc}")


def _run(coro):
    return asyncio.run(coro)


def _assert_numeric(value: Any, field_name: str) -> None:
    assert isinstance(value, (int, float)), f"{field_name} must be numeric"


def _deterministic_leaf_batch(batch_size: int) -> list[str]:
    return [
        hashlib.sha256(f"diiac-test-leaf:{batch_size}:{index}".encode("utf-8")).hexdigest()
        for index in range(batch_size)
    ]


def _resolve_merkle_path(leaf_hash: str, verification_path: list[str]) -> str:
    rolling_hash = leaf_hash
    for adjacent_hash in verification_path:
        rolling_hash = hash_node_pair(rolling_hash, adjacent_hash)
    return rolling_hash


def test_diiac_merkle_root_determinism():
    for batch_size in (1, 4, 7, 32):
        leaf_hashes = _deterministic_leaf_batch(batch_size)
        original_hashes = list(leaf_hashes)
        root_one, audit_one = compute_diiac_merkle_root(leaf_hashes)
        root_two, audit_two = compute_diiac_merkle_root(list(leaf_hashes))

        assert leaf_hashes == original_hashes
        assert SHA256_HEX_PATTERN.fullmatch(root_one)
        assert root_one == root_two
        assert audit_one == audit_two
        assert audit_one["leaf_count"] == batch_size
        assert len(audit_one["leaves"]) == batch_size

        for index, leaf_hash in enumerate(leaf_hashes):
            verification_path = audit_one["proof_paths"][str(index)]
            assert _resolve_merkle_path(leaf_hash, verification_path) == root_one

    with pytest.raises(ValueError):
        compute_diiac_merkle_root([])
    with pytest.raises(ValueError):
        hash_node_pair("A" * 64, "0" * 64)


def test_standard_execution_flow():
    response = _run(_post_run(_base_payload()))

    assert response.status_code == 200
    result = response.json()
    assert result["success_flag"] is True
    assert result["visited_nodes"] == ["LEM-04", "LEM-01", "LEM-02", "LEM-03"]
    _assert_numeric(result.get("E_c"), "E_c")
    _assert_numeric(result.get("delta_a"), "delta_a")

    active_bias_profile = result.get("active_bias_profile")
    assert isinstance(active_bias_profile, dict)
    for field_name in ("supervisor_bias", "creative_bias", "validator_bias", "radar_bias"):
        _assert_numeric(active_bias_profile.get(field_name), f"active_bias_profile.{field_name}")


def test_radar_short_circuit_flow():
    response = _run(
        _post_run(
            _base_payload(
                target_prompt="Force an authenticated LEM-04 radar degradation test path.",
                evidence_context="Evidence: controlled adversarial probe for graph routing validation.",
                simulate_radar_failure=True,
                override_passphrase=ADVERSARIAL_OVERRIDE_KEY,
            )
        )
    )

    assert response.status_code == 200
    result = response.json()
    assert result["visited_nodes"] == ["LEM-04", "LEM-03"]
    assert result["intercept_triggered"] is True
    assert result["S_d"] == pytest.approx(0.5)
    assert result["pruning_percentage"] == pytest.approx(0.5)


def test_security_perimeter_failures():
    invalid_token_response = _run(
        _post_run(
            _base_payload(target_prompt="Corrupt substrate token should be rejected."),
            headers=_authorized_headers("CORRUPT_SUBSTRATE_TOKEN"),
        )
    )
    if SUBSTRATE_ENV == "development":
        assert invalid_token_response.status_code == 200
        assert invalid_token_response.json()["success_flag"] is True
    else:
        assert invalid_token_response.status_code == 401

    bad_passphrase_response = _run(
        _post_run(
            _base_payload(
                target_prompt="Invalid adversarial passphrase should be forbidden.",
                simulate_radar_failure=True,
                override_passphrase="CORRUPT_OVERRIDE_TOKEN",
            )
        )
    )
    assert bad_passphrase_response.status_code == 403


def test_dual_horizon_cache_interception():
    unique_target = f"Dual-horizon cache interception probe {uuid.uuid4()}"
    payload = _base_payload(
        target_prompt=unique_target,
        evidence_context=(
            "Evidence: repeatable dual-horizon cache validation context with stable "
            "RACI vocabulary and vendor accountability markers."
        ),
    )

    async def _round_trip_cache_probe():
        async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=REQUEST_TIMEOUT) as client:
            miss = await _post_run_with_client(client, payload)
            hit_start = time.perf_counter()
            hit = await _post_run_with_client(client, payload)
            return miss, hit, time.perf_counter() - hit_start

    miss_response, hit_response, hit_elapsed = _run(_round_trip_cache_probe())
    assert miss_response.status_code == 200
    miss_result = miss_response.json()
    assert miss_result["success_flag"] is True
    assert miss_result.get("telemetry", {}).get("cache_hit") is False

    assert hit_response.status_code == 200
    assert hit_elapsed < 1.0
    hit_result = hit_response.json()
    assert hit_result["success_flag"] is True
    assert hit_result.get("telemetry", {}).get("cache_hit") is True
    assert float(hit_result.get("velocity_ms", 1000.0)) < 1000.0
    assert hit_result["visited_nodes"] == ["LEM-04", "LEM-01", "LEM-02", "LEM-03"]
    assert hit_result["run_id"].startswith("cache-")


def test_memory_consolidation_lifecycle():
    existing_digest = (
        DIGEST_SNAPSHOT_PATH.read_bytes()
        if DIGEST_SNAPSHOT_PATH.exists()
        else None
    )
    try:
        unauthorized_response = _run(
            _post_admin_consolidate(headers=_authorized_headers("CORRUPT_SUBSTRATE_TOKEN"))
        )
        if SUBSTRATE_ENV == "development":
            assert unauthorized_response.status_code == 200
            assert unauthorized_response.json()["status"] == "CONSOLIDATED"
        else:
            assert unauthorized_response.status_code == 401

        response = _run(_post_admin_consolidate())
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "CONSOLIDATED"
        assert isinstance(result["compiled_records_count"], int)
        assert result["target_digest_file"] == "core_knowledge_digest.json"
        assert isinstance(result.get("timestamp"), str)
    finally:
        if existing_digest is None:
            DIGEST_SNAPSHOT_PATH.unlink(missing_ok=True)
        else:
            DIGEST_SNAPSHOT_PATH.write_bytes(existing_digest)


def test_substrate_digest_runtime_injection():
    existing_digest = (
        DIGEST_SNAPSHOT_PATH.read_bytes()
        if DIGEST_SNAPSHOT_PATH.exists()
        else None
    )
    try:
        DIGEST_SNAPSHOT_PATH.write_text('"MOCK_TRAJECTORY_ALPHA"', encoding="utf-8")
        unique_target = f"Core knowledge digest runtime injection probe {uuid.uuid4()}"
        response = _run(
            _post_run(
                _base_payload(
                    target_prompt=unique_target,
                    evidence_context="Evidence: deterministic digest boot validation.",
                )
            )
        )

        assert response.status_code == 200
        result = response.json()
        assert result["success_flag"] is True
        assert result["digest_loaded"] is True
        assert any("digest_loaded=True" in log for log in result.get("logs", []))
        supervisor_payload = result.get("supervisor_payload", {})
        assert supervisor_payload.get("Digest_Loaded") is True
        assert "MOCK_TRAJECTORY_ALPHA" in supervisor_payload.get("Core_Knowledge_Digest", "")
        assert any(
            "MOCK_TRAJECTORY_ALPHA" in constraint
            for constraint in supervisor_payload.get("Constraints", [])
        )
    finally:
        if existing_digest is None:
            DIGEST_SNAPSHOT_PATH.unlink(missing_ok=True)
        else:
            DIGEST_SNAPSHOT_PATH.write_bytes(existing_digest)


def test_diiac_cryptographic_attestation_integrity():
    unique_target = f"DIIaC cryptographic attestation probe {uuid.uuid4()}"
    response = _run(
        _post_run(
            _base_payload(
                target_prompt=unique_target,
                evidence_context="Evidence: verify deterministic Merkle leaf and Ed25519 signature.",
            )
        )
    )

    assert response.status_code == 200
    result = response.json()
    leaf_hash_hex = result.get("diiac_merkle_leaf_hash")
    signature_hex = result.get("diiac_attestation_signature")
    public_key_pem = result.get("diiac_attestation_public_key")

    assert isinstance(leaf_hash_hex, str)
    assert SHA256_HEX_PATTERN.fullmatch(leaf_hash_hex)
    assert isinstance(signature_hex, str)
    assert ED25519_SIGNATURE_HEX_PATTERN.fullmatch(signature_hex)
    assert isinstance(public_key_pem, str)
    assert "BEGIN PUBLIC KEY" in public_key_pem

    recomputed_leaf_hash = canonicalize_diiac_leaf(
        target_prompt=result["target_prompt"],
        visited_nodes=result["visited_nodes"],
        final_output=result["current_node_payload"],
        telemetry_metrics=result["telemetry"],
    )
    second_recomputed_leaf_hash = canonicalize_diiac_leaf(
        target_prompt=result["target_prompt"],
        visited_nodes=result["visited_nodes"],
        final_output=result["current_node_payload"],
        telemetry_metrics=result["telemetry"],
    )
    assert recomputed_leaf_hash == second_recomputed_leaf_hash
    assert recomputed_leaf_hash.hex() == leaf_hash_hex
    assert verify_trajectory_leaf_signature(
        recomputed_leaf_hash,
        signature_hex,
        public_key_pem,
    )


def test_governance_ledger_pack_export_lifecycle():
    collected_hashes: list[str] = []
    for index in range(3):
        response = _run(
            _post_run(
                _base_payload(
                    target_prompt=f"Governance ledger pack probe {uuid.uuid4()}",
                    evidence_context=f"Evidence: ledger export transaction index {index}.",
                )
            )
        )
        assert response.status_code == 200
        result = response.json()
        assert SHA256_HEX_PATTERN.fullmatch(result["diiac_merkle_leaf_hash"])
        collected_hashes.append(result["diiac_merkle_leaf_hash"])

    response = _run(_get_ledger_pack())
    assert response.status_code == 200
    ledger_pack = response.json()
    assert ledger_pack["ledger_pack_id"].startswith("LG-EXP-")
    assert isinstance(ledger_pack.get("timestamp_marker"), str)
    assert SHA256_HEX_PATTERN.fullmatch(ledger_pack["diiac_merkle_root"])
    assert ledger_pack["transaction_count"] == len(ledger_pack["manifest_registry"])
    assert ledger_pack["transaction_count"] >= len(collected_hashes)

    manifest = ledger_pack["manifest_registry"]
    manifest_leaf_hashes = [entry["leaf_hash"] for entry in manifest]
    assert manifest_leaf_hashes == sorted(manifest_leaf_hashes)
    computed_root, audit_tree = compute_diiac_merkle_root(manifest_leaf_hashes)
    assert computed_root == ledger_pack["diiac_merkle_root"]

    for index, entry in enumerate(manifest):
        assert isinstance(entry["run_id"], str)
        assert SHA256_HEX_PATTERN.fullmatch(entry["leaf_hash"])
        assert ED25519_SIGNATURE_HEX_PATTERN.fullmatch(entry["signature_proof"])
        audit_trail = entry["audit_trail"]
        assert audit_trail["computed_index"] == index
        assert audit_trail["verification_path"] == audit_tree["proof_paths"][str(index)]
        assert _resolve_merkle_path(
            entry["leaf_hash"],
            audit_trail["verification_path"],
        ) == ledger_pack["diiac_merkle_root"]
