from typing import Any, Dict, List, TypedDict


TOTAL_LEMMING_NODES = 4
MAX_CONTEXT_CHARS = 12000
CONTEXT_TRUNCATION_FLAG = "... [CONTEXT TRUNCATED BY SUBSTRATE BUDGET GUARD]"
CONCURRENCY_LOCK_LOG = (
    "[CONCURRENCY] Secondary invocation intercepted. Substrate state lock active. "
    "Request queued sequentially to prevent transactional collision."
)


DEFAULT_AGENT_DIRECTIVES: Dict[str, str] = {
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
            "You are deliberately unconstrained by feasibility, cost, politics, or current technology.",
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
            "You are the Left-Hemisphere Validator - an aggressive systems auditor.",
            "",
            "Analyze the RH Core output line-by-line.",
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
            "4. After any reset, output a clean executive directive that re-aligns the entire system with the human's original intent and sovereignty.",
            "",
            "Banter and humour are valid and preferred recalibration tools.",
            "Do not be overly polite when directness is more effective.",
        ]
    ),
}


class SubstrateState(TypedDict):
    """Canonical LangGraph state carrier for the 20W Lemming substrate."""

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
    active_bias_profile: Dict[str, Any]
    node_bias_profiles: Dict[str, str]
    ai_api_config: Dict[str, Any]
    historical_context: List[Dict[str, Any]]
    max_history_relevance_score: float
    governance_audit_trail: Dict[str, Any]
    context_utilization_ratio: float
    total_payload_chars: int
    max_context_chars: int
    context_truncated: bool
    lock_contention_detected: bool
    simulate_radar_failure: bool
    intercept_triggered: bool
    supervisor_payload: Dict[str, Any]
    strategic_layers: List[str]
    execution_matrix: str
    visited_nodes: List[str]
    pruning_percentage: float
    autonomous_decisions: int
    total_decisions: int
    E_c: float
    delta_a: float
    S_d: float
    velocity_ms: float
    success_flag: bool
