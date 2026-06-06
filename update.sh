#!/usr/bin/env bash
set -euo pipefail

echo "Updating Kubernetes Platform Engineer MCP..."

git pull origin main || { echo "ERROR: git pull failed"; exit 1; }

[[ -x ./stop.sh ]] || { echo "ERROR: stop.sh not found or not executable"; exit 1; }
./stop.sh

[[ -x ./start.sh ]] || { echo "ERROR: start.sh not found or not executable"; exit 1; }
./start.sh

echo "Update complete and server restarted."
