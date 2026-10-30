#!/usr/bin/env bash
# Deploy WhyChain to Nebius AI Cloud as a Serverless Endpoint, from an image in Nebius Container Registry.
# Creates billable resources (a registry and a CPU endpoint): run it only when you mean to.
#
#   ./deploy/nebius-deploy.sh                  # keyless replay demo (no model calls, nothing to drain)
#   LIVE=1 ./deploy/nebius-deploy.sh           # live investigations on Token Factory, behind an access code
#
# Needs: the nebius CLI, logged in (nebius profile create), Docker, and for LIVE=1 NEBIUS_API_KEY and
# WHYCHAIN_ACCESS_CODE in the environment. On Windows run it from WSL (Ubuntu), where the nebius CLI lives.
set -euo pipefail
cd "$(dirname "$0")/.."

NEBIUS=${NEBIUS:-nebius}
command -v "$NEBIUS" >/dev/null 2>&1 || NEBIUS="$HOME/.nebius/bin/nebius"
NAME=${NAME:-whychain}
PLATFORM=${PLATFORM:-cpu-d3}          # CPU is enough: the models run on Token Factory, not in the container
PRESET=${PRESET:-4vcpu-16gb}
TAG=$(date +%Y%m%d-%H%M%S)

# 1. A Container Registry (once). Its id without the "registry-" prefix is the image path.
REGISTRY_ID=${REGISTRY_ID:-$("$NEBIUS" registry list --format json | python3 -c \
  'import json,sys; print(next((i["metadata"]["id"] for i in json.load(sys.stdin).get("items", []) if i["metadata"]["name"] == "whychain"), ""))')}
if [ -z "$REGISTRY_ID" ]; then
  REGISTRY_ID=$("$NEBIUS" registry create --name whychain --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["metadata"]["id"])')
fi
REGION=${REGION:-eu-north1}
HOST="cr.$REGION.nebius.cloud"
IMAGE="$HOST/${REGISTRY_ID#registry-}/$NAME:$TAG"

# 2. Build for linux/amd64 and push (the registry login is a short-lived IAM token)
docker build --platform linux/amd64 -t "$IMAGE" .
"$NEBIUS" iam get-access-token | docker login "$HOST" --username iam --password-stdin
docker push "$IMAGE"

# 3. The Serverless Endpoint. Keyless by default; LIVE=1 adds the Token Factory key behind an access code and caps.
ENV_ARGS=()
if [ "${LIVE:-0}" = "1" ]; then
  : "${NEBIUS_API_KEY:?set NEBIUS_API_KEY}" "${WHYCHAIN_ACCESS_CODE:?set WHYCHAIN_ACCESS_CODE}"
  ENV_ARGS+=(--env "NEBIUS_API_KEY=$NEBIUS_API_KEY" --env "WHYCHAIN_ACCESS_CODE=$WHYCHAIN_ACCESS_CODE"
             --env "WHYCHAIN_MAX_RUNS_PER_DAY=${WHYCHAIN_MAX_RUNS_PER_DAY:-20}"
             --env "WHYCHAIN_DAILY_TOKEN_BUDGET=${WHYCHAIN_DAILY_TOKEN_BUDGET:-1000000}")
fi
SUBNET=$("$NEBIUS" vpc subnet list --format json | python3 -c \
  'import json,sys; i=json.load(sys.stdin).get("items", []); print(i[0]["metadata"]["id"] if i else "")')
"$NEBIUS" ai endpoint create --name "$NAME-$TAG" --image "$IMAGE" --platform "$PLATFORM" --preset "$PRESET" \
  --container-port 8000 --auth none ${SUBNET:+--subnet-id "$SUBNET"} "${ENV_ARGS[@]}" --format json

# 4. Wait for its public URL, then check health
echo "Waiting for the endpoint..."
for _ in $(seq 60); do
  URL=$("$NEBIUS" ai endpoint list --format json | python3 -c "
import json,sys
for i in json.load(sys.stdin).get('items', []):
    if i['metadata']['name'] == '$NAME-$TAG':
        u = [x for x in (i.get('status') or {}).get('public_endpoints') or [] if str(x).startswith('http')]
        print(u[0] if u else '')")
  [ -n "$URL" ] && curl -fsS "$URL/api/health" && { echo; echo "WhyChain is live at $URL"; exit 0; }
  sleep 10
done
echo "The endpoint did not come up in 10 minutes: nebius ai endpoint list" >&2
exit 1
