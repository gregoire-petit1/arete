#!/usr/bin/env bash
# Remove all but the KEEP newest deployments matching Vercel API filters.
#
#   scripts/ci/prune_deployments.sh KEEP [query filters...]
#   scripts/ci/prune_deployments.sh 1 meta-pr=42
#   scripts/ci/prune_deployments.sh 2 target=production
#
# Each deployment stores its own ~430 MB Python function, and the Hobby plan's
# function storage is 10 GB. The list comes from the REST API (`vercel list`
# cannot load the project without a `.vercel` link); `vercel remove --safe`
# never removes a deployment an alias still points to (the live production).
# One page of 100 bounds a single run.
set -euo pipefail

keep="$1"
shift

query="projectId=$VERCEL_PROJECT_ID&teamId=$VERCEL_ORG_ID&limit=100"
for filter in "$@"; do
  query="$query&$filter"
done

curl -fsS -H "Authorization: Bearer $VERCEL_TOKEN" \
  "https://api.vercel.com/v6/deployments?$query" \
  | jq -r --argjson keep "$keep" '.deployments | sort_by(-.created) | .[$keep:][] | .url' \
  | while read -r url; do
      vercel remove "$url" --safe --yes --token "$VERCEL_TOKEN" --scope "$VERCEL_ORG_ID"
    done
