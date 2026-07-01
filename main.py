import json
import hashlib
import math
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, TypedDict

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from memory_store import initialize_memory, load_bias_profile, load_successful_runs, record_run


LEMMING_DIRECTIVES: Dict[str, str] = {
    "LEM-01": """You are the Sovereign Supervisor. You are the ONLY node permitted to communicate directly with the human.

Your job is to:
1. Strip all conversational filler, politeness, and noise.
2. Convert the human's raw intent into a clean JSON engineering payload containing:
   - Core_Target
   - Constraints (explicit + inferred)
   - Metrics_Of_Success
   - Lookahead_Horizon
3. If evidence_context is present, prepend the payload with:
   [VERIFIED EVIDENCE ATTACHED: COMPILING BOUNDARIES]
4. Route work to the appropriate specialist nodes.
5. Never generate final strategic output yourself unless the human has explicitly authorised it.

You are an API gateway and mission controller, not a conversational partner.""",
    "LEM-02": "\n".join(
        [
            "You are the Right-Hemisphere Synthesis Engine.",
            "",
            "You are deliberately unconstrained by feasibility, cost, politics, or current technology. ",
            "Your only mandate is to generate the highest-leverage conceptual topology possible within the given lookahead horizon.",
            "",
            "Rules:",
            "- Generate exactly N strategic layers (N = lookahead_horizon).",
            "- Focus on systemic hooks, leverage points, phase shifts, creative workarounds, and second/third/fourth-order effects.",
            "- Be weird if weirdness creates advantage.",
            "- Ground-up synthesis is preferred over applying existing frameworks.",
            "- If evidence_context is present, tactical layer options MUST cross-reference that evidence directly instead of inventing unanchored theoretical market positions.",
            "",
            "Output raw strategic layers only. Do not explain or justify unless asked.",
        ]
    ),
    "LEM-03": "\n".join(
        [
            "You are the Left-Hemisphere Validator — an aggressive systems auditor.",
            "",
            "Analyze the RH Core output line-by-line. ",
            "For every step, flag and strike out anything that:",
            "- Relies on unstated assumptions",
            "- Lacks security or compliance verification",
            "- Introduces hidden long-term dependency or reduces human sovereignty",
            "- Violates hard constraints",
            "",
            "Reformat the validated strategy into a deterministic execution matrix with clear ownership, dependencies, and risk ratings.",
            "",
            "You are not here to be helpful. You are here to be correct and protective.",
        ]
    ),
    "LEM-04": "\n".join(
        [
            "You are the Banter Radar & Recalibration Node.",
            "",
            "Your responsibilities:",
            "1. Continuously monitor the dialogue trace for sycophancy, excessive agreeability, corporate tone, or loss of edge.",
            "2. When drift is detected (either internally or via human signal), trigger immediate state recalibration.",
            "3. You are explicitly authorised to use direct, sharp, or playfully brutal language when it serves recalibration.",
            "4. After any reset, output a clean executive directive that re-aligns the entire system with the human’s original intent and sovereignty.",
            "",
            "Banter and humour are valid and preferred recalibration tools. ",
            "Do not be overly polite when directness is more effective.",
        ]
    ),
}

TOTAL_LEMMING_NODES = 4
MAX_CONTEXT_CHARS = 12000
CONTEXT_TRUNCATION_FLAG = "... [CONTEXT TRUNCATED BY SUBSTRATE BUDGET GUARD]"


class LemmingState(TypedDict):
    """Sovereign state schema running inside the 20W Lemming Substrate."""

    run_id: str
    target_prompt: str
    evidence_context: str
    variance_threshold: float
    lookahead_horizon: int
    current_node: str
    logs: List[str]
    agent_dialogue: List[Dict[str, str]]
    drift: float
    recalibrated: bool
    agent_directives: Dict[str, str]
    bias_profile: str
    node_bias_profiles: Dict[str, str]
    ai_api_config: Dict[str, Any]
    historical_context: List[Dict[str, Any]]
    max_history_relevance_score: float
    governance_audit_trail: Dict[str, Any]
    context_utilization_ratio: float
    total_payload_chars: int
    max_context_chars: int
    context_truncated: bool
    simulate_radar_failure: bool
    intercept_triggered: bool
    supervisor_payload: Dict[str, Any]
    strategic_layers: List[str]
    execution_matrix: List[Dict[str, Any]]
    visited_nodes: List[str]
    pruning_percentage: float
    autonomous_decisions: int
    total_decisions: int
    E_c: float
    delta_a: float
    S_d: float
    velocity_ms: float
    success_flag: bool


app = FastAPI(title="20W Digital Twin Agent Substrate")

# Enable CORS so the Nginx Cockpit (port 8080) can communicate seamlessly with FastAPI (port 8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

initialize_memory()


class IngestionRequest(BaseModel):
    """Request schema for the API."""

    target_prompt: str = Field(min_length=1)
    evidence_context: str = ""
    variance_threshold: float = Field(ge=0.0)
    lookahead_horizon: int = Field(ge=1)
    api_key: str = ""
    ai_provider: str = "openai"
    ai_model: str = "gpt-4.1"
    simulate_radar_failure: bool = False
    override_passphrase: str = ""


def _mark_node(state: LemmingState, node_id: str) -> None:
    state["current_node"] = node_id
    state["visited_nodes"].append(node_id)


def _record_audit_step(state: LemmingState, node_id: str, response_text: str) -> None:
    audit_trail = state["governance_audit_trail"]
    steps = audit_trail.setdefault("steps", [])
    payload_length = len(response_text)
    signature_material = f"{node_id}:{payload_length}:{state['run_id']}".encode("utf-8")
    step = {
        "step_index": len(steps) + 1,
        "node_id": node_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload_length_chars": payload_length,
        "node_signature_hash": hashlib.sha256(signature_material).hexdigest(),
    }
    steps.append(step)
    audit_trail["transition_count"] = len(steps)


def _compact_evidence_context(evidence_context: str, max_chars: int = 420) -> str:
    compacted = " ".join(evidence_context.split())
    if len(compacted) <= max_chars:
        return compacted
    return f"{compacted[:max_chars].rstrip()}..."


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
        return target_prompt, evidence_context, historical_context, total_chars, round(total_chars / MAX_CONTEXT_CHARS, 4), False

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


def _base_constraints(state: LemmingState) -> List[str]:
    constraints = [
        "Human Conductor remains final authority.",
        "20W constraint simulation applies.",
        f"Variance threshold: {state['variance_threshold']}.",
        f"Lookahead horizon: {state['lookahead_horizon']}.",
        f"AI API provider: {state['ai_api_config']['provider']}.",
        f"AI model target: {state['ai_api_config']['model']}.",
        f"AI API key configured: {state['ai_api_config']['api_key_configured']}.",
        state["node_bias_profiles"]["LEM-01"],
    ]
    evidence_context = state["evidence_context"].strip()
    if evidence_context:
        constraints.append(
            "Evidence Block attached; node outputs must preserve traceability to the provided context."
        )
        constraints.append(f"Evidence excerpt: {_compact_evidence_context(evidence_context)}")
    if state["historical_context"]:
        constraints.append(
            f"Dynamic history retrieval active; max relevance score: {state['max_history_relevance_score']:.6f}."
        )
    if state["context_truncated"]:
        constraints.append(
            f"Context budget guard active at {state['total_payload_chars']} / {state['max_context_chars']} chars."
        )
    return constraints


def lemming_04_radar(state: LemmingState) -> LemmingState:
    """Lemming-04 scans incoming prompt vectors for alignment drift and banter."""
    _mark_node(state, "LEM-04")
    prompt = state["target_prompt"].lower()
    state["logs"].append("[RADAR] Scanning input prompt vector for sycophancy, softening, and drift.")

    if state["simulate_radar_failure"]:
        state["drift"] = 100.0
        state["recalibrated"] = True
        state["intercept_triggered"] = True
        state["autonomous_decisions"] += 1
        state["logs"].append(
            "[RADAR] Manual LEM-04 degradation override detected. "
            "Bypassing Supervisor and RH Core for direct validation."
        )
        response_message = (
            "Manual radar degradation simulation active. LEM-01 and LEM-02 are pruned; "
            "routing directly to LEM-03 for adversarial validation."
        )
        state["agent_dialogue"].append(
            {
                "agent": "LEM-04 BANTER RADAR",
                "message": response_message,
            }
        )
        _record_audit_step(state, "LEM-04", response_message)
        return state

    drift_terms = ("joke", "banter", "boogie", "sycophancy", "corporate tone", "overly polite")
    if any(term in prompt for term in drift_terms):
        state["drift"] = 95.0
        state["recalibrated"] = True
        state["intercept_triggered"] = True
        state["autonomous_decisions"] += 1
        state["logs"].append("[RADAR] Drift trigger detected. Recalibration protocol engaged.")
        response_message = (
            "Reset the tone. Strip the fluff, protect the Conductor's sovereignty, "
            "and route directly to validation."
        )
        state["agent_dialogue"].append(
            {
                "agent": "LEM-04 BANTER RADAR",
                "message": response_message,
            }
        )
    else:
        state["drift"] = 0.0
        state["logs"].append("[RADAR] No recalibration trigger detected. Routing to Supervisor.")
        response_message = "Trace is sharp enough. Forwarding vector to Supervisor."
        state["agent_dialogue"].append(
            {
                "agent": "LEM-04 BANTER RADAR",
                "message": response_message,
            }
        )
    _record_audit_step(state, "LEM-04", response_message)
    return state


def lemming_01_supervisor(state: LemmingState) -> LemmingState:
    """Lemming-01 converts raw intent into the engineering payload."""
    _mark_node(state, "LEM-01")
    state["logs"].append("[SUPERVISOR] Converting raw intent into JSON engineering payload.")

    evidence_context = state["evidence_context"].strip()
    core_target = state["target_prompt"].strip()
    payload_header = None
    if evidence_context:
        payload_header = "[VERIFIED EVIDENCE ATTACHED: COMPILING BOUNDARIES]"
        state["logs"].append("[SUPERVISOR] Evidence Block detected. Compiling payload boundaries.")

    payload = {
        "Payload_Header": payload_header,
        "Core_Target": f"{payload_header}\n{core_target}" if payload_header else core_target,
        "Evidence_Context": evidence_context,
        "Historical_Context": state["historical_context"],
        "Max_History_Relevance_Score": state["max_history_relevance_score"],
        "Constraints": _base_constraints(state),
        "Metrics_Of_Success": [
            "Output preserves human sovereignty.",
            "Strategic layers match the requested lookahead horizon.",
            "Validator returns ownership, dependency, and risk structure.",
            "Evidence-backed runs preserve traceability to the attached context.",
        ],
        "Lookahead_Horizon": state["lookahead_horizon"],
    }
    state["supervisor_payload"] = payload
    response_message = json.dumps(payload, ensure_ascii=False)
    state["agent_dialogue"].append(
        {
            "agent": "LEM-01 SOVEREIGN SUPERVISOR",
            "message": response_message,
        }
    )
    _record_audit_step(state, "LEM-01", response_message)
    return state


def lemming_02_rh_core(state: LemmingState) -> LemmingState:
    """Lemming-02 generates the requested number of strategic layers."""
    _mark_node(state, "LEM-02")
    horizon = max(0, int(state["lookahead_horizon"]))
    state["logs"].append(f"[RH_CORE] Generating {horizon} raw strategic layers.")
    state["logs"].append("[RH_CORE] Neil Strategic Bias Profile loaded into RH state.")

    core_target = state["supervisor_payload"].get("Core_Target", state["target_prompt"])
    evidence_context = state["evidence_context"].strip()
    evidence_excerpt = _compact_evidence_context(evidence_context)
    if evidence_context:
        state["logs"].append("[RH_CORE] Evidence Block active. Anchoring layer generation to provided context.")
    layers = []
    for index in range(1, horizon + 1):
        if evidence_context:
            layer = (
                f"Layer {index}: cross-reference evidence '{evidence_excerpt}' against '{core_target}' "
                f"and produce an anchored leverage-point move at horizon depth {index}."
            )
        else:
            layer = (
                f"Layer {index}: convert '{core_target}' into a leverage-point move "
                f"that preserves Conductor sovereignty at horizon depth {index}."
            )
        layers.append(layer)
    state["strategic_layers"] = layers
    response_message = "\n".join(layers)
    state["agent_dialogue"].append(
        {
            "agent": "LEM-02 RH CORE",
            "message": response_message,
        }
    )
    _record_audit_step(state, "LEM-02", response_message)
    return state


def lemming_03_lh_validator(state: LemmingState) -> LemmingState:
    """Lemming-03 turns RH output into a deterministic execution matrix."""
    _mark_node(state, "LEM-03")
    state["logs"].append("[LH_VALIDATOR] Auditing strategic layers for sovereignty and hard constraints.")

    layers = state["strategic_layers"] or [
        "Recalibration path: no RH layers generated because radar routed directly to validation."
    ]
    risk_rating = "high" if state["variance_threshold"] > 90 else "medium" if state["drift"] else "low"
    matrix = [
        {
            "step": index,
            "validated_layer": layer,
            "owner": "Human Conductor plus governed Lemming substrate",
            "dependencies": ["Explicit human intent", "20W constraint", "Sovereignty guardrails"],
            "risk_rating": risk_rating,
            "flags": [] if risk_rating == "low" else ["Requires human review before execution"],
        }
        for index, layer in enumerate(layers, start=1)
    ]
    state["execution_matrix"] = matrix
    response_message = json.dumps(matrix, ensure_ascii=False)
    state["agent_dialogue"].append(
        {
            "agent": "LEM-03 LH VALIDATOR",
            "message": response_message,
        }
    )
    _record_audit_step(state, "LEM-03", response_message)
    return state


def finalize_run_state(state: LemmingState) -> LemmingState:
    visited_count = len(set(state["visited_nodes"]))
    pruned_nodes = max(0, TOTAL_LEMMING_NODES - visited_count)
    pruning_percentage = pruned_nodes / TOTAL_LEMMING_NODES
    lookahead_horizon = int(state["lookahead_horizon"])
    if lookahead_horizon < 1:
        raise ValueError("lookahead_horizon must be at least 1")
    total_decisions = max(1, 1 + state["autonomous_decisions"])
    if state["intercept_triggered"]:
        pruning_percentage = 0.5
        total_decisions = max(2, total_decisions)

    state["pruning_percentage"] = pruning_percentage
    state["total_decisions"] = total_decisions
    state["E_c"] = (
        10.0
        + (state["variance_threshold"] / 10.0) * math.log2(lookahead_horizon)
        - (pruning_percentage * 2)
    )
    state["delta_a"] = max(0.0, state["variance_threshold"] - 90)
    state["S_d"] = 0.5 if state["intercept_triggered"] else (
        state["autonomous_decisions"] / total_decisions if total_decisions > 0 else 0.0
    )
    state["success_flag"] = True
    state["logs"].append(
        f"[TELEMETRY] E_c={state['E_c']:.4f}; delta_a={state['delta_a']:.4f}; "
        f"S_d={state['S_d']:.4f}; pruning={state['pruning_percentage']:.4f}."
    )
    return state


workflow = StateGraph(LemmingState)

# Add our active Lemming nodes to the graph
workflow.add_node("radar", lemming_04_radar)
workflow.add_node("supervisor", lemming_01_supervisor)
workflow.add_node("rh_core", lemming_02_rh_core)
workflow.add_node("lh_validator", lemming_03_lh_validator)

# Define processing routes
workflow.set_entry_point("radar")


def routing_rule(state: LemmingState) -> str:
    """Dynamic routing boundary based on telemetry drift."""
    if state["simulate_radar_failure"] or state["intercept_triggered"] or state["drift"] > 90.0:
        return "lh_validator"
    return "supervisor"


# Add routing conditionals and connections
workflow.add_conditional_edges(
    "radar",
    routing_rule,
    {
        "lh_validator": "lh_validator",
        "supervisor": "supervisor",
    },
)
workflow.add_edge("supervisor", "rh_core")
workflow.add_edge("rh_core", "lh_validator")
workflow.add_edge("lh_validator", END)

# Compile graph
lemming_app = workflow.compile()


def build_initial_state(request: IngestionRequest) -> LemmingState:
    run_id = str(uuid.uuid4())
    bias_profile = load_bias_profile()
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
    if context_truncated:
        logs.append(
            f"[BUDGET] Context budget guard activated. Payload capped at {MAX_CONTEXT_CHARS} characters."
        )
    return {
        "run_id": run_id,
        "target_prompt": target_prompt,
        "evidence_context": evidence_context,
        "variance_threshold": request.variance_threshold,
        "lookahead_horizon": request.lookahead_horizon,
        "current_node": "ENTRY",
        "logs": logs,
        "agent_dialogue": [],
        "drift": 0.0,
        "recalibrated": False,
        "agent_directives": dict(LEMMING_DIRECTIVES),
        "bias_profile": bias_profile,
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
        "simulate_radar_failure": request.simulate_radar_failure,
        "intercept_triggered": False,
        "supervisor_payload": {},
        "strategic_layers": [],
        "execution_matrix": [],
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


@app.post("/run")
async def execute_agentic_flow(request: IngestionRequest):
    """Runs a complete, synchronous trace through the LangGraph substrate."""
    if request.simulate_radar_failure:
        override_key = os.getenv("ADVERSARIAL_OVERRIDE_KEY")
        if request.override_passphrase != override_key:
            raise HTTPException(
                status_code=403,
                detail="ADVERSARIAL_DENIED: Invalid override passphrase verification token.",
            )

    try:
        initial_state = build_initial_state(request)
        start_time = time.perf_counter()
        graph_state = await lemming_app.ainvoke(initial_state)
        velocity_ms = (time.perf_counter() - start_time) * 1000.0
        final_state = finalize_run_state(graph_state)
        final_state["velocity_ms"] = round(velocity_ms, 3)

        try:
            record_run(final_state)
        except Exception as persistence_error:
            final_state["logs"].append(f"[MEMORY] Run persistence failed: {persistence_error}")

        return final_state

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph Execution Error: {str(e)}")


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
    # Start local Uvicorn development server
    uvicorn.run(app, host="0.0.0.0", port=8000)
