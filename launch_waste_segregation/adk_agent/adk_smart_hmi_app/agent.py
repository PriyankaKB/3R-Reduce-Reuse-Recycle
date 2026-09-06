import os
import dotenv
import requests
from . import tools
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from google.adk.agents import LlmAgent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from a2a.types import Message, AgentCard
from datetime import datetime

dotenv.load_dotenv()

PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT', 'project_not_set')
MODEL = os.getenv('MODEL', 'gemini-2.5-flash')

# Endpoints mapping across the GKE internal DNS service topology
SEGREGATION_AGENT_URL = os.getenv("SEGREGATION_AGENT_URL", "http://adk-segregation-service:8080/process")
ROBOTIC_ARM_AGENT_URL = os.getenv("ROBOTIC_ARM_AGENT_URL", "http://adk-robotic-service:8081/process")
DISPATCH_AGENT_URL = os.getenv("DISPATCH_AGENT_URL", "http://adk-dispatch-service:8083/process")

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

# --- 1. Define Agent Cards for Multi-Agent Collaboration Network ---

segregation_card = AgentCard(
    name="segregation_agent",
    description="Processes raw input/GCS streams to extract and classify waste material categories.",
    defaultInputModes=["application/json"],
    defaultOutputModes=["application/json"],
    skills=[{"id": "material_classification", "name": "material_classification", "description": "Gemini-powered multimodal classification", "tags": ["vision"]}],
    url=SEGREGATION_AGENT_URL,
    capabilities={},
    version="1.0.0"
)

robotic_card = AgentCard(
    name="robotic_arm_agent",
    description="Calculates grid coordinates, physics trajectories, and assigns target sorting bin mappings.",
    defaultInputModes=["application/json"],
    defaultOutputModes=["application/json"],
    skills=[{"id": "kinematics_calc", "name": "kinematics_calc", "description": "Kinematics calculation engine", "tags": ["robotics"]}],
    url=ROBOTIC_ARM_AGENT_URL,
    capabilities={},
    version="1.0.0"
)

dispatch_card = AgentCard(
    name="dispatch_agent",
    description="Commits analytical streaming log events to BigQuery storage.",
    defaultInputModes=["application/json"],
    defaultOutputModes=["application/json"],
    skills=[{"id": "bq_commit", "name": "bq_commit", "description": "BigQuery ingestion gateway", "tags": ["database"]}],
    url=DISPATCH_AGENT_URL,
    capabilities={},
    version="1.0.0"
)

# --- 2. Setup Remote A2A Instances ---

segregation_agent = RemoteA2aAgent(
    name="segregation_agent",
    description="Agent handling initial vision intelligence and ingestion hooks.",
    agent_card=segregation_card
)

robotic_arm_agent = RemoteA2aAgent(
    name="robotic_arm_agent",
    description="Agent handling spatial grid sorting evaluations.",
    agent_card=robotic_card
)

dispatch_agent = RemoteA2aAgent(
    name="dispatch_agent",
    description="Agent handling final historical persistence operations.",
    agent_card=dispatch_card
)

maps_toolset = tools.get_maps_mcp_toolset()
bigquery_toolset = tools.get_bigquery_mcp_toolset()

# --- 3. Define Orchestrated Smart HMI LlmAgent Instance ---

root_agent = LlmAgent(
    model=MODEL,
    name='smart_hmi_agent',
    description="Formats user telemetry alerts and orchestrates verification between upstream/downstream nodes.",
    instruction=f"""Generate string status payloads and trigger dispatch routing logs.
                    1. **BigQuery toolset:** Access waste_categories_data, recyclable_materials_data, plastic_segregation_data, foam_segregation_data, and dustbin_color_codes in the waste_segregation_3r dataset. For dispatch logs, metrics, robot kinematics, and segrgation telemetry refer to gke-dispatch-logs, gke-hmi-metrics, gke-robotic-kinematics, and gke-segregation-telemetry in the waste_segregation_3r dataset. Do not use any other dataset.
                Run all query jobs from project id: {PROJECT_ID}. 

                    2. **Maps Toolset:** Use this for real-world location analysis, finding competition/places and calculating necessary travel routes.
                    Include a hyperlink to an interactive map in your response where appropriate.    
    """,
    # Registering all 3 sub-agents allows the LLM to orchestrate cross-agent communication if necessary
    tools=[maps_toolset, bigquery_toolset],
    sub_agents=[dispatch_agent, segregation_agent, robotic_arm_agent]
)

@app.get("/.well-known/agent.json")
async def get_card():
    return {
        "name": "smart_hmi_agent",
        "description": "Formulates real-time notification streams and diagnostic telemetry lines.",
        "url": os.getenv("HMI_AGENT_URL", "http://adk-hmi-service:8082/process"),
        "version": "1.0.0"
    }

@app.post("/process")
async def process(request: Request):
    incoming_data = await request.json()
    
    # Current timestamp for telemetry logs
    current_timestamp = datetime.utcnow().isoformat() + "Z"
    
    # Extract values with fallbacks matching your exact BigQuery baseline definitions
    batch_id = incoming_data.get("batch_id", "B-UNKNOWN")
    material = incoming_data.get("material_category", "UNKNOWN")
    bin_id = incoming_data.get("assigned_bin_id", "BIN-MISC")
    speed = incoming_data.get("conveyor_speed_fps", 4.5)
    matrix = incoming_data.get("robot_execution_matrix", f"ROTATION_Y: 45deg, SPEED_FACTOR: {speed}")
    
    hmi_msg = f"[ALERT] Batch {batch_id} flagged as {material}. Sending to {bin_id}."
    
    # Keep exact structures intact for downstream dispatch agent mapping
    telemetry_payload = {
        # Schema 1: gke-dispatch-logs
        "gke_dispatch_logs": {
            "batch_id": batch_id,
            "image_gcs_uri": incoming_data.get("image_gcs_uri", f"gs://3r-waste-bucket/item_{batch_id}.jpg"),
            "material_category": material,
            "assigned_bin_id": bin_id,
            "robot_matrix": matrix,
            "hmi_message": hmi_msg,
            "bigquery_commit_success": True 
        },
        # Schema 2: gke-hmi-metrics
        "gke_hmi_metrics": {
            "log_id": incoming_data.get("log_id", f"HMI-{batch_id.split('-')[-1]}"),
            "timestamp": current_timestamp,
            "conveyor_queue_depth": incoming_data.get("conveyor_queue_depth", 1),
            "active_operator_id": incoming_data.get("active_operator_id", "OP-04"),
            "override_triggered": incoming_data.get("override_triggered", False),
            "system_health_score": incoming_data.get("system_health_score", 0.99)
        },
        # Schema 3: gke-robotic-kinematics
        "gke_robotic_kinematics": {
            "item_profile_id": incoming_data.get("item_profile_id", f"P-{material}"),
            "weight_class": incoming_data.get("weight_class", "MEDIUM"),
            "target_bin_id": bin_id,
            "max_extension_cm": incoming_data.get("max_extension_cm", 120),
            "arm_velocity_deg_sec": incoming_data.get("arm_velocity_deg_sec", 150.0),
            "expected_cycle_time_ms": incoming_data.get("expected_cycle_time_ms", 600)
        },
        # Schema 4: gke-segregation-telemetry
        "gke_segregation_telemetry": {
            "batch_id": batch_id,
            "timestamp": current_timestamp,
            "conveyor_speed_fps": speed,
            "weight_grams": incoming_data.get("weight_grams", 150.0),
            "ambient_light_lux": incoming_data.get("ambient_light_lux", 850),
            "camera_temperature_c": incoming_data.get("camera_temperature_c", 34.2)
        }
    }
    
    # Route structured metrics payload down to your BigQuery historical persistence agent
    response = requests.post(DISPATCH_AGENT_URL, json=telemetry_payload).json()
    return response