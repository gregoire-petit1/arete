#!/usr/bin/env bash
# Remove all but the KEEP newest deployments matching `vercel list` filters.
#
#   scripts/ci/prune_deployments.sh KEEP [vercel list filters...]
#   scripts/ci/prune_deployments.sh 1 --meta pr=42
#   scripts/ci/prune_deployments.sh 2 --environment production
#
# Each deployment stores its own ~430 MB Python function, and the Hobby plan's
# function storage is 10 GB. `--safe` never removes a deployment an alias still
# points to (the live production), and one listing page bounds a single run.
set -euo pipefail

keep="$1"
shift

vercel list "$@" --format json --token "$VERCEL_TOKEN" \
  | jq -r --argjson keep "$keep" '.deployments | sort_by(-.createdAt) | .[$keep:][] | .url' \
  | while read -r url; do
      vercel remove "$url" --safe --yes --token "$VERCEL_TOKEN"
    done
