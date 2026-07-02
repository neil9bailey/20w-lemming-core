import hashlib
import asyncio
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

from state_schema import SubstrateState, TOTAL_LEMMING_NODES


logger = logging.getLogger(__name__)

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

EVIDENCE_CHUNK_MAX_CHARS = 3000
SOURCE_READ_BUFFER_CHARS = 65536
SUPPORTED_EXTERNAL_SOURCE_SUFFIXES = {".txt", ".json", ".md"}
EXCLUDED_EXTERNAL_SOURCE_PARTS = {
    ".agents",
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "agents",
    "node_modules",
    "venv",
}
LINGUISTIC_FILLER_PATTERNS = (
    "it is important to note that",
    "please note that",
    "in order to",
    "as previously mentioned",
    "for the avoidance of doubt",
)


def compact_evidence_context(evidence_context: str, max_chars: int = 420) -> str:
    compacted = " ".join(evidence_context.split())
    if len(compacted) <= max_chars:
        return compacted
    return f"{compacted[:max_chars].rstrip()}..."


def chunk_text_by_token_density(text: str, max_chars: int = EVIDENCE_CHUNK_MAX_CHARS) -> List[str]:
    """Split evidence into deterministic word-bound chunks without breaking token groups."""
    normalized = " ".join(str(text).split())
    if not normalized:
        return []
    if len(normalized) <= max_chars:
        return [normalized]

    chunks: List[str] = []
    current_tokens: List[str] = []
    current_length = 0
    for token in normalized.split(" "):
        token_length = len(token) + (1 if current_tokens else 0)
        if current_tokens and current_length + token_length > max_chars:
            chunks.append(" ".join(current_tokens))
            current_tokens = [token]
            current_length = len(token)
        else:
            current_tokens.append(token)
            current_length += token_length

    if current_tokens:
        chunks.append(" ".join(current_tokens))
    return chunks


def _evidence_segments(evidence_context: str) -> List[str]:
    stripped = evidence_context.strip()
    if not stripped:
        return []
    if stripped.startswith("[") and stripped.endswith("]"):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return [evidence_context]
        if isinstance(parsed, list):
            return [
                item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
                for item in parsed
            ]
    return [evidence_context]


def _strip_linguistic_fluff(text: str) -> str:
    refined = " ".join(text.split())
    lowered = refined.lower()
    for filler in LINGUISTIC_FILLER_PATTERNS:
        if filler in lowered:
            refined = refined.replace(filler, "").replace(filler.title(), "")
            lowered = refined.lower()
    return " ".join(refined.split())


async def _compress_evidence_chunk(chunk: str) -> str:
    return _strip_linguistic_fluff(chunk)


async def _prepare_streaming_evidence_context(evidence_context: str) -> tuple[str, int]:
    chunks: List[str] = []
    for segment in _evidence_segments(evidence_context):
        chunks.extend(chunk_text_by_token_density(segment))

    if not chunks:
        return "", 0
    if len(chunks) == 1 and len(chunks[0]) <= EVIDENCE_CHUNK_MAX_CHARS:
        return chunks[0], 1

    refined_chunks = await asyncio.gather(*(_compress_evidence_chunk(chunk) for chunk in chunks))
    return "\n".join(chunk for chunk in refined_chunks if chunk), len(refined_chunks)


def _is_hidden_or_development_path(path: Path, root: Path) -> bool:
    if root.name.lower().startswith(".") or root.name.lower() in EXCLUDED_EXTERNAL_SOURCE_PARTS:
        return True
    try:
        relative_parts = path.relative_to(root).parts
    except ValueError:
        relative_parts = path.parts
    for part in relative_parts:
        normalized_part = part.lower()
        if normalized_part.startswith(".") or normalized_part in EXCLUDED_EXTERNAL_SOURCE_PARTS:
            return True
    return False


def _read_text_file_bounded(file_path: Path) -> str:
    chunks: List[str] = []
    with file_path.open("r", encoding="utf-8", errors="replace") as source_file:
        while True:
            chunk = source_file.read(SOURCE_READ_BUFFER_CHARS)
            if not chunk:
                break
            chunks.append(chunk)
    return "".join(chunks)


async def sync_external_source_payloads(directory_path: str) -> List[str]:
    """Collect supported text sources without blocking the async graph execution loop."""
    if not directory_path or not directory_path.strip():
        return []

    root = Path(directory_path).expanduser()
    if not root.exists() or not root.is_dir():
        logger.info("[SOURCE_MONITOR] External source root missing or not a directory: %s", root)
        return []

    payloads: List[str] = []
    try:
        source_paths = root.rglob("*")
        for file_path in source_paths:
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in SUPPORTED_EXTERNAL_SOURCE_SUFFIXES:
                continue
            if _is_hidden_or_development_path(file_path, root):
                continue
            try:
                payload = await asyncio.to_thread(_read_text_file_bounded, file_path)
            except OSError as exc:
                logger.warning("[SOURCE_MONITOR] Skipping unreadable source file %s: %s", file_path, exc)
                continue
            if payload.strip():
                payloads.append(payload)
                await asyncio.sleep(0)
    except OSError as exc:
        logger.warning("[SOURCE_MONITOR] External source scan interrupted for %s: %s", root, exc)
    return payloads


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


def _bias_factor(state: SubstrateState, bias_key: str) -> float:
    active_profile = state.get("active_bias_profile", {})
    try:
        return min(1.0, max(0.0, float(active_profile.get(bias_key, 0.5))))
    except (TypeError, ValueError):
        return 0.5


def _bias_instruction(state: SubstrateState, bias_key: str) -> str:
    return f"[BIAS ENFORCEMENT FACTOR: {_bias_factor(state, bias_key):.2f}]"


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
    external_source_count = 0
    external_source_root = str(state.get("external_source_root", "")).strip()
    if external_source_root:
        external_payloads = await sync_external_source_payloads(external_source_root)
        external_source_count = len(external_payloads)
        if external_payloads:
            external_chunks: List[str] = []
            for payload in external_payloads:
                external_chunks.extend(chunk_text_by_token_density(payload))
            refined_external_chunks = await asyncio.gather(
                *(_compress_evidence_chunk(chunk) for chunk in external_chunks)
            )
            external_context = "\n".join(chunk for chunk in refined_external_chunks if chunk)
            evidence_context = "\n".join(
                part
                for part in [
                    evidence_context,
                    "[EXTERNAL SOURCE PAYLOADS]",
                    external_context,
                ]
                if part
            )
            state["evidence_context"] = evidence_context
            state["logs"].append(
                f"[SUPERVISOR] Evidence_Source_Count={external_source_count}; "
                "external source payloads synchronized into evidence context."
            )
        else:
            state["logs"].append(
                f"[SUPERVISOR] Evidence_Source_Count=0; no supported external source payloads found at {external_source_root}."
            )

    evidence_chunk_count = 0
    if evidence_context:
        evidence_context, evidence_chunk_count = await _prepare_streaming_evidence_context(evidence_context)
        state["evidence_context"] = evidence_context
        if evidence_chunk_count > 1:
            state["logs"].append(
                f"[SUPERVISOR] Streaming evidence payload normalized into {evidence_chunk_count} chunks."
            )
    core_target = state["target_prompt"].strip()
    payload_header = None
    if evidence_context:
        payload_header = "[VERIFIED EVIDENCE ATTACHED: COMPILING BOUNDARIES]"
        state["logs"].append("[SUPERVISOR] Evidence Block detected. Compiling payload boundaries.")

    bias_instruction = _bias_instruction(state, "supervisor_bias")
    payload = {
        "Payload_Header": payload_header,
        "Core_Target": f"{payload_header}\n{core_target}" if payload_header else core_target,
        "Evidence_Context": evidence_context,
        "Historical_Context": state["historical_context"],
        "Evidence_Chunk_Count": evidence_chunk_count,
        "Evidence_Source_Count": external_source_count,
        "External_Source_Root": external_source_root or None,
        "Max_History_Relevance_Score": state["max_history_relevance_score"],
        "Constraints": [*_base_constraints(state), bias_instruction],
        "Bias_Enforcement_Factor": bias_instruction,
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
    bias_instruction = _bias_instruction(state, "creative_bias")
    state["logs"].append(f"[RH_CORE] Generating {horizon} raw strategic layers.")
    state["logs"].append("[RH_CORE] Strategic Bias Profile loaded into RH state.")
    state["logs"].append(f"[RH_CORE] {bias_instruction}")

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
                f"and produce an anchored leverage-point move at horizon depth {index}. {bias_instruction}"
            )
        else:
            layer = (
                f"Layer {index}: convert '{core_target}' into a leverage-point move "
                f"that preserves Conductor sovereignty at horizon depth {index}. {bias_instruction}"
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
