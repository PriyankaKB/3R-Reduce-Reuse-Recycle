import os
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from google.adk import Agent, Workflow

app = FastAPI(title="GKE Cloud-Native Multi-Agent Orchestrator")

# Define our highly scalable validation state shared between GKE services
class WasteStreamPayload(BaseModel):
    batch_id: str
    image_gcs_uri: str
    material_category: str = "UNKNOWN"
    target_bin_id: str = "NONE"
    robot_execution_matrix: str = "PENDING"
    hmi_telemetry_payload: str = ""
    bigquery_commit_success: bool = False

# Fetch our local internal GKE CoreDNS target mapping addresses
SEGREGATION_URL = os.getenv("SEGREGATION_AGENT_URL", "http://adk-segregation-service:8080/process")
ROBOTIC_URL = os.getenv("ROBOTIC_ARM_AGENT_URL", "http://adk-robotic-service:8081/process")
HMI_URL = os.getenv("HMI_AGENT_URL", "http://adk-hmi-service:8082/process")
DISPATCH_URL = os.getenv("DISPATCH_AGENT_URL", "http://adk-dispatch-service:8083/process")

# Define Google ADK Execution Node Steps
def run_segregation_step(state: dict) -> dict:
    res = requests.post(SEGREGATION_URL, json=state).json()
    return res

def run_robotic_step(state: dict) -> dict:
    res = requests.post(ROBOTIC_URL, json=state).json()
    return res

def run_hmi_step(state: dict) -> dict:
    res = requests.post(HMI_URL, json=state).json()
    return res

def run_dispatch_step(state: dict) -> dict:
    res = requests.post(DISPATCH_URL, json=state).json()
    return res

# Construct the Sequential Multi-Agent Workflow Engine Graph using ADK
workflow_graph = Workflow(
    name="project_3r_waste_segregation_pipeline",
    edges=[
        {"source": "START", "target": run_segregation_step},
        {"source": run_segregation_step, "target": run_robotic_step},
        {"source": run_robotic_step, "target": run_hmi_step},
        {"source": run_hmi_step, "target": run_dispatch_step},
        {"source": run_dispatch_step, "target": "END"}
    ]
)


@app.post("/v1/pipeline/sort")
async def trigger_conveyor_sorting_loop(payload: WasteStreamPayload):
    try:
        # Convert Pydantic payload to clean state dict maps for ADK execution loops
        initial_state = payload.model_dump()
        final_state = workflow_graph.run(initial_state)
        return final_state
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conveyor pipeline workflow error: {str(e)}")