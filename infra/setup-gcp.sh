#!/usr/bin/env bash
# setup-gcp.sh — One-time GCP infrastructure setup for Vantage v2.0
# Target project: supple-moon-495404-b0 | Region: global (us-central1)
# Run: bash infra/setup-gcp.sh

set -euo pipefail

PROJECT="supple-moon-495404-b0"
PROJECT_NUMBER="717874273203"
REGION="us-central1"
BQ_DATASET="vantage"

echo "=== Vantage v2.0 GCP Setup ==="
echo "Project: $PROJECT | Region: $REGION"

gcloud config set project "$PROJECT"

# ── 1. Enable APIs ─────────────────────────────────────────────────────────────
echo ""
echo "--- Enabling APIs ---"

gcloud services enable \
  aiplatform.googleapis.com \
  ml.googleapis.com \
  storage.googleapis.com \
  bigquery.googleapis.com \
  bigquerystorage.googleapis.com \
  firestore.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  cloudtasks.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  cloudtrace.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  redis.googleapis.com \
  vpcaccess.googleapis.com \
  servicenetworking.googleapis.com

echo "APIs enabled."

# ── 2. Service Accounts ────────────────────────────────────────────────────────
echo ""
echo "--- Creating Service Accounts ---"

SA_CLOUDRUN="vantage-cloudrun-sa"
SA_CLOUDBUILD="vantage-cloudbuild-sa"
SA_TASKS="vantage-tasks-sa"
SA_SCHEDULER="vantage-scheduler-sa"

for SA_NAME in "$SA_CLOUDRUN" "$SA_CLOUDBUILD" "$SA_TASKS" "$SA_SCHEDULER"; do
  if ! gcloud iam service-accounts describe "${SA_NAME}@${PROJECT}.iam.gserviceaccount.com" &>/dev/null; then
    gcloud iam service-accounts create "$SA_NAME" \
      --project="$PROJECT" \
      --display-name="Vantage ${SA_NAME}"
    echo "Created: $SA_NAME"
  else
    echo "Exists: $SA_NAME"
  fi
done

# ── 3. IAM Bindings ────────────────────────────────────────────────────────────
echo ""
echo "--- Assigning IAM roles ---"

CLOUDRUN_SA="${SA_CLOUDRUN}@${PROJECT}.iam.gserviceaccount.com"
CLOUDBUILD_SA="${SA_CLOUDBUILD}@${PROJECT}.iam.gserviceaccount.com"
TASKS_SA="${SA_TASKS}@${PROJECT}.iam.gserviceaccount.com"
SCHEDULER_SA="${SA_SCHEDULER}@${PROJECT}.iam.gserviceaccount.com"

# Cloud Run runtime roles
for ROLE in \
  roles/aiplatform.user \
  roles/bigquery.dataEditor \
  roles/bigquery.jobUser \
  roles/datastore.user \
  roles/storage.objectAdmin \
  roles/cloudtasks.enqueuer \
  roles/secretmanager.secretAccessor \
  roles/logging.logWriter \
  roles/cloudtrace.agent; do
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:${CLOUDRUN_SA}" \
    --role="$ROLE" \
    --quiet
done
echo "Cloud Run SA roles assigned."

# Cloud Build roles
for ROLE in \
  roles/run.developer \
  roles/artifactregistry.writer \
  roles/iam.serviceAccountUser \
  roles/storage.objectViewer; do
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:${CLOUDBUILD_SA}" \
    --role="$ROLE" \
    --quiet
done
echo "Cloud Build SA roles assigned."

# Cloud Tasks invoker
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${TASKS_SA}" \
  --role="roles/run.invoker" --quiet

# Cloud Scheduler
for ROLE in roles/cloudtasks.enqueuer roles/run.invoker; do
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:${SCHEDULER_SA}" \
    --role="$ROLE" --quiet
done
echo "Tasks / Scheduler SA roles assigned."

# ── 4. Artifact Registry ───────────────────────────────────────────────────────
echo ""
echo "--- Creating Artifact Registry ---"

if ! gcloud artifacts repositories describe vantage \
    --location="$REGION" --project="$PROJECT" &>/dev/null; then
  gcloud artifacts repositories create vantage \
    --repository-format=docker \
    --location="$REGION" \
    --project="$PROJECT" \
    --description="Vantage AdCopy Agent container images"
  echo "Artifact Registry 'vantage' created."
else
  echo "Artifact Registry 'vantage' already exists."
fi

# ── 5. Cloud Storage Buckets ───────────────────────────────────────────────────
echo ""
echo "--- Creating GCS Buckets ---"

for BUCKET in \
  "vantage-uploads-${PROJECT}" \
  "vantage-failed-ingestion-${PROJECT}"; do
  if ! gsutil ls "gs://${BUCKET}" &>/dev/null; then
    gsutil mb -p "$PROJECT" -l US "gs://${BUCKET}"
    gsutil lifecycle set infra/gcs-lifecycle.json "gs://${BUCKET}" 2>/dev/null || true
    echo "Bucket created: gs://${BUCKET}"
  else
    echo "Bucket exists: gs://${BUCKET}"
  fi
done

# ── 6. BigQuery Dataset and Tables ────────────────────────────────────────────
echo ""
echo "--- Creating BigQuery Dataset and Tables ---"

if ! bq ls --project_id="$PROJECT" "$BQ_DATASET" &>/dev/null; then
  bq --location=US mk --dataset "${PROJECT}:${BQ_DATASET}"
  echo "BigQuery dataset '$BQ_DATASET' created."
fi

# ad_performance_events
bq mk --table --ignore_existing \
  "${PROJECT}:${BQ_DATASET}.ad_performance_events" \
  "brand_id:STRING,platform:STRING,campaign_id:STRING,headline:STRING,\
description:STRING,ctr:FLOAT64,cpc:FLOAT64,roas:FLOAT64,impressions:INTEGER,\
date:DATE,training_run_id:STRING,model_version:STRING,ingested_at:TIMESTAMP"

# generation_audit
bq mk --table --ignore_existing \
  "${PROJECT}:${BQ_DATASET}.generation_audit" \
  "timestamp:TIMESTAMP,brand_id:STRING,user_id:STRING,platform:STRING,\
model:STRING,tokens_in:INTEGER,tokens_out:INTEGER,latency_ms:INTEGER,\
ad_content_hash:STRING,training_run_id:STRING,request_type:STRING"

# training_audit
bq mk --table --ignore_existing \
  "${PROJECT}:${BQ_DATASET}.training_audit" \
  "timestamp:TIMESTAMP,brand_id:STRING,run_id:STRING,mode:STRING,\
section_type:STRING,row_count:INTEGER,quality_score:FLOAT64,status:STRING,\
model_version:STRING"

# safety_events
bq mk --table --ignore_existing \
  "${PROJECT}:${BQ_DATASET}.safety_events" \
  "timestamp:TIMESTAMP,brand_id:STRING,user_id:STRING,category:STRING,\
severity:STRING,content_hash:STRING,blocked:BOOL"

echo "BigQuery tables created."

# ── 7. Cloud Tasks Queue ───────────────────────────────────────────────────────
echo ""
echo "--- Creating Cloud Tasks Queue ---"

if ! gcloud tasks queues describe vantage-ingestion \
    --location="$REGION" --project="$PROJECT" &>/dev/null; then
  gcloud tasks queues create vantage-ingestion \
    --location="$REGION" \
    --project="$PROJECT" \
    --max-dispatches-per-second=10 \
    --max-concurrent-dispatches=20 \
    --max-attempts=5 \
    --min-backoff=10s \
    --max-backoff=300s
  echo "Cloud Tasks queue 'vantage-ingestion' created."
fi

# ── 8. Secret Manager — placeholder secrets ────────────────────────────────────
echo ""
echo "--- Creating Secret Manager secrets (placeholders) ---"

for SECRET_ID in \
  "vantage-jwt-secret-key" \
  "vantage-google-places-api-key" \
  "vantage-google-custom-search-api-key" \
  "vantage-google-custom-search-cx" \
  "vantage-firebase-service-account"; do
  if ! gcloud secrets describe "$SECRET_ID" \
      --project="$PROJECT" &>/dev/null; then
    echo "PLACEHOLDER_REPLACE_ME" | gcloud secrets create "$SECRET_ID" \
      --project="$PROJECT" \
      --data-file=-
    echo "Secret created: $SECRET_ID"
  else
    echo "Secret exists: $SECRET_ID"
  fi
done

echo ""
echo "=== Setup complete! ==="
echo ""
echo "NEXT STEPS:"
echo "1. Replace placeholder secrets:"
echo "   gcloud secrets versions add vantage-jwt-secret-key --data-file=- <<< 'YOUR_JWT_SECRET'"
echo "   gcloud secrets versions add vantage-google-places-api-key --data-file=- <<< 'YOUR_KEY'"
echo "   gcloud secrets versions add vantage-google-custom-search-api-key --data-file=- <<< 'YOUR_KEY'"
echo "   gcloud secrets versions add vantage-google-custom-search-cx --data-file=- <<< 'YOUR_CX'"
echo "   gcloud secrets versions add vantage-firebase-service-account --data-file=firebase-service-account.json"
echo ""
echo "2. Create Vertex AI Vector Search index (in GCP Console or via gcloud)"
echo "   Location: us-central1"
echo ""
echo "3. Create Memorystore Redis instance:"
echo "   gcloud redis instances create vantage-cache --size=1 --region=$REGION --tier=BASIC"
echo ""
echo "4. Trigger Cloud Build:"
echo "   gcloud builds submit --project=$PROJECT --config=cloudbuild.yaml ."
