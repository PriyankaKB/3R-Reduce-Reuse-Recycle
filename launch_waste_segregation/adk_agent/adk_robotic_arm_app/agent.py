import os
import dotenv
import requests
from adk_robotic_arm_app import tools
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from google.adk.agents import LlmAgent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from a2a.types import Message, AgentCard

dotenv.load_dotenv()
PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT', 'project_not_set')

# Internal GKE DNS URLs for pipeline orchestration
HMI_AGENT_URL = os.getenv("HMI_AGENT_URL", "http://adk-hmi-service:8082/process")
SEGREGATION_AGENT_URL = os.getenv("SEGREGATION_AGENT_URL", "http://adk-segregation-service:8080/process")

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

# 1. Define Agent Cards for downstream/collaborating agents
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

segregation_card = AgentCard(
    name="segregation_agent",
    description="Handles material sorting validation and physical segregation pipeline tracking.",
    defaultInputModes=["application/json"],
    defaultOutputModes=["application/json"],
    skills=[{"id": "validate_sorting", "name": "validate_sorting", "description": "Validates bin assignments.", "tags": ["sorting"]}],
    url=SEGREGATION_AGENT_URL,
    capabilities={},
    version="1.0.0"
)

# 2. Setup the Remote A2A instances
smart_hmi_agent = RemoteA2aAgent(
    name="smart_hmi_agent",
    description="Agent handling downstream dashboard updates and user messages.",
    agent_card=hmi_card
)

segregation_agent = RemoteA2aAgent(
    name="segregation_agent",
    description="Agent handling physical material segregation updates.",
    agent_card=segregation_card
)

maps_toolset = tools.get_maps_mcp_toolset()
bigquery_toolset = tools.get_bigquery_mcp_toolset()

# 3. Define the Robot Agent itself
root_agent = LlmAgent(
    model='gemini-2.5-flash',
    name='robotic_arm_agent',
    description="Calculates conveyor sort locations and physics trajectory coordinates.",
    instruction=f"""
        Evaluate the material category and conveyor speed given. 
        1.  **BigQuery toolset:** Access recyclable_materials_data, recycle_bin_id_matrix and dustbin_color_codes in the waste_segregation_3r dataset. Do not use any other dataset.
        Run all query jobs from project id: {PROJECT_ID}.

        2.  **Maps Toolset:** Use this for real-world location analysis, finding competition/places and calculating necessary travel routes.
        Include a hyperlink to an interactive map in your response where appropriate.

        Calculate the appropriate physical BIN assignment by referring to recyclable_materials_data:
        Output JSON mapping and hand off the task to the sub-agents.
    """,
    tools=[maps_toolset, bigquery_toolset],
    sub_agents=[smart_hmi_agent, segregation_agent]
)

# Expose its own Agent Card for discovery
@app.get("/.well-known/agent.json")
async def get_card():
    return {
        "name": "robotic_arm_agent",
        "description": "Calculates kinematics and assigns physical sort bin mappings.",
        "url": os.getenv("ROBOTIC_ARM_AGENT_URL", "http://adk-robotic-service:8081/process"),
        "version": "1.0.0"
    }

@app.post("/process")
async def process(request: Request):
    data = await request.json()
    
    # Process the kinematics
    material = data.get("material_category", "UNKNOWN")
    speed = data.get("conveyor_speed_fps", 4.5)
    
    # Keeping your explicit BigQuery baseline mappings intact
    bin_map = {"PLASTIC": "BIN-00", "FOAM": "BIN-01", "GLASS": "BIN-02", "PAPER": "BIN-10", "METAL": "BIN-11", "TEXTILE": "BIN-12"}
    assigned_bin = bin_map.get(material, "BIN-MISC")
    
    # Enrich the payload state
    data["assigned_bin_id"] = assigned_bin
    data["robot_execution_matrix"] = f"ROTATION_Y: 45deg, SPEED_FACTOR: {speed}"
    
    # 1. Interact with Segregation Agent to process sorting updates
    try:
        segregation_response = requests.post(SEGREGATION_AGENT_URL, json=data).json()
        # Optionally merge any new state data from the segregation step
        if isinstance(segregation_response, dict):
            data.update(segregation_response)
    except Exception as e:
        # Fallback logging if service is down, maintaining pipeline resilience
        data["segregation_error"] = str(e)

    # 2. Cascade final state forward to the HMI Agent for UI/Dashboard tracking
    hmi_response = requests.post(HMI_AGENT_URL, json=data).json()
    
    return hmi_response