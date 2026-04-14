#!/usr/bin/env bash
set -euo pipefail

# Needs: az (logged in) and gh (logged in to GitHub)
if ! command -v az >/dev/null; then echo "az not found"; exit 1; fi
if ! command -v gh >/dev/null; then echo "gh not found"; exit 1; fi

echo "Minting new Azure AI bearer token..."
TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)

echo "Updating GitHub secret AGENT_BEARER_TOKEN..."
# If your repo slug changes, update the --repo value:
gh secret set AGENT_BEARER_TOKEN --repo FischerHewitt/sar-agent-mvp --body "$TOKEN"

echo "Done. Push a tiny commit to trigger CI:"
echo "  git commit --allow-empty -m 'ci: trigger smoke test (fresh token)' && git push"
