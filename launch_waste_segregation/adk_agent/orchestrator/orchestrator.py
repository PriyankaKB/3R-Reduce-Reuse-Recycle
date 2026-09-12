import os
import requests
import dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.adk import Agent, Workflow
from google.adk import Runner
from google.adk.session import InMemorySessionService

# Load environment variables from .env file
dotenv.load_dotenv()

app = FastAPI(title="GKE Cloud-Native Multi-Agent Orchestrator")

# Allow these origins to access the API
origins = [
    "http://localhost", # Localhost for development
    "https://localhost:3000", # Localhost for development
    "http://127.0.0.1:3000", # Localhost for development
    "https://console.cloud.google.com",   # Google Cloud Console
    "http://adk-segregation-service:8080/process", # Segregation Service
    "http://adk-robotic-service:8081/process", # Robotic Service
    "http://adk-hmi-service:8082/process", # HMI Service
    "http://adk-dispatch-service:8083/process", # Dispatch Service
]

# Dynamically add the FRONTEND_URL environment variable if it exists
frontend_url = os.getenv("FRONTEND_URL")
if frontend_url:
    # Handles both a single URL or comma-separated URLs
    for url in frontend_url.split(","):
        origins.append(url.strip())

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Permits requests from any origin (ideal for testing)
    allow_credentials=True,
    allow_methods=["*"],  # Permits all HTTP verbs (GET, POST, etc.)
    allow_headers=["*"],
)

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
# Construct the Sequential Multi-Agent Workflow Engine Graph using ADK (CORRECTED)
# Construct the Sequential Multi-Agent Workflow Engine Graph using ADK (CORRECTED)
# Construct the Sequential Multi-Agent Workflow Engine Graph using ADK (CORRECTED)
workflow_graph = Workflow(
    name="adk_segregation_app",
    edges=[
        ("START", run_segregation_step),
        (run_segregation_step, run_robotic_step),
        (run_robotic_step, run_hmi_step),
        (run_hmi_step, run_dispatch_step)
        # No transition to "END" is needed; the workflow naturally terminates after run_dispatch_step
    ]
)

# 1. Initialize the ADK 2 Session Service and Runner using "adk_segregation_app"
session_service = InMemorySessionService()
runner = Runner(
    agent=workflow_graph,
    app_name="adk_segregation_app", # <-- Updated to match your workflow name
    session_service=session_service,
)

# 2. Update your FastAPI POST endpoint to use the correct app_name
@app.post("/adk_segregation_app/run")
@app.post("/v1/pipeline/sort")
async def trigger_conveyor_sorting_loop(payload: dict):
    try:
        session_id = "temp_session"
        user_id = "user_1"
        
        # Create a session using "adk_segregation_app"
        await session_service.create_session(
            app_name="adk_segregation_app", # <-- Updated
            user_id=user_id,
            session_id=session_id,
            state=payload
        )
        
        # Execute the workflow
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id
        ):
            pass
            
        # Retrieve the final mutated state from the session
        session = await session_service.get_session(
            app_name="adk_segregation_app", # <-- Updated
            user_id=user_id,
            session_id=session_id
        )
        
        return session.state
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Conveyor pipeline workflow error: {str(e)}"
        )
