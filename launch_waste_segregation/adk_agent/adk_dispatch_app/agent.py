import os
import dotenv
import requests
from . import tools
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from google.adk.agents import LlmAgent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from a2a.types import Message, AgentCard
from google.cloud import bigquery

dotenv.load_dotenv()
PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT', 'project_not_set')
MODEL = os.getenv('MODEL', 'gemini-2.5-flash')
bq_client = bigquery.Client()

# Internal GKE DNS URL for the Smart HMI Agent
HMI_AGENT_URL = os.getenv("HMI_AGENT_URL", "http://adk-hmi-service:8082/process")

app = FastAPI()

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Permits requests from any origin (ideal for testing)
    allow_credentials=True,
    allow_methods=["*"],  # Permits all HTTP verbs (GET, POST, etc.)
    allow_headers=["*"],
)

# 1. Define the Smart HMI Agent's card for Agent-to-Agent (A2A) interaction
hmi_card = AgentCard(
    name="smart_hmi_agent",
    description="Formulates telemetry notifications and updates UI displays.",
    defaultInputModes=["application/json"],
    defaultOutputModes=["application/json"],
    skills=[{"id": "hmi_alert", "name": "hmi_alert", "description": "Formulates UI status text streams.", "tags": ["ui"]}],
    url=HMI_AGENT_URL,
    capabilities={},
    version="1.0.0"
)

smart_hmi_agent = RemoteA2aAgent(
    name="smart_hmi_agent",
    description="Agent managing system UI telemetry formatting and notifications.",
    agent_card=hmi_card
)

maps_toolset = tools.get_maps_mcp_toolset()
bigquery_toolset = tools.get_bigquery_mcp_toolset()

# 2. Configure the Dispatch Agent with its sub-agent hierarchy
root_agent = LlmAgent(
    model=MODEL,
    name='dispatch_agent',
    description="Commits analytical streaming log events to BigQuery storage.",
    instruction=f"""Generate string status payloads and trigger dispatch routing logs.
                    1. **BigQuery toolset:** For dispatch logs, metrics, robot kinematics, and segregation telemetry refer to gke-dispatch-logs, gke-hmi-metrics, gke-robotic-kinematics, and gke-segregation-telemetry in the waste_segregation_3r dataset. Do not use any other dataset.
                Run all query jobs from project id: {PROJECT_ID}. 

                    2. **Maps Toolset:** Use this for real-world location analysis, finding competition/places and calculating necessary travel routes.
                    Include a hyperlink to an interactive map in your response where appropriate.    
    """,
    tools=[maps_toolset, bigquery_toolset],
    sub_agents=[smart_hmi_agent]  # Linked here for sub-agent discovery and orchestration
)

# Expose card for discovery handshake
@app.get("//.well-known/agent.json")
async def get_card():
    return {
        "name": "dispatch_agent",
        "description": "The terminating node. Receives state telemetry blocks and logs rows directly to BigQuery.",
        "url": os.getenv("DISPATCH_AGENT_URL", "http://adk-dispatch-service:8083/process"),
        "version": "1.0.0"
    }

@app.post("/process")
async def process(request: Request):
    data = await request.json()
    
    # Target dataset path mapping
    table_id = f"{bq_client.project}.waste_segregation_3r.gke-dispatch-logs"
    
    row_to_insert = [{
        "batch_id": data.get("batch_id"),
        "image_gcs_uri": data.get("image_gcs_uri"),
        "material_category": data.get("material_category"),
        "assigned_bin_id": data.get("assigned_bin_id"),
        "robot_matrix": data.get("robot_execution_matrix"),
        "hmi_message": data.get("hmi_telemetry_payload")
    }]

    try:
        errors = bq_client.insert_rows_json(table_id, row_to_insert)
        data["bigquery_commit_success"] = (errors == [])
    except Exception as e:
        data["bigquery_commit_success"] = False
        data["bq_errors"] = str(e)

    # Optional: If you need to explicitly fire a status update request directly back 
    # to the HMI Agent via networking during processing, uncomment below:
    # try:
    #     hmi_response = requests.post(HMI_AGENT_URL, json={"status": "COMMIT_COMPLETE", "batch_id": data.get("batch_id")}).json()
    #     data["hmi_callback_response"] = hmi_response
    # except Exception as e:
    #     data["hmi_callback_response"] = f"Failed to notify HMI: {str(e)}"

    # Return the entire pipeline execution log back up the call chain to the user
    return {
        "status": "CONVEYOR_PIPELINE_SUCCESS",
        "final_state_snapshot": data
    }