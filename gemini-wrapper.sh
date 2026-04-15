#!/bin/sh
set -eu

if [ -f /usr/local/bin/sync-gemini-cli-auth.py ]; then
  python3 /usr/local/bin/sync-gemini-cli-auth.py --quiet >/dev/null 2>&1 || true
fi

if [ -z "${GOOGLE_CLOUD_ACCESS_TOKEN:-}" ]; then
  ACCESS_TOKEN="$(python3 - <<'PY'
import json
from pathlib import Path

creds_path = Path("/home/node/.gemini/oauth_creds.json")
try:
    payload = json.loads(creds_path.read_text(encoding="utf-8"))
except Exception:
    payload = {}

access_token = payload.get("access_token")
if isinstance(access_token, str) and access_token.strip():
    print(access_token.strip())
PY
)"
  if [ -n "$ACCESS_TOKEN" ]; then
    export GOOGLE_GENAI_USE_GCA="${GOOGLE_GENAI_USE_GCA:-true}"
    export GOOGLE_CLOUD_ACCESS_TOKEN="$ACCESS_TOKEN"
  fi
fi

if [ -z "${GOOGLE_CLOUD_PROJECT:-}" ] || [ -z "${GOOGLE_CLOUD_PROJECT_ID:-}" ]; then
  PROJECT_ID="$(python3 - <<'PY'
import json
from pathlib import Path

auth_path = Path("/home/node/.openclaw/agents/main/agent/auth-profiles.json")
try:
    payload = json.loads(auth_path.read_text(encoding="utf-8"))
except Exception:
    payload = {}

profiles = payload.get("profiles") if isinstance(payload, dict) else {}
if isinstance(profiles, dict):
    for profile in profiles.values():
        if not isinstance(profile, dict):
            continue
        if profile.get("provider") != "google-gemini-cli":
            continue
        project_id = profile.get("projectId")
        if isinstance(project_id, str) and project_id.strip():
            print(project_id.strip())
            break
PY
)"
  if [ -n "$PROJECT_ID" ]; then
    export GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-$PROJECT_ID}"
    export GOOGLE_CLOUD_PROJECT_ID="${GOOGLE_CLOUD_PROJECT_ID:-$PROJECT_ID}"
  fi
fi

exec node /usr/local/lib/node_modules/@google/gemini-cli/bundle/gemini.js "$@"
