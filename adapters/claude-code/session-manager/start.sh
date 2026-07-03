#!/bin/bash
# Run from WSL2: bash start.sh
cd "$(dirname "$0")"
# Load local env vars if .env exists (IKEOS_METRICS_URL, IKEOS_CAPTURE_TOKEN, etc.)
if [ -f .env ]; then
    set -a; source .env; set +a
fi
pip install -r requirements.txt -q
python3 app.py
