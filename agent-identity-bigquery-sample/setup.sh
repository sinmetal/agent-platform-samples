#!/usr/bin/env bash
# Setup for the Agent Identity 3LO BigQuery sample.
# Fill in the values below for your own environment before running.
# Run the steps one block at a time and read the comments — some steps depend on
# the output of `deploy.py` (the agent's Engine ID / principal).
set -euo pipefail

# ---- Fill these in for your environment ----
export PROJECT_ID=your-project-id
export PROJECT_NUMBER=YOUR_PROJECT_NUMBER
export ORG_ID=YOUR_ORG_ID
export LOCATION=us-central1
export CONNECTOR_NAME=bigquery-3lo
export STAGING_BUCKET=gs://your-project-id-agent-staging

# You fill these in after creating the OAuth client (step 3).
export OAUTH_CLIENT_ID="REPLACE_ME"
export OAUTH_CLIENT_SECRET="REPLACE_ME"

# The agent principalSet (all agents in the project) and, after deploy, the
# single agent principal.
AGENT_PRINCIPAL_SET="principalSet://agents.global.org-${ORG_ID}.system.id.goog/attribute.platformContainer/aiplatform/projects/${PROJECT_NUMBER}"
# After deploy.py prints the Engine ID, set ENGINE_ID and use AGENT_PRINCIPAL.
export ENGINE_ID="REPLACE_AFTER_DEPLOY"
AGENT_PRINCIPAL="principal://agents.global.org-${ORG_ID}.system.id.goog/resources/aiplatform/projects/${PROJECT_NUMBER}/locations/${LOCATION}/reasoningEngines/${ENGINE_ID}"

# ============================================================
# Step 1: Enable APIs
# ============================================================
gcloud services enable \
  aiplatform.googleapis.com \
  iamconnectors.googleapis.com \
  iamconnectorcredentials.googleapis.com \
  bigquery.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project="${PROJECT_ID}"

# ============================================================
# Step 2: Create the staging bucket (for Agent Runtime deploy)
# ============================================================
gcloud storage buckets create "${STAGING_BUCKET}" \
  --project="${PROJECT_ID}" --location="${LOCATION}" || true

# ============================================================
# Step 3: Create an OAuth 2.0 client (do this in the Console)
# ============================================================
# Console > APIs & Services > Credentials > Create credentials > OAuth client ID
#   Application type: Web application
#   Authorized redirect URI (exactly this):
#   https://iamconnectorcredentials.googleapis.com/v1/projects/${PROJECT_ID}/locations/${LOCATION}/connectors/${CONNECTOR_NAME}/oauthcallback
# Then copy the Client ID / Secret into OAUTH_CLIENT_ID / OAUTH_CLIENT_SECRET above.
echo "Redirect URI to register on the OAuth client:"
echo "https://iamconnectorcredentials.googleapis.com/v1/projects/${PROJECT_ID}/locations/${LOCATION}/connectors/${CONNECTOR_NAME}/oauthcallback"

# ============================================================
# Step 4: Create the 3LO connector (auth provider)
# ============================================================
gcloud alpha agent-identity connectors create "${CONNECTOR_NAME}" \
  --project="${PROJECT_ID}" \
  --location="${LOCATION}" \
  --three-legged-oauth-client-id="${OAUTH_CLIENT_ID}" \
  --three-legged-oauth-client-secret="${OAUTH_CLIENT_SECRET}" \
  --three-legged-oauth-authorization-url="https://accounts.google.com/o/oauth2/v2/auth" \
  --three-legged-oauth-token-url="https://oauth2.googleapis.com/token" \
  --allowed-scopes="https://www.googleapis.com/auth/bigquery"

# ============================================================
# Step 5: Deploy the agent (gets the Engine ID + identity)
# ============================================================
# Run from the sample root:
#   python deploy.py
# Copy the printed Engine ID into ENGINE_ID above and re-source this file.

# ============================================================
# Step 6: Grant the agent permission to USE the connector
# ============================================================
gcloud alpha agent-identity connectors add-iam-policy-binding "${CONNECTOR_NAME}" \
  --project="${PROJECT_ID}" \
  --location="${LOCATION}" \
  --role="roles/iamconnectors.user" \
  --member="${AGENT_PRINCIPAL}"

# ============================================================
# Step 7: Let the agent use the project (Service Usage)
# ============================================================
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="${AGENT_PRINCIPAL_SET}" \
  --role="roles/serviceusage.serviceUsageConsumer"

echo "Setup commands complete. Run the frontend in client/ to test (see README)."
