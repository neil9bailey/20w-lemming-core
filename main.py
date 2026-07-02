import asyncio
import hashlib
import json
import os
import time
import uuid
from typing import Any, Dict, List

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from agent_nodes import (
    lh_validator_node,
    radar_node,
    rh_core_node,
    supervisor_node,
    sync_external_source_payloads,
)
from memory_store import (
    DEFAULT_ACTIVE_BIAS_PROFILE,
    commit_horizon_cache,
    fetch_horizon_cache,
    initialize_memory,
    load_active_bias_profile,
    load_bias_profile,
    load_successful_runs,
    record_run,
)
from state_schema import (
    CONCURRENCY_LOCK_LOG,
    CONTEXT_TRUNCATION_FLAG,
    DEFAULT_AGENT_DIRECTIVES,
    MAX_CONTEXT_CHARS,
    SubstrateState,
)


app = FastAPI(title="20W Digital Twin Agent Substrate")
substrate_execution_lock = asyncio.Lock()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

initialize_memory()


class IngestionRequest(BaseModel):
    """Request schema for the API gateway."""

    target_prompt: str = Field(min_length=1)
    evidence_context: str = ""
    variance_threshold: float = Field(ge=0.0)
    lookahead_horizon: int = Field(ge=1)
    api_key: str = ""
    ai_provider: str = "openai"
    ai_model: str = "gpt-4.1"
    simulate_radar_failure: bool = False
    override_passphrase: str = ""
    external_source_root: str = ""


def configured_bias_profile_name() -> str:
    configured_name = os.environ.get("SUBSTRATE_BIAS_PROFILE", DEFAULT_ACTIVE_BIAS_PROFILE)
    return configured_name.strip() or DEFAULT_ACTIVE_BIAS_PROFILE


def calculate_input_fingerprint(target_prompt: str, evidence_context: str) -> str:
    """Computes a deterministic SHA-256 hash tracking key for context pairs."""
    combined_raw_text = f"p:{target_prompt.strip()}|c:{evidence_context.strip()}"
    return hashlib.sha256(combined_raw_text.encode("utf-8")).hexdigest()


async def resolve_active_evidence_context(request: IngestionRequest) -> str:
    evidence_parts = [request.evidence_context.rstrip()]
    external_source_root = request.external_source_root.strip()
    if external_source_root:
        external_payloads = await sync_external_source_payloads(external_source_root)
        if external_payloads:
            evidence_parts.extend(["[EXTERNAL SOURCE PAYLOADS]", *external_payloads])
    return "\n".join(part for part in evidence_parts if part)


def _cache_source_text(request: IngestionRequest, active_evidence_context: str) -> str:
    runtime_config = (
        f"[RUN CONFIG] variance={request.variance_threshold}; "
        f"lookahead={request.lookahead_horizon}; "
        f"provider={request.ai_provider.strip() or 'openai'}; "
        f"model={request.ai_model.strip() or 'gpt-4.1'}; "
        f"simulate_radar_failure={request.simulate_radar_failure}"
    )
    return "\n".join(part for part in [active_evidence_context, runtime_config] if part)


def _cache_interception_enabled(request: IngestionRequest) -> bool:
    return not request.simulate_radar_failure


def _telemetry_cache_block(
    cache_hit: bool,
    input_fingerprint: str,
    E_c: float = 0.0,
    delta_a: float = 0.0,
    S_d: float = 0.0,
) -> Dict[str, Any]:
    return {
        "E_c": E_c,
        "delta_a": delta_a,
        "S_d": S_d,
        "cache_hit": cache_hit,
        "input_fingerprint": input_fingerprint,
    }


def _final_output_string(graph_output: Dict[str, Any]) -> str:
    execution_matrix = str(graph_output.get("execution_matrix", "")).strip()
    if execution_matrix:
        return execution_matrix

    dialogue = graph_output.get("agent_dialogue", [])
    if isinstance(dialogue, list) and dialogue:
        latest_entry = dialogue[-1]
        if isinstance(latest_entry, dict):
            return str(latest_entry.get("message", "")).strip()
        return str(latest_entry).strip()

    return json.dumps(graph_output, ensure_ascii=False, default=str)


def _cache_hit_payload(
    request: IngestionRequest,
    cached_payload: str,
    active_bias_profile: Dict[str, Any],
    input_fingerprint: str,
    lock_contention_detected: bool,
    velocity_ms: float,
) -> Dict[str, Any]:
    run_id = f"cache-{uuid.uuid4()}"
    telemetry = _telemetry_cache_block(True, input_fingerprint)
    return {
        "success_flag": True,
        "run_id": run_id,
        "target_prompt": request.target_prompt.strip(),
        "evidence_context": request.evidence_context.rstrip(),
        "current_node": "CACHE",
        "visited_nodes": ["LEM-04", "LEM-01", "LEM-02", "LEM-03"],
        "current_node_payload": cached_payload,
        "execution_matrix": cached_payload,
        "agent_dialogue": [
            {
                "agent": "CACHE",
                "message": cached_payload,
            }
        ],
        "logs": ["[CACHE] Dual-horizon cache hit. Graph execution bypassed."],
        "active_bias_profile": active_bias_profile,
        "telemetry": telemetry,
        "cache_hit": True,
        "input_fingerprint": input_fingerprint,
        "E_c": 0.0,
        "delta_a": 0.0,
        "S_d": 0.0,
        "pruning_percentage": 0.0,
        "autonomous_decisions": 0,
        "total_decisions": 1,
        "velocity_ms": round(velocity_ms, 3),
        "lock_contention_detected": lock_contention_detected,
        "context_utilization_ratio": 0.0,
        "total_payload_chars": len(request.target_prompt) + len(request.evidence_context),
        "max_context_chars": MAX_CONTEXT_CHARS,
        "context_truncated": False,
        "intercept_triggered": False,
        "governance_audit_trail": {
            "run_id": run_id,
            "transition_count": 0,
            "steps": [],
            "cache_hit": True,
        },
    }


def _truncate_text(value: str, max_chars: int) -> tuple[str, bool]:
    if len(value) <= max_chars:
        return value, False
    if max_chars <= len(CONTEXT_TRUNCATION_FLAG):
        return CONTEXT_TRUNCATION_FLAG[:max_chars], True
    return f"{value[:max_chars - len(CONTEXT_TRUNCATION_FLAG)].rstrip()}{CONTEXT_TRUNCATION_FLAG}", True


def _history_payload_chars(historical_context: List[Dict[str, Any]]) -> int:
    return len(json.dumps(historical_context, ensure_ascii=False))


def _balance_context_budget(
    target_prompt: str,
    evidence_context: str,
    historical_context: List[Dict[str, Any]],
) -> tuple[str, str, List[Dict[str, Any]], int, float, bool]:
    total_chars = len(target_prompt) + len(evidence_context) + _history_payload_chars(historical_context)
    if total_chars <= MAX_CONTEXT_CHARS:
        return (
            target_prompt,
            evidence_context,
            historical_context,
            total_chars,
            round(total_chars / MAX_CONTEXT_CHARS, 4),
            False,
        )

    target_budget = int(MAX_CONTEXT_CHARS * 0.4)
    remaining_budget = MAX_CONTEXT_CHARS - target_budget
    evidence_budget = int(remaining_budget * 0.4)
    history_budget = MAX_CONTEXT_CHARS - target_budget - evidence_budget

    balanced_target, target_truncated = _truncate_text(target_prompt, target_budget)
    balanced_evidence, evidence_truncated = _truncate_text(evidence_context, evidence_budget)

    balanced_history: List[Dict[str, Any]] = []
    history_truncated = bool(historical_context)
    for row in historical_context:
        candidate_rows = [*balanced_history, row]
        if _history_payload_chars(candidate_rows) <= history_budget:
            balanced_history = candidate_rows
        else:
            history_truncated = True
            break

    if history_truncated and balanced_history:
        oldest_retained = balanced_history[-1]
        oldest_retained["core_target"] = (
            f"{str(oldest_retained.get('core_target', '')).rstrip()}{CONTEXT_TRUNCATION_FLAG}"
        )

    return balanced_target, balanced_evidence, balanced_history, MAX_CONTEXT_CHARS, 1.0, (
        target_truncated or evidence_truncated or history_truncated
    )


def build_initial_state(request: IngestionRequest) -> SubstrateState:
    run_id = str(uuid.uuid4())
    bias_profile = load_bias_profile()
    active_bias_profile = load_active_bias_profile(configured_bias_profile_name())
    historical_context = load_successful_runs(target_prompt=request.target_prompt, limit=3)
    (
        target_prompt,
        evidence_context,
        historical_context,
        total_payload_chars,
        context_utilization_ratio,
        context_truncated,
    ) = _balance_context_budget(
        target_prompt=request.target_prompt,
        evidence_context=request.evidence_context.rstrip(),
        historical_context=historical_context,
    )
    max_history_relevance_score = max(
        (float(row.get("relevance_score", 0.0)) for row in historical_context),
        default=0.0,
    )
    ai_provider = request.ai_provider.strip() or "openai"
    ai_model = request.ai_model.strip() or "gpt-4.1"
    logs = ["Initialize trace through 20W multi-agent engine..."]
    logs.append(
        f"[BIAS] Active bias profile loaded: {active_bias_profile.get('pattern_type', configured_bias_profile_name())}."
    )
    if context_truncated:
        logs.append(
            f"[BUDGET] Context budget guard activated. Payload capped at {MAX_CONTEXT_CHARS} characters."
        )

    return {
        "run_id": run_id,
        "target_prompt": target_prompt,
        "evidence_context": evidence_context,
        "external_source_root": request.external_source_root.strip(),
        "variance_threshold": request.variance_threshold,
        "lookahead_horizon": request.lookahead_horizon,
        "current_node": "ENTRY",
        "logs": logs,
        "agent_dialogue": [],
        "drift": 0.0,
        "recalibrated": False,
        "agent_directives": dict(DEFAULT_AGENT_DIRECTIVES),
        "bias_profile": bias_profile,
        "active_bias_profile": active_bias_profile,
        "node_bias_profiles": {
            "LEM-01": bias_profile,
            "LEM-02": bias_profile,
        },
        "ai_api_config": {
            "provider": ai_provider,
            "model": ai_model,
            "api_key_configured": bool(request.api_key.strip()),
        },
        "historical_context": historical_context,
        "max_history_relevance_score": max_history_relevance_score,
        "governance_audit_trail": {
            "run_id": run_id,
            "transition_count": 0,
            "steps": [],
        },
        "context_utilization_ratio": context_utilization_ratio,
        "total_payload_chars": total_payload_chars,
        "max_context_chars": MAX_CONTEXT_CHARS,
        "context_truncated": context_truncated,
        "lock_contention_detected": False,
        "simulate_radar_failure": request.simulate_radar_failure,
        "intercept_triggered": False,
        "supervisor_payload": {},
        "strategic_layers": [],
        "execution_matrix": "",
        "visited_nodes": [],
        "pruning_percentage": 0.0,
        "autonomous_decisions": 0,
        "total_decisions": 1,
        "E_c": 0.0,
        "delta_a": 0.0,
        "S_d": 0.0,
        "velocity_ms": 0.0,
        "success_flag": False,
    }


def route_after_radar(state: SubstrateState) -> str:
    if state["simulate_radar_failure"] or state["intercept_triggered"] or state["drift"] > 90.0:
        return "lh_validator"
    return "supervisor"


def build_workflow():
    workflow = StateGraph(SubstrateState)
    workflow.add_node("radar", radar_node)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("rh_core", rh_core_node)
    workflow.add_node("lh_validator", lh_validator_node)

    workflow.set_entry_point("radar")
    workflow.add_conditional_edges(
        "radar",
        route_after_radar,
        {
            "lh_validator": "lh_validator",
            "supervisor": "supervisor",
        },
    )
    workflow.add_edge("supervisor", "rh_core")
    workflow.add_edge("rh_core", "lh_validator")
    workflow.add_edge("lh_validator", END)
    return workflow


app_workflow = build_workflow().compile()


def _extract_stream_state(stream_output: Dict[str, Any]) -> Dict[str, Any] | None:
    if not isinstance(stream_output, dict):
        return None
    for value in stream_output.values():
        if isinstance(value, dict) and "run_id" in value:
            return value
    if "run_id" in stream_output:
        return stream_output
    return None


def _sse_data(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def validate_override_authorization(request: IngestionRequest) -> None:
    if not request.simulate_radar_failure:
        return

    override_key = os.environ.get("ADVERSARIAL_OVERRIDE_KEY")
    if not override_key:
        raise HTTPException(
            status_code=503,
            detail="ADVERSARIAL_DENIED: Override token is not configured in the runtime environment.",
        )
    if request.override_passphrase != override_key:
        raise HTTPException(
            status_code=403,
            detail="ADVERSARIAL_DENIED: Invalid override passphrase verification token.",
        )


def validate_substrate_authorization(x_substrate_auth: str) -> None:
    expected_token = os.environ.get("SUBSTRATE_AUTH_TOKEN", "").strip()
    if not expected_token:
        return
    if x_substrate_auth != expected_token:
        raise HTTPException(
            status_code=401,
            detail="SUBSTRATE_AUTH_DENIED: Invalid or missing X-Substrate-Auth token.",
        )


@app.post("/run")
async def execute_agentic_flow(
    request: IngestionRequest,
    x_substrate_auth: str = Header(default="", alias="X-Substrate-Auth"),
):
    """Runs a complete trace through the compiled LangGraph substrate."""
    validate_substrate_authorization(x_substrate_auth)
    validate_override_authorization(request)

    lock_contention_detected = substrate_execution_lock.locked()
    if lock_contention_detected:
        print(CONCURRENCY_LOCK_LOG, flush=True)

    async with substrate_execution_lock:
        try:
            start_time = time.perf_counter()
            active_evidence_context = await resolve_active_evidence_context(request)
            cache_source_text = _cache_source_text(request, active_evidence_context)
            request_fingerprint = calculate_input_fingerprint(request.target_prompt, cache_source_text)
            active_bias_profile = load_active_bias_profile(configured_bias_profile_name())
            cache_enabled = _cache_interception_enabled(request)
            cached_payload = (
                await fetch_horizon_cache(request.target_prompt, cache_source_text)
                if cache_enabled
                else None
            )
            if cached_payload:
                velocity_ms = (time.perf_counter() - start_time) * 1000.0
                return _cache_hit_payload(
                    request=request,
                    cached_payload=cached_payload,
                    active_bias_profile=active_bias_profile,
                    input_fingerprint=request_fingerprint,
                    lock_contention_detected=lock_contention_detected,
                    velocity_ms=velocity_ms,
                )

            initial_state = build_initial_state(request)
            initial_state["lock_contention_detected"] = lock_contention_detected

            graph_output = await app_workflow.ainvoke(initial_state)
            velocity_ms = (time.perf_counter() - start_time) * 1000.0
            graph_output["velocity_ms"] = round(velocity_ms, 3)
            graph_output["lock_contention_detected"] = lock_contention_detected
            graph_output["cache_hit"] = False
            graph_output["input_fingerprint"] = request_fingerprint
            graph_output["telemetry"] = _telemetry_cache_block(
                False,
                request_fingerprint,
                E_c=float(graph_output.get("E_c", 0.0)),
                delta_a=float(graph_output.get("delta_a", 0.0)),
                S_d=float(graph_output.get("S_d", 0.0)),
            )

            try:
                record_run(graph_output)
            except Exception as persistence_error:
                graph_output["logs"].append(f"[MEMORY] Run persistence failed: {persistence_error}")
            if cache_enabled:
                cache_payload = _final_output_string(graph_output)
                cache_key = await commit_horizon_cache(
                    request.target_prompt,
                    cache_source_text,
                    cache_payload,
                )
                if cache_key:
                    graph_output["logs"].append("[CACHE] Dual-horizon payload committed for future intercepts.")

            return graph_output

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Graph Execution Error: {str(e)}")


@app.post("/api/stream-run")
@app.post("/stream-run")
async def execute_streaming_agentic_flow(
    request: IngestionRequest,
    x_substrate_auth: str = Header(default="", alias="X-Substrate-Auth"),
):
    """Streams LangGraph state mutations as server-sent event chunks."""
    validate_substrate_authorization(x_substrate_auth)
    validate_override_authorization(request)

    lock_contention_detected = substrate_execution_lock.locked()
    if lock_contention_detected:
        print(CONCURRENCY_LOCK_LOG, flush=True)

    stream_start_time = time.perf_counter()
    active_evidence_context = await resolve_active_evidence_context(request)
    cache_source_text = _cache_source_text(request, active_evidence_context)
    request_fingerprint = calculate_input_fingerprint(request.target_prompt, cache_source_text)
    active_bias_profile = load_active_bias_profile(configured_bias_profile_name())
    cache_enabled = _cache_interception_enabled(request)
    cached_payload = (
        await fetch_horizon_cache(request.target_prompt, cache_source_text)
        if cache_enabled
        else None
    )
    if cached_payload:
        cache_state = _cache_hit_payload(
            request=request,
            cached_payload=cached_payload,
            active_bias_profile=active_bias_profile,
            input_fingerprint=request_fingerprint,
            lock_contention_detected=lock_contention_detected,
            velocity_ms=(time.perf_counter() - stream_start_time) * 1000.0,
        )

        async def immediate_cache_stream():
            yield _sse_data(
                {
                    "event": "stream_started",
                    "run_id": cache_state["run_id"],
                    "cache_hit": True,
                    "lock_contention_detected": lock_contention_detected,
                }
            )
            yield _sse_data(
                {
                    "event": "cache_intercept_flush",
                    "node": "CACHE",
                    "run_id": cache_state["run_id"],
                    "current_node": "CACHE",
                    "current_node_payload": cached_payload,
                    "active_bias_profile": active_bias_profile,
                    "visited_nodes": cache_state["visited_nodes"],
                    "telemetry": cache_state["telemetry"],
                    "cache_hit": True,
                }
            )
            yield _sse_data({"event": "stream_complete", "state": cache_state, "cache_hit": True})

        return StreamingResponse(immediate_cache_stream(), media_type="text/event-stream")

    async def async_graph_stream_generator():
        async with substrate_execution_lock:
            graph_output: Dict[str, Any] | None = None
            start_time = time.perf_counter()
            try:
                initial_state = build_initial_state(request)
                initial_state["lock_contention_detected"] = lock_contention_detected
                yield _sse_data(
                    {
                        "event": "stream_started",
                        "run_id": initial_state["run_id"],
                        "lock_contention_detected": lock_contention_detected,
                        "cache_hit": False,
                    }
                )

                async for output in app_workflow.astream(initial_state):
                    extracted_state = _extract_stream_state(output)
                    if extracted_state is not None:
                        graph_output = extracted_state
                    yield _sse_data(output)

                if graph_output is not None:
                    velocity_ms = (time.perf_counter() - start_time) * 1000.0
                    graph_output["velocity_ms"] = round(velocity_ms, 3)
                    graph_output["lock_contention_detected"] = lock_contention_detected
                    graph_output["cache_hit"] = False
                    graph_output["input_fingerprint"] = request_fingerprint
                    graph_output["telemetry"] = _telemetry_cache_block(
                        False,
                        request_fingerprint,
                        E_c=float(graph_output.get("E_c", 0.0)),
                        delta_a=float(graph_output.get("delta_a", 0.0)),
                        S_d=float(graph_output.get("S_d", 0.0)),
                    )
                    try:
                        record_run(graph_output)
                    except Exception as persistence_error:
                        graph_output["logs"].append(f"[MEMORY] Run persistence failed: {persistence_error}")
                    if cache_enabled:
                        cache_key = await commit_horizon_cache(
                            request.target_prompt,
                            cache_source_text,
                            _final_output_string(graph_output),
                        )
                        if cache_key:
                            graph_output["logs"].append("[CACHE] Dual-horizon payload committed for future intercepts.")
                    yield _sse_data({"event": "stream_complete", "state": graph_output})
            except Exception as e:
                yield _sse_data({"event": "stream_error", "detail": f"Graph Execution Error: {str(e)}"})

    return StreamingResponse(async_graph_stream_generator(), media_type="text/event-stream")


@app.get("/health")
async def health_check():
    """Returns baseline system telemetries."""
    return {
        "status": "ONLINE",
        "substrate": "neil9bailey/20w-lemming-core",
        "compliance_ceiling_watts": 20.0,
        "memory": "20w_memory.db",
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
