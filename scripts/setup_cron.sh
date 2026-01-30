#!/bin/bash
# Setup cron job for daily PaperPulse digest at 6am

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON_PATH="$(which python3)"
LOG_FILE="$HOME/.paperpulse/daily_digest.log"

# Create log directory
mkdir -p "$HOME/.paperpulse"

# Create the cron command
CRON_CMD="0 6 * * * cd $PROJECT_DIR && $PYTHON_PATH $SCRIPT_DIR/daily_digest.py >> $LOG_FILE 2>&1"

echo "Setting up PaperPulse daily digest cron job..."
echo ""
echo "Cron command:"
echo "$CRON_CMD"
echo ""

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "daily_digest.py"; then
    echo "⚠️  Cron job already exists. Remove it first with:"
    echo "   crontab -e  (then delete the PaperPulse line)"
    exit 1
fi

# Add to crontab
(crontab -l 2>/dev/null; echo "# PaperPulse daily digest at 6am"; echo "$CRON_CMD") | crontab -

echo "✅ Cron job installed!"
echo ""
echo "To verify: crontab -l"
echo "To remove: crontab -e (delete the PaperPulse lines)"
echo "Logs at: $LOG_FILE"
