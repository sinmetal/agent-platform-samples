# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Deploys the BigQuery agent to the Gemini Enterprise Agent Platform / Agent
Runtime with Agent Identity enabled.

Run:
    export GOOGLE_CLOUD_PROJECT=your-project-id
    export GOOGLE_CLOUD_LOCATION=us-central1
    export STAGING_BUCKET=gs://your-project-id-agent-staging
    python deploy.py

After deploy, this prints the reasoningEngine resource name and the agent's
effective identity (principal://...). Use that principal to grant the connector
binding in README.md step 6.
"""

import os

import vertexai
from vertexai import types
from vertexai.agent_engines import AdkApp

from agent import root_agent

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "your-project-id")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
STAGING_BUCKET = os.environ.get(
    "STAGING_BUCKET", "gs://your-project-id-agent-staging"
)

# v1beta1 is required for Agent Identity (identity_type) support.
client = vertexai.Client(
    project=PROJECT_ID,
    location=LOCATION,
    http_options=dict(api_version="v1beta1"),
)

app = AdkApp(agent=root_agent)

remote_app = client.agent_engines.create(
    agent=app,
    config={
        "display_name": "agent-identity-bigquery",
        # Give the deployed agent its own per-agent identity.
        "identity_type": types.IdentityType.AGENT_IDENTITY,
        "requirements": [
            "google-cloud-aiplatform[agent_engines,adk]",
            "google-adk[agent-identity]",
            "httpx",
        ],
        # Upload agent.py so the runtime can import the `agent` module that the
        # pickled tool functions reference.
        "extra_packages": ["agent.py"],
        "staging_bucket": STAGING_BUCKET,
    },
)

resource_name = remote_app.api_resource.name
print("=" * 72)
print(f"Deployed: {resource_name}")
print(f"Engine ID: {resource_name.split('/')[-1]}")
try:
  print(f"Effective identity: {remote_app.api_resource.spec.effective_identity}")
except Exception as e:  # pylint: disable=broad-except
  print(f"(could not read effective_identity: {e})")
print("=" * 72)
print(
    "Next: grant this principal roles/iamconnectors.user on the bigquery-3lo"
    " connector (README.md step 6)."
)
