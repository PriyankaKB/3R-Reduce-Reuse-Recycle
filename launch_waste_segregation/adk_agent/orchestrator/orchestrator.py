import os
import requests
import dotenv
import uuid
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.adk import Agent, Workflow
from google.adk import Runner
from google.adk.sessions import InMemorySessionService

# Load environment variables from .env file
dotenv.load_dotenv()

# 1. Strictly fetch the project ID. If missing, raise a configuration error.
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
if not PROJECT_ID:
    raise RuntimeError("CRITICAL: GOOGLE_CLOUD_PROJECT environment variable is not set!")

# 2. Fetch the bucket name. If not set, construct a generic bucket name dynamically 
# using the active project ID variable. No hardcoded names allowed.
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET")
if not GCS_BUCKET_NAME:
    GCS_BUCKET_NAME = f"3r-autonoumous-waste-segregation-{PROJECT_ID}"

# Configure logger once at app startup
logging.basicConfig(
    level=logging.INFO,  # or DEBUG for more detail
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("conveyor")

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

# Default image URI for testing purposes; can be overridden by the frontend
default_image_uri = f"gs://{GCS_BUCKET_NAME}/final_waste_dataset/paper/Paper_1.jpg"

# 2. Get the app configuration from the environment variable
@app.get("/api/config")
def get_runtime_config():
    # Return the validated backend variables directly to the frontend
    return {
        "bucket_name": GCS_BUCKET_NAME,
        "project_id": PROJECT_ID,
        "image_gcs_uri": os.environ.get("IMAGE_GCS_URI", default_image_uri),
    }

# 2. API to POST and dynamically write/set os.environ["IMAGE_GCS_URI"] from UI at runtime
class ConfigUpdateRequest(BaseModel):
    image_gcs_uri: str


@app.post("/api/config")
def update_config(payload: ConfigUpdateRequest):
    uri = payload.image_gcs_uri.strip()
    if not uri.startswith("gs://"):
         raise HTTPException(status_code=400, detail="Invalid GCS URI. Must start with 'gs://'")
    
    # Strictly update the OS environment variable at runtime!
    os.environ["IMAGE_GCS_URI"] = uri
    return {
        "message": "Server-side environment variable updated successfully!",
        "IMAGE_GCS_URI": os.environ["IMAGE_GCS_URI"]
    }


# 2. Update your FastAPI POST endpoint to use the correct app_name
@app.post("/adk_segregation_app/run")
@app.post("/v1/pipeline/sort")
async def trigger_conveyor_sorting_loop(payload: dict):
    try:
        session_id = str(uuid.uuid4())  # Generate a unique session ID
        user_id = "user_1"

        validated = WasteStreamPayload(**payload)
        logger.info("Received payload: %s", validated.dict())
        
        # Create a session using "adk_segregation_app"
        await session_service.create_session(
            app_name="adk_segregation_app", # <-- Updated
            user_id=user_id,
            session_id=session_id,
            state=validated.dict()
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
        return {"status": "ok", "payload": session.state}
    
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Conveyor pipeline workflow error: {str(e)}"
        )


