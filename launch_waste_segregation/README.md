# launch_waste_segregation

## Refer to the codelabs below for installation and process flow

https://codelabs.developers.google.com/adk-mcp-bigquery-maps#0

https://codelabs.developers.google.com/codelabs/production-ready-ai-with-gc/5-deploying-agents/deploy-an-adk-agent-to-cloud-run#0

## Run the setup scripts in the setup folder

1. Run the environment setup script. This script enables the BigQuery and Google Maps APIs, and creates a .env file with your Project ID and Maps API Key.

```
chmod +x setup/setup_env.sh
./setup/setup_env.sh
```

2. Run the BigQuery setup script. This script automates creating the Cloud Storage bucket, uploading data, and provisioning the BigQuery dataset and tables.

```
chmod +x ./setup/setup_bigquery.sh
./setup/setup_bigquery.sh
```

# Deploying on GKE

To build a new Google Kubernetes Engine (GKE) cluster and a container registry to push your Docker builds, it is important to note a key update regarding **`gcr.io` (Google Container Registry)**:

As of **March 2025**, the legacy Google Container Registry was fully shut down and no longer accepts writes. To use the `gcr.io` domain or to follow standard practices, you must utilize **Artifact Registry**, which is Google Cloud's modern successor. Artifact Registry offers full backwards compatibility for `gcr.io` paths if your existing automation requires it, or you can use the modern standard format (`*.pkg.dev`).

Below are the complete setup paths for both a modern registry and a backwards-compatible `gcr.io` repository setup alongside your new GKE cluster.

---

### Step 1: Enable the Necessary APIs

First, ensure that your local environment or Cloud Shell is pointing to your current project and enable both the GKE and Artifact Registry APIs:

```bash
# Set your active project ID
gcloud config set project YOUR_PROJECT_ID

# Enable the required Google Cloud APIs
gcloud services enable container.googleapis.com artifactregistry.googleapis.com

```

---

### Step 2: Create the Container Registry

#### Option A: Standard Modern Registry (Recommended)

This creates a clean, regional Docker repository using the standard `pkg.dev` format.

```bash
# Create a standard Docker repository in a specified region (e.g., us-central1)
gcloud artifacts repositories create project-3r-repo \
    --repository-format=docker \
    --location=us-central1 \
    --description="Docker repository for Project-3R builds"

```

*Your image push path will look like:* `us-central1-docker.pkg.dev/YOUR_PROJECT_ID/my-docker-repo/image-name:tag`

#### Option B: Enable `gcr.io` Backwards Compatibility

If your build tools, scripts, or continuous integration pipelines are strictly hardcoded to use `gcr.io`, you can configure Artifact Registry to intercept and host requests sent to `gcr.io`.

```bash
# Route all traffic for gcr.io paths to look into Artifact Registry instead
gcloud artifacts docker upgrade migrate --projects=YOUR_PROJECT_ID

```

*Your image push path can remain:* `gcr.io/YOUR_PROJECT_ID/image-name:tag`

---

### Step 3: Create your brand new GKE Cluster

Depending on your engineering preferences, you can create either an **Autopilot** cluster (fully managed infrastructure provisioning) or a **Standard** cluster (where you explicitly manage your node virtual machines).

#### Option 1: GKE Autopilot (Recommended for modern, keyless management)

```bash
gcloud container clusters create-auto project-3r-cluster \
    --region us-central1

```

#### Option 2: GKE Standard Cluster

```bash
gcloud container clusters create project-3r-cluster \
    --zone us-central1-a \
    --num-nodes 3 \
    --machine-type e2-standard-4

```

---

### Step 4: Configure Docker Authentication & Push

To push images directly from your local machine or a VM build target, configure your local Docker daemon to securely authenticate with Google Cloud using your `gcloud` credentials:

```bash
# For standard repositories (Option A):
gcloud auth configure-docker us-central1-docker.pkg.dev

# For gcr.io compatible paths (Option B):
gcloud auth configure-docker gcr.io

```

Once authenticated, you can build, tag, and push your images securely:

```bash
# Example using standard modern registry path:
docker build -t us-central1-docker.pkg.dev/YOUR_PROJECT_ID/my-docker-repo/my-app:v1 .
docker push us-central1-docker.pkg.dev/YOUR_PROJECT_ID/my-docker-repo/my-app:v1

```

### Step 5: Connect `kubectl` to your new GKE cluster

Finally, fetch the access credentials so you can deploy your Docker builds to the cluster:

```bash
gcloud container clusters get-credentials project-3r-cluster --region us-central1

```

## Linking the Tables inside Looker Studio

Once your dispatch_agent receives this nested schema payload and updates the 4 tables in the waste_segregation_3r dataset, connect them to your React Looker iframe by following these steps:

1. Open Looker Studio and click Create $\rightarrow$ Data Source.
2. Select the native BigQuery connector.
3. Choose your billing project, select the waste_segregation_3r dataset, and add your tables. You can add them as 4 distinct data sources, or use a Custom Query to join them automatically like this:

```
SELECT 
  dl.batch_id, dl.material_category, dl.assigned_bin_id, dl.hmi_message,
  hm.system_health_score, hm.active_operator_id,
  rk.arm_velocity_deg_sec, rk.expected_cycle_time_ms,
  st.conveyor_speed_fps, st.weight_grams, st.timestamp
FROM `your-project-id.waste_segregation_3r.gke-dispatch-logs` dl
JOIN `your-project-id.waste_segregation_3r.gke-segregation-telemetry` st ON dl.batch_id = st.batch_id
LEFT JOIN `your-project-id.waste_segregation_3r.gke-hmi-metrics` hm ON st.timestamp = hm.timestamp
LEFT JOIN `your-project-id.waste_segregation_3r.gke-robotic-kinematics` rk ON dl.assigned_bin_id = rk.target_bin_id
```


4. Build out your UI widgets (e.g., a timeline tracking system_health_score, or a bar chart of material_category vs weight_grams).
5. Click File $\rightarrow$ Embed report, copy the generated embed URL, and plug it right back into your React front-end component's src parameter!


## Agent Service URLs

SEGREGATION_AGENT_URL: "http://adk-segregation-service:8080/process"
ROBOTIC_ARM_AGENT_URL: "http://adk-robotic-service:8081/process"
HMI_AGENT_URL: "http://adk-hmi-service:8082/process"
DISPATCH_AGENT_URL: "http://adk-dispatch-service:8083/process"
 


