from __future__ import annotations

import asyncio
import os
from typing import Any, Dict

import httpx
import pytest


API_BASE_URL = os.environ.get("SUBSTRATE_API_BASE_URL", "http://localhost:8080/api").rstrip("/")
SUBSTRATE_AUTH_TOKEN = os.environ.get("SUBSTRATE_AUTH_TOKEN", "LEMMING_GATEWAY_8080")
ADVERSARIAL_OVERRIDE_KEY = os.environ.get("ADVERSARIAL_OVERRIDE_KEY", "LEMMING_SECRET_422")
REQUEST_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


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


def _run(coro):
    return asyncio.run(coro)


def _assert_numeric(value: Any, field_name: str) -> None:
    assert isinstance(value, (int, float)), f"{field_name} must be numeric"


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
