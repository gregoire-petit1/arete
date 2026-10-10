#!/usr/bin/env bash
# Remove all but the KEEP newest deployments matching Vercel API filters.
#
#   scripts/ci/prune_deployments.sh KEEP [query filters...]
#   scripts/ci/prune_deployments.sh 1 meta-pr=42
#   scripts/ci/prune_deployments.sh 2 target=production
#
# Each deployment stores its own ~430 MB Python function, and the Hobby plan's
# function storage is 10 GB. Everything goes through the REST API: in CI the
# CLI can neither load the project (`vercel list`, no `.vercel` link) nor
# resolve `--scope` with the token. A deployment an alias still points to (the
# live production, the fixed main preview) is never removed. One page of 100
# bounds a single run.
set -euo pipefail

keep="$1"
shift

api="https://api.vercel.com"
team="teamId=$VERCEL_ORG_ID"
auth=(-H "Authorization: Bearer $VERCEL_TOKEN")

query="projectId=$VERCEL_PROJECT_ID&$team&limit=100"
for filter in "$@"; do
  query="$query&$filter"
done

curl -fsS "${auth[@]}" "$api/v6/deployments?$query" \
  | jq -r --argjson keep "$keep" '.deployments | sort_by(-.created) | .[$keep:][] | .uid' \
  | while read -r id; do
      aliases=$(curl -fsS "${auth[@]}" "$api/v2/deployments/$id/aliases?$team" | jq '.aliases | length')
      if [[ "$aliases" != 0 ]]; then
        echo "kept $id: still aliased"
        continue
      fi
      curl -fsS -X DELETE "${auth[@]}" "$api/v13/deployments/$id?$team" >/dev/null
      echo "removed $id"
    done
