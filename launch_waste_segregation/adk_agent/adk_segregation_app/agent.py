import os
import requests
import dotenv
from adk_segregation_app import tools
from typing import Literal
from google import genai
from pydantic import BaseModel, Field
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from google.adk.agents import LlmAgent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from a2a.types import Message, AgentCard
from google.genai import types

# NVIDIA RAPIDS zero-code drop-in acceleration layer
import cudf.pandas
cudf.pandas.install()
import pandas as pd

dotenv.load_dotenv()
PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT', 'my-gen-ai-sandbox-project1')

# Fetch downstream cluster internal CoreDNS URLs
ROBOTIC_ARM_AGENT_URL = os.getenv("ROBOTIC_ARM_AGENT_URL", "http://adk-robotic-service:8081/process")
HMI_AGENT_URL = os.getenv("HMI_AGENT_URL", "http://adk-hmi-service:8082/process")

# This will automatically pick up your GEMINI_API_KEY from your .env file
ai_client = genai.Client()

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

# Register downstream agent capability matrix using your card layout
robotic_card = AgentCard(
    name="robotic_arm_agent",
    description="Calculates kinematics and assigns physical sort bin mappings.",
    defaultInputModes=["application/json"],
    defaultOutputModes=["application/json"],
    skills=[{"id": "arm_sort", "name": "arm_sort", "description": "Kinematics bin destination routing", "tags": ["robotics"]}],
    url=ROBOTIC_ARM_AGENT_URL,
    capabilities={},
    version="1.0.0"
)

robotic_arm_agent = RemoteA2aAgent(
    name="robotic_arm_agent",
    description="Agent handling path planning and sorting commands.",
    agent_card=robotic_card
)

# New interaction definition: Define the Smart HMI Agent's capability card
hmi_card = AgentCard(
    name="smart_hmi_agent",
    description="Formulates real-time notification streams and diagnostic telemetry displays.",
    defaultInputModes=["application/json"],
    defaultOutputModes=["application/json"],
    skills=[{"id": "hmi_alert", "name": "hmi_alert", "description": "Formulates UI status updates", "tags": ["ui"]}],
    url=HMI_AGENT_URL,
    capabilities={},
    version="1.0.0"
)

smart_hmi_agent = RemoteA2aAgent(
    name="smart_hmi_agent",
    description="Agent handling UI/UX status reporting and operations dashboards.",
    agent_card=hmi_card
)

maps_toolset = tools.get_maps_mcp_toolset()
bigquery_toolset = tools.get_bigquery_mcp_toolset()

# Instantiate Root Agent using Gemini backend
root_agent = LlmAgent(
    model='gemini-2.5-flash',
    name='segregation_agent',
    description="Classifies conveyor items via GCS URIs and dispatches work downstream.",
    instruction=f"""Analyze raw images from Cloud Storage buckets. Categorize items into exactly: PAPER, GLASS, FOAM, METAL, PLASTIC, TEXTILE.
                    1.  **BigQuery toolset:** Access waste_categories_data, recyclable_materials_data, plastic_segregation_data, foam_segregation_data, and dustbin_color_codes in the waste_segregation_3r dataset. Do not use any other dataset.
                Run all query jobs from project id: {PROJECT_ID}. 

                    2.  **Maps Toolset:** Use this for real-world location analysis, finding competition/places and calculating necessary travel routes.
                    Include a hyperlink to an interactive map in your response where appropriate.
                """,
    # Added both downstream sub-agents to allow seamless context delegation
    tools=[maps_toolset, bigquery_toolset],
    sub_agents=[robotic_arm_agent, smart_hmi_agent]

)

class WasteClassification(BaseModel):
    category: Literal["PLASTIC", "FOAM", "METAL", "GLASS", "PAPER", "TEXTILE"] = Field(
        description="The normalized uppercase waste sorting category matching the physical 2x3 grid."
    )

@app.post("/process")
async def process(request: Request):
    data = await request.json()
    batch_id = data.get("batch_id", "B-000")
    image_path = data.get("image_path", "data/box-packed-with-styrofoam.jpg") 
    sensor_log_path = data.get("sensor_log_path", "data/gke-segregation-telemetry.csv")

    # A. Local GPU Accelerated operation via cuDF
    if os.path.exists(sensor_log_path):
        gdf = pd.read_csv(sensor_log_path)
        conveyor_speed = float(gdf['conveyor_speed_fps'].mean())
    else:
        conveyor_speed = 4.5

    # B. Real Live Gemini Vision Execution
    detected_category = "PLASTIC" # Robust production safety fallback default
    
    try:
        if os.path.exists(image_path):
            # Load the image binary data securely
            with open(image_path, "rb") as f:
                image_bytes = f.read()
                
            # FIX: Define image_part clearly using the correct SDK types constructor
            image_part = types.Part.from_bytes(
                data=image_bytes,
                mime_type="image/jpeg"
            )
            
            # Trigger context prediction using the defined ai_client and image_part
            response = ai_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[
                    image_part, 
                    "Identify the dominant category from the predefined classification types matching the grid system."
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=WasteClassification,
                    temperature=0.0 # Force deterministic output mapping
                ),
            )
            
            structured_output = WasteClassification.model_validate_json(response.text)
            detected_category = structured_output.category
        else:
            print(f"[Warning] Image path not found at {image_path}. Using fallback classification.")
            
    except Exception as e:
        print(f"[Gemini Exception] Error analyzing stream image: {str(e)}")

    # C. Compile the exact cross-agent state payload object
    pipeline_payload = {
        "batch_id": batch_id,
        "image_source": image_path,
        "material_category": detected_category,     # Handed directly from real Gemini execution output
        "conveyor_speed_fps": conveyor_speed        # Evaluated via NVIDIA local RAPIDS hardware
    }

    print(f"[Segregation Node] Resolved category: {detected_category} at speed: {conveyor_speed} FPS")

    # D. Forward state down the A2A chain over GKE network bounds
    try:
        response_from_arm = requests.post(ROBOTIC_ARM_AGENT_URL, json=pipeline_payload).json()
        return response_from_arm
    except Exception as e:
        return {
            "status": "NETWORK_ROUTING_ERROR", 
            "details": str(e), 
            "local_processed_state": pipeline_payload
        }