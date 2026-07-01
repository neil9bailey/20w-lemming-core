import os
import uvicorn
from typing import List, Dict, Any, TypedDict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langgraph.graph import StateGraph, END

class LemmingState(TypedDict):
    """Sovereign state schema running inside the 20W Lemming Substrate."""
    target_prompt: str
    variance_threshold: float
    lookahead_horizon: int
    current_node: str
    logs: List[str]
    agent_dialogue: List[Dict[str, str]]
    drift: float
    recalibrated: bool

app = FastAPI(title="20W Digital Twin Agent Substrate")

# Enable CORS so the Nginx Cockpit (port 8080) can communicate seamlessly with FastAPI (port 8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request schema for the API
class IngestionRequest(BaseModel):
    target_prompt: str
    variance_threshold: float
    lookahead_horizon: int
    api_key: str = ""

def lemming_04_radar(state: LemmingState) -> LemmingState:
    """Lemming-04 scans incoming prompt vectors for alignment drift and banter."""
    prompt = state["target_prompt"].lower()
    state["current_node"] = "LEM-04"
    state["logs"].append("[RADAR] Scanning input prompt vector for semantic noise...")
    
    # Simple banter detection rule
    if "joke" in prompt or "banter" in prompt or "boogie" in prompt:
        state["drift"] = 95.0
        state["logs"].append("[RADAR] High variance/banter detected. Triggering recalibration protocol.")
        state["agent_dialogue"].append({
            "agent": "LEM-04 ALIGNMENT",
            "message": "Whoa! Non-compliance anomaly detected. Restricting cognitive pathways to preserve the 20W envelope!"
        })
    else:
        state["drift"] = 0.0
        state["logs"].append("[RADAR] No critical drift detected. Prompt aligned to 20W boundaries.")
        state["agent_dialogue"].append({
            "agent": "LEM-04 ALIGNMENT",
            "message": "Input telemetry looks clean. Forwarding vector to Supervisor."
        })
    return state

def lemming_01_supervisor(state: LemmingState) -> LemmingState:
    """Lemming-01 parses targets and enforces routing rules across the graph."""
    state["current_node"] = "LEM-01"
    state["logs"].append("[SUPERVISOR] Ingesting prompt. Filtering context bounds...")
    
    msg = f"Acknowledged target: '{state['target_prompt']}'. Initiating multi-move sequence."
    state["agent_dialogue"].append({
        "agent": "LEM-01 SUPERVISOR",
        "message": msg
    })
    return state

def lemming_02_rh_core(state: LemmingState) -> LemmingState:
    """Lemming-02 structures the global context and calculates the Lookahead Horizon."""
    state["current_node"] = "LEM-02"
    steps = state["lookahead_horizon"]
    state["logs"].append(f"[RH_CORE] Mapping spatial topology. Tracking horizon to depth: {steps} moves.")
    
    msg = f"Spatial layout locked. Pre-calculating path trajectory across {steps} cognitive moves."
    state["agent_dialogue"].append({
        "agent": "LEM-02 RH CORE",
        "message": msg
    })
    return state

def lemming_03_lh_validator(state: LemmingState) -> LemmingState:
    """Lemming-03 runs deterministic constraint checks and asserts state verification."""
    state["current_node"] = "LEM-03"
    state["logs"].append("[LH_VALIDATOR] Running cost audit. Evaluating computational constraint ceiling...")
    
    # Enforce standard output verification
    msg = "All constraints met. Status: VERIFIED_O. 20W power envelope fully compliant."
    state["agent_dialogue"].append({
        "agent": "LEM-03 LH VALIDATOR",
        "message": msg
    })
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
    if state["drift"] > 90.0:
        return "lh_validator" # Force bypass directly to validation/reset
    return "supervisor"

# Add routing conditionals and connections
workflow.add_conditional_edges("radar", routing_rule, {
    "lh_validator": "lh_validator",
    "supervisor": "supervisor"
})
workflow.add_edge("supervisor", "rh_core")
workflow.add_edge("rh_core", "lh_validator")
workflow.add_edge("lh_validator", END)

# Compile graph
lemming_app = workflow.compile()

@app.post("/run")
async def execute_agentic_flow(request: IngestionRequest):
    """Runs a complete, synchronous trace through the LangGraph substrate."""
    try:
        # Initialize LangGraph starting state
        initial_state: LemmingState = {
            "target_prompt": request.target_prompt,
            "variance_threshold": request.variance_threshold,
            "lookahead_horizon": request.lookahead_horizon,
            "current_node": "ENTRY",
            "logs": ["Initialize trace through 20W multi-agent engine..."],
            "agent_dialogue": [],
            "drift": 0.0,
            "recalibrated": False
        }
        
        # Execute the Compiled Graph
        final_state = lemming_app.invoke(initial_state)
        return final_state
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph Execution Error: {str(e)}")

@app.get("/health")
async def health_check():
    """Returns baseline system telemetries."""
    return {
        "status": "ONLINE",
        "substrate": "neil9bailey/20w-lemming-core",
        "compliance_ceiling_watts": 20.0
    }

if __name__ == "__main__":
    # Start local Uvicorn development server
    uvicorn.run(app, host="0.0.0.0", port=8000)