To comply with your security policy banning raw API keys, you should shift authentication to **Application Default Credentials (ADC)** via **GKE Workload Identity Federation** (formerly Workload Identity).

This approach completely removes the need for `project-3r-secrets` containing strings like `GEMINI_API_KEY`. Instead, your Segregation Agent container automatically inherits credentials implicitly via the Google SDK when initialized.

Here is the fast-track conversion setup to switch to ADC:

### Step 1: Bind your GKE Service Account to GCP IAM Roles

Run these three quick `gcloud` commands in Cloud Shell to authorize your GKE pod natively via Workload Identity:

```bash
# 1. Create a dedicated Google IAM Service Account (GSA)
gcloud iam service-accounts create project-3r-gke-sa --display-name="Project 3R GKE Agent Service Account"

# 2. Grant it access to Vertex AI (Gemini), BigQuery, and GCS
gcloud projects add-iam-policy-binding your-gcp-project-id \
    --member="serviceAccount:project-3r-gke-sa@your-gcp-project-id.iam.gserviceaccount.com" \
    --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding your-gcp-project-id \
    --member="serviceAccount:project-3r-gke-sa@your-gcp-project-id.iam.gserviceaccount.com" \
    --role="roles/bigquery.dataEditor"

# 3. Allow your Kubernetes Service Account (KSA) to impersonate the GSA
gcloud iam service-accounts add-iam-policy-binding project-3r-gke-sa@your-gcp-project-id.iam.gserviceaccount.com \
    --role="roles/iam.workloadIdentityUser" \
    --member="serviceAccount:your-gcp-project-id.svc.id.goog[default/project-3r-ksa]"

```
## Consider below commands to handle permission related issues

# 1. Grant permissions to submit builds
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="user:<your_email>" \
    --role="roles/cloudbuild.builds.editor"

# 2. Grant permissions to stage the source context in the Cloud Build default bucket
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="user:<your_email>" \
    --role="roles/storage.admin"
---

Note: Replace YOUR_PROJECT_ID with your real Google Cloud Project ID.

Verify Service Accounts (If you recently enabled Cloud Build)
If your project is brand new, the Cloud Build Service Account itself might not have initialized its default bindings yet. Ensure the Cloud Build service account has permission to write to your Artifact Registry:


# Get your project number
PROJECT_NUMBER=$(gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)")

# Grant the Cloud Build service account permission to push images into Artifact Registry
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
    --role="roles/artifactregistry.writer"

## For persistent errors consider below commands
The error occurs because Cloud Build uses a service account to fetch your uploaded source code from the staging storage bucket (`gs://my-gen-ai-sandbox-project1_cloudbuild`), and that specific service account lacks permissions to read from the bucket.

In Google Cloud, Cloud Build can execute using either the legacy Compute Engine default service account (`[PROJECT_NUMBER]-compute@developer.gserviceaccount.com`) or the modern dedicated Cloud Build service account, depending on your project configuration. The error explicitly shows that `659952133659-compute@developer.gserviceaccount.com` is being denied access.

### The Fix

You can grant the required permissions directly using Cloud Shell. Execute the following commands to give the service account permission to read objects from your Cloud Build bucket:

```bash
# Define project variables
PROJECT_ID="my-gen-ai-sandbox-project1"
SERVICE_ACCOUNT="659952133659-compute@developer.gserviceaccount.com"
BUCKET_NAME="my-gen-ai-sandbox-project1_cloudbuild"

# Grant Storage Object Viewer permission on the specific bucket
gcloud storage buckets add-iam-policy-binding gs://$BUCKET_NAME \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/storage.objectViewer"

```

OR

# 1. Set the variables in your terminal first
PROJECT_ID=$(gcloud config get-value project)
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
SA_NAME=lab2-cr-service

# 2. Create the .env file using those variables
cat <<EOF > .env
PROJECT_ID=$PROJECT_ID
PROJECT_NUMBER=$PROJECT_NUMBER
SA_NAME=$SA_NAME
SERVICE_ACCOUNT=${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com
MODEL="gemini-2.5-flash"
EOF

### Alternative / Best Practice Recommendation

If you are running builds using the default Compute Engine service account, it often indicates Cloud Build is missing its default wider permissions or is using an older defaults layout. You can explicitly ensure it has standard Cloud Build execution capability on the project level by running:

```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/cloudbuild.builds.builder"

```

Once you apply the IAM bindings, wait about 10–15 seconds for the permissions to propagate globally, then re-run your build command:

```bash
gcloud builds submit --tag us-central1-docker.pkg.dev/my-gen-ai-sandbox-project1/project-3r-repo/orchestrator:latest .

```


### Step 2: The Security-Compliant YAML (`project-3r-adc.yaml`)

This updated manifest provisions a Kubernetes Service Account (`project-3r-ksa`) linked natively to Google Cloud's ADC engine. It securely drops the raw `Secret` object completely:

```yaml
---

## Enable necessary APIs

# Ensure your project is set correctly
PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
echo "Enabling APIs for Project: $PROJECT_ID"

# Enable Google Kubernetes Engine (GKE) and Artifact Registry
gcloud services enable container.googleapis.com --project=$PROJECT_ID
gcloud services enable artifactregistry.googleapis.com --project=$PROJECT_ID

# Enable Vertex AI / AI Platform and API Keys Management
gcloud services enable aiplatform.googleapis.com --project=$PROJECT_ID
gcloud services enable apikeys.googleapis.com --project=$PROJECT_ID

# Enable BigQuery and Location/Maps Platforms
gcloud services enable bigquery.googleapis.com --project=$PROJECT_ID
gcloud services enable mapstools.googleapis.com --project=$PROJECT_ID
# ==============================================================================
# KUBERNETES SERVICE ACCOUNT (WORKLOAD IDENTITY / ADC LINK)
# ==============================================================================
apiVersion: v1
kind: ServiceAccount
metadata:
  name: project-3r-ksa
  namespace: default
  annotations:
    # This annotation maps your pod directly to the secure GCP IAM Service account
    iam.gke.io/gcp-service-account: "project-3r-gke-sa@your-gcp-project-id.iam.gserviceaccount.com"
---
# ==============================================================================
# CONFIGMAP (Environment Targets Only)
# ==============================================================================
apiVersion: v1
kind: ConfigMap
metadata:
  name: project-3r-config
data:
  GCP_PROJECT_ID: "your-gcp-project-id"
  GCS_WASTE_BUCKET: "your-3r-waste-bucket"
  BQ_DATASET: "waste_analytics"
  BQ_TELEMETRY_TABLE: "gke_segregation_telemetry"
  SEGREGATION_AGENT_URL: "http://adk-segregation-service:8080/process"
  ROBOTIC_ARM_AGENT_URL: "http://adk-robotic-service:8081/process"
  HMI_AGENT_URL: "http://adk-hmi-service:8082/process"
  DISPATCH_AGENT_URL: "http://adk-dispatch-service:8083/process"

---
# ==============================================================================
# 1. SEGREGATION AGENT (Port 8080 - Now Using Native ADC Engine)
# ==============================================================================
apiVersion: apps/v1
kind: Deployment
metadata:
  name: segregation-agent
spec:
  replicas: 1
  selector:
    matchLabels:
      app: segregation-agent
  template:
    metadata:
      labels:
        app: segregation-agent
    spec:
      serviceAccountName: project-3r-ksa # Instructs pod to assume Workload Identity metadata
      containers:
      - name: agent
        image: gcr.io/your-gcp-project-id/segregation-agent:latest
        ports:
        - containerPort: 8080
        envFrom:
        - configMapRef:
            name: project-3r-config
        # Note: NO Secret reference or GEMINI_API_KEY environment variable injected here!
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
---
apiVersion: v1
kind: Service
metadata:
  name: segregation-service
spec:
  type: ClusterIP
  selector:
    app: segregation-agent
  ports:
  - port: 8080
    targetPort: 8080

---
# ==============================================================================
# 2. ROBOTIC ARM AGENT (Port 8081)
# ==============================================================================
apiVersion: apps/v1
kind: Deployment
metadata:
  name: robotic-arm-agent
spec:
  replicas: 1
  selector:
    matchLabels:
      app: robotic-arm-agent
  template:
    metadata:
      labels:
        app: robotic-arm-agent
    spec:
      serviceAccountName: project-3r-ksa
      containers:
      - name: agent
        image: gcr.io/your-gcp-project-id/robotic-arm-agent:latest
        ports:
        - containerPort: 8081
        envFrom:
        - configMapRef:
            name: project-3r-config
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
---
apiVersion: v1
kind: Service
metadata:
  name: robotic-arm-service
spec:
  type: ClusterIP
  selector:
    app: robotic-arm-agent
  ports:
  - port: 8081
    targetPort: 8081

---
# ==============================================================================
# 3. SMART HMI AGENT (Port 8082)
# ==============================================================================
apiVersion: apps/v1
kind: Deployment
metadata:
  name: smart-hmi-agent
spec:
  replicas: 1
  selector:
    matchLabels:
      app: smart-hmi-agent
  template:
    metadata:
      labels:
        app: smart-hmi-agent
    spec:
      serviceAccountName: project-3r-ksa
      containers:
      - name: agent
        image: gcr.io/your-gcp-project-id/smart-hmi-agent:latest
        ports:
        - containerPort: 8082
        envFrom:
        - configMapRef:
            name: project-3r-config
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
---
apiVersion: v1
kind: Service
metadata:
  name: smart-hmi-service
spec:
  type: ClusterIP
  selector:
    app: smart-hmi-agent
  ports:
  - port: 8082
    targetPort: 8082

---
# ==============================================================================
# 4. REVIEW & DISPATCH AGENT (Port 8083)
# ==============================================================================
apiVersion: apps/v1
kind: Deployment
metadata:
  name: review-dispatch-agent
spec:
  replicas: 1
  selector:
    matchLabels:
      app: review-dispatch-agent
  template:
    metadata:
      labels:
        app: review-dispatch-agent
    spec:
      serviceAccountName: project-3r-ksa
      containers:
      - name: agent
        image: gcr.io/your-gcp-project-id/review-dispatch-agent:latest
        ports:
        - containerPort: 8083
        envFrom:
        - configMapRef:
            name: project-3r-config
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
---
apiVersion: v1
kind: Service
metadata:
  name: review-dispatch-service
spec:
  type: ClusterIP
  selector:
    app: review-dispatch-agent
  ports:
  - port: 8083
    targetPort: 8083

```

---

### Step 3: Code Verification for the Segregation Agent

When using ADC, you initialization pattern inside `adk_segregation_app/agent.py` simplifies. The new `google-genai` SDK natively sweeps the container environment for Workload Identity tokens when instantiated cleanly without parameters:

```python
from google import genai
from google.genai import types

# Initialize client using ADC
ai_client = genai.Client()

# Construct the Part referencing your Cloud Storage URI directly
# Replace this with your actual GCS bucket variable or dynamic incoming payload
gcs_image_uri = "gs://your-3r-waste-bucket/sample_conveyor_clip.jpg"

image_part = types.Part.from_uri(
    file_uri=gcs_image_uri,
    mime_type="image/jpeg"  # or image/png depending on your file type
)

# Pass it directly to Gemini
response = ai_client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[
        image_part,
        "Analyze this item on the waste segregation conveyor belt and output standard JSON routing data."
    ]
)

print(response.text)

```

Apply this manifest using `kubectl apply -f project-3r-adc.yaml`. Your cluster is now fully compliant with your team's keyless security configuration.


### Step 3
Based on your architecture and the target corporate Artifact Registry layout (`us-central1-docker.pkg.dev/your-gcp-project-id/my-docker-repo/`), you can use Google Cloud Build to compile and push your containers securely via Cloud Shell.

For each application, navigate to its corresponding directory in Cloud Shell and run the respective `gcloud builds submit` command (ensuring the trailing `.` is included to pass the current directory context):

### 1. Segregation Agent

* **Directory:** `adk_segregation_app/`
* **Command:**
```bash
gcloud builds submit --tag us-central1-docker.pkg.dev/your-gcp-project-id/my-docker-repo/segregation-agent:latest .

```



### 2. Robotic Arm Agent

* **Directory:** `adk_robotic_arm_app/`
* **Command:**
```bash
gcloud builds submit --tag us-central1-docker.pkg.dev/your-gcp-project-id/my-docker-repo/robotic-arm-agent:latest .

```



### 3. Smart HMI Agent

* **Directory:** `adk_smart_hmi_app/`
* **Command:**
```bash
gcloud builds submit --tag us-central1-docker.pkg.dev/your-gcp-project-id/my-docker-repo/smart-hmi-agent:latest .

```



### 4. Dispatch Agent

* **Directory:** `adk_dispatch_app/`
* **Command:**
```bash
gcloud builds submit --tag us-central1-docker.pkg.dev/your-gcp-project-id/my-docker-repo/dispatch-agent:latest .

```



### 5. Orchestrator Agent

* **Directory:** `adk_orchestrator_app/`
* **Command:**
```bash
gcloud builds submit --tag us-central1-docker.pkg.dev/your-gcp-project-id/my-docker-repo/orchestrator-agent:latest .

```



### 6. React Frontend UI

If your project uses a custom Dockerfile configuration name (such as `frontend.Dockerfile`) inside your React root directory, explicitly point Cloud Build to it using the `--config` flag:

* **Directory:** Your React project root directory
* **Command:**
```bash
gcloud builds submit --config frontend.Dockerfile --tag us-central1-docker.pkg.dev/your-gcp-project-id/my-docker-repo/react-frontend-ui:latest .

```



*(Note: Replace `your-gcp-project-id` with your actual Google Cloud Project ID and change the `us-central1` or `my-docker-repo` naming parts if your regional configurations or repository names differ).*
