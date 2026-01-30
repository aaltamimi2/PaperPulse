#!/bin/bash
# Run the PaperPulse feedback server

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Load environment
source .env 2>/dev/null || true

# Default port
PORT=${FEEDBACK_PORT:-8765}

echo "Starting PaperPulse Feedback Server on port $PORT..."
echo "Endpoints:"
echo "  GET /read/{token}           - Mark paper as read"
echo "  GET /rate/{token}/up        - Thumbs up"
echo "  GET /rate/{token}/down      - Thumbs down"
echo "  GET /stats                  - View feedback stats"
echo ""

python -m uvicorn paperpulse.api.feedback_server:app --host 0.0.0.0 --port $PORT
