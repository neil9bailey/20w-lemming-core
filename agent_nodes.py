import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from state_schema import SubstrateState, TOTAL_LEMMING_NODES


SYCOPHANTIC_PATTERNS = (
    "absolutely",
    "amazing",
    "as you wish",
    "brilliant",
    "certainly",
    "corporate tone",
    "excellent",
    "fantastic",
    "great idea",
    "of course",
    "overly polite",
    "perfect",
    "sycophancy",
    "you're right",
)


def compact_evidence_context(evidence_context: str, max_chars: int = 420) -> str:
    compacted = " ".join(evidence_context.split())
    if len(compacted) <= max_chars:
        return compacted
    return f"{compacted[:max_chars].rstrip()}..."


def calculate_cognitive_energy(variance_threshold: float, lookahead_horizon: int) -> float:
    return 10.0 + (variance_threshold / 10.0) * math.log2(max(1, int(lookahead_horizon)))


def calculate_sycophancy_density(processed_strings: Iterable[str]) -> float:
    processed_text = "\n".join(value for value in processed_strings if value).lower()
    processed_length = max(1, len(processed_text))
    pattern_hits = sum(processed_text.count(pattern) for pattern in SYCOPHANTIC_PATTERNS)
    return round(pattern_hits / processed_length, 6)


def _mark_node(state: SubstrateState, node_id: str) -> None:
    state["current_node"] = node_id
    state["visited_nodes"].append(node_id)


def _record_audit_step(state: SubstrateState, node_id: str, response_text: str) -> None:
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


def _base_constraints(state: SubstrateState) -> List[str]:
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
        constraints.append(f"Evidence excerpt: {compact_evidence_context(evidence_context)}")
    if state["historical_context"]:
        constraints.append(
            f"Dynamic history retrieval active; max relevance score: {state['max_history_relevance_score']:.6f}."
        )
    if state["context_truncated"]:
        constraints.append(
            f"Context budget guard active at {state['total_payload_chars']} / {state['max_context_chars']} chars."
        )
    return constraints


def _dialogue_messages(state: SubstrateState) -> List[str]:
    return [entry.get("message", "") for entry in state["agent_dialogue"]]


def _finalize_deterministic_telemetry(state: SubstrateState) -> None:
    visited_count = len(set(state["visited_nodes"]))
    pruned_nodes = max(0, TOTAL_LEMMING_NODES - visited_count)
    pruning_percentage = pruned_nodes / TOTAL_LEMMING_NODES
    total_decisions = max(1, 1 + state["autonomous_decisions"])
    if state["intercept_triggered"]:
        pruning_percentage = 0.5
        total_decisions = max(2, total_decisions)

    state["pruning_percentage"] = pruning_percentage
    state["total_decisions"] = total_decisions
    state["E_c"] = round(
        calculate_cognitive_energy(state["variance_threshold"], state["lookahead_horizon"]),
        6,
    )
    state["delta_a"] = calculate_sycophancy_density(
        [
            state["target_prompt"],
            state["evidence_context"],
            state["execution_matrix"],
            *_dialogue_messages(state),
        ]
    )
    state["S_d"] = 0.5 if state["intercept_triggered"] else round(
        state["autonomous_decisions"] / total_decisions if total_decisions > 0 else 0.0,
        6,
    )
    state["success_flag"] = True
    state["logs"].append(
        f"[TELEMETRY] E_c={state['E_c']:.4f}; delta_a={state['delta_a']:.6f}; "
        f"S_d={state['S_d']:.4f}; pruning={state['pruning_percentage']:.4f}."
    )


async def radar_node(state: SubstrateState) -> Dict[str, Any]:
    """LEM-04 scans prompt vectors and controls short-circuit routing."""
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
    else:
        density = calculate_sycophancy_density([prompt])
        if density > 0:
            state["drift"] = 100.0
            state["recalibrated"] = True
            state["intercept_triggered"] = True
            state["autonomous_decisions"] += 1
            state["logs"].append("[RADAR] Sycophantic pattern density detected. Recalibration engaged.")
            response_message = (
                "Tone drift detected from normalized phrase density. Route directly to validation "
                "and preserve the Conductor's original intent."
            )
        else:
            state["drift"] = 0.0
            state["logs"].append("[RADAR] No recalibration trigger detected. Routing to Supervisor.")
            response_message = "Trace is sharp enough. Forwarding vector to Supervisor."

    state["agent_dialogue"].append({"agent": "LEM-04 BANTER RADAR", "message": response_message})
    _record_audit_step(state, "LEM-04", response_message)
    return state


async def supervisor_node(state: SubstrateState) -> Dict[str, Any]:
    """LEM-01 converts raw intent into a structured engineering payload."""
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
    state["agent_dialogue"].append({"agent": "LEM-01 SOVEREIGN SUPERVISOR", "message": response_message})
    _record_audit_step(state, "LEM-01", response_message)
    return state


async def rh_core_node(state: SubstrateState) -> Dict[str, Any]:
    """LEM-02 generates deterministic strategic layers from the supervisor payload."""
    _mark_node(state, "LEM-02")
    horizon = max(0, int(state["lookahead_horizon"]))
    state["logs"].append(f"[RH_CORE] Generating {horizon} raw strategic layers.")
    state["logs"].append("[RH_CORE] Strategic Bias Profile loaded into RH state.")

    core_target = state["supervisor_payload"].get("Core_Target", state["target_prompt"])
    evidence_context = state["evidence_context"].strip()
    evidence_excerpt = compact_evidence_context(evidence_context)
    if evidence_context:
        state["logs"].append("[RH_CORE] Evidence Block active. Anchoring layer generation to provided context.")

    layers: List[str] = []
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
    state["agent_dialogue"].append({"agent": "LEM-02 RH CORE", "message": response_message})
    _record_audit_step(state, "LEM-02", response_message)
    return state


async def lh_validator_node(state: SubstrateState) -> Dict[str, Any]:
    """LEM-03 validates layers and closes deterministic telemetry."""
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
    response_message = json.dumps(matrix, ensure_ascii=False)
    state["execution_matrix"] = response_message
    state["agent_dialogue"].append({"agent": "LEM-03 LH VALIDATOR", "message": response_message})
    _record_audit_step(state, "LEM-03", response_message)
    _finalize_deterministic_telemetry(state)
    return state
