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

"""Agent Identity (3-legged OAuth) sample that queries BigQuery on behalf of the end user.

This agent does NOT use a service account or its own machine identity to read
BigQuery. Instead it uses the Agent Identity 3LO connector to obtain the END
USER's Google OAuth token, then calls the BigQuery REST API with that token.
Every query therefore runs with the consented user's own IAM permissions and is
attributed to that user in BigQuery audit logs.

See:
  - https://docs.cloud.google.com/iam/docs/auth-with-3lo
  - https://docs.cloud.google.com/iam/docs/agent-identity-overview
"""

from __future__ import annotations

import os

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.auth.auth_credential import AuthCredential
from google.adk.auth.auth_tool import AuthConfig
from google.adk.auth.credential_manager import CredentialManager
from google.adk.integrations.agent_identity import GcpAuthProvider
from google.adk.integrations.agent_identity import GcpAuthProviderScheme
from google.adk.tools.authenticated_function_tool import AuthenticatedFunctionTool
import httpx

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "your-project-id")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

# Name of the 3LO connector (auth provider) you create with
# `gcloud alpha agent-identity connectors create`. See README.md step 4.
BIGQUERY_3LO_AUTH_PROVIDER_ID = os.environ.get(
    "BIGQUERY_3LO_AUTH_PROVIDER_ID", "bigquery-3lo"
)
BIGQUERY_3LO_AUTH_PROVIDER = (
    f"projects/{PROJECT_ID}/locations/{LOCATION}/connectors/"
    f"{BIGQUERY_3LO_AUTH_PROVIDER_ID}"
)

# Where the OAuth consent flow redirects once the user has granted consent.
# This must point at the local frontend (client/main.py) /commit endpoint and
# must match a URL the frontend serves. Use `localhost`, not 127.0.0.1.
CONTINUE_URI = os.environ.get("CONTINUE_URI", "http://localhost:8080/commit")

# OAuth scope the user consents to. BigQuery read/write needs the bigquery
# scope; use bigquery.readonly if you only ever SELECT.
BIGQUERY_SCOPE = os.environ.get(
    "BIGQUERY_SCOPE", "https://www.googleapis.com/auth/bigquery"
)

MODEL = "gemini-2.5-flash"


async def bigquery_query(credential: AuthCredential, sql: str) -> str | list:
  """Runs a Standard SQL query against BigQuery as the consented end user.

  The query is executed with the end user's own OAuth token (obtained via the
  Agent Identity 3LO connector), so it only succeeds for data the user is
  allowed to read, and the BigQuery job is billed to and audited under
  PROJECT_ID.

  Args:
    credential: Injected by ADK; carries the end user's bearer token.
    sql: A BigQuery Standard SQL query to run.

  Returns:
    A list of result rows (each a dict of column -> value), or an error string.
  """
  token = None
  if (http := credential.http) and http.credentials:
    token = http.credentials.token

  if not token:
    return "Error: No authentication token available."

  # jobs.query runs short queries synchronously and returns rows inline.
  url = (
      "https://bigquery.googleapis.com/bigquery/v2/projects/"
      f"{PROJECT_ID}/queries"
  )
  headers = {
      "Authorization": f"Bearer {token}",
      "Content-Type": "application/json",
  }
  body = {
      "query": sql,
      "useLegacySql": False,
      "maxResults": 50,
      # Run the job in PROJECT_ID's billing context, as the end user.
      "location": LOCATION,
  }

  async with httpx.AsyncClient(timeout=60.0) as client:
    response = await client.post(url, headers=headers, json=body)

  if response.status_code != 200:
    return f"Error from BigQuery API: {response.status_code} - {response.text}"

  data = response.json()
  field_names = [f["name"] for f in data.get("schema", {}).get("fields", [])]
  rows = []
  for row in data.get("rows", []):
    values = [cell.get("v") for cell in row.get("f", [])]
    rows.append(dict(zip(field_names, values)))

  if not rows:
    return "Query succeeded but returned no rows."
  return rows


# Configure the 3LO auth provider scheme: ADK will run the interactive consent
# flow (via the frontend's continue_uri) and inject the user's token into
# `credential` when calling bigquery_query.
bigquery_auth_config_3lo = AuthConfig(
    auth_scheme=GcpAuthProviderScheme(
        name=BIGQUERY_3LO_AUTH_PROVIDER,
        scopes=[BIGQUERY_SCOPE],
        continue_uri=CONTINUE_URI,
    )
)
bigquery_tool = AuthenticatedFunctionTool(
    func=bigquery_query,
    auth_config=bigquery_auth_config_3lo,
)

# Register the Agent Identity auth provider so ADK can resolve the GCP connector
# scheme above into real credentials at runtime.
CredentialManager.register_auth_provider(GcpAuthProvider())

root_agent = Agent(
    name="bigquery_agent",
    model=MODEL,
    instruction=(
        "You are a BigQuery data assistant. When the user asks a data "
        "question, write a single BigQuery Standard SQL query and call the "
        "`bigquery_query` tool with it. The query runs with the user's own "
        "permissions. Prefer LIMIT on exploratory queries. If you don't know "
        "the table, you may query public datasets such as "
        "`bigquery-public-data.samples.shakespeare`. Summarize the results "
        "clearly and concisely."
    ),
    tools=[bigquery_tool],
)

# Used by `adk web` for local iteration.
app = App(
    name="agent_identity_bigquery",
    root_agent=root_agent,
)
