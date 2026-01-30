#!/bin/bash
# Setup cron jobs for PaperPulse:
# - Daily digest at 6am
# - Saturday wrap-up at 9am

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON_PATH="$(which python3)"
LOG_DIR="$HOME/.paperpulse"

# Create log directory
mkdir -p "$LOG_DIR"

# Cron commands
DAILY_CMD="0 6 * * * cd $PROJECT_DIR && $PYTHON_PATH $SCRIPT_DIR/daily_digest.py >> $LOG_DIR/daily_digest.log 2>&1"
SATURDAY_CMD="0 9 * * 6 cd $PROJECT_DIR && $PYTHON_PATH $SCRIPT_DIR/saturday_wrapup.py >> $LOG_DIR/saturday_wrapup.log 2>&1"

echo "Setting up PaperPulse cron jobs..."
echo ""
echo "1. Daily digest at 6:00 AM (every day)"
echo "2. Saturday wrap-up at 9:00 AM (Saturdays only)"
echo ""

# Check if cron jobs already exist
if crontab -l 2>/dev/null | grep -q "paperpulse"; then
    echo "⚠️  PaperPulse cron jobs already exist."
    echo "   To update, first remove with: crontab -e"
    echo ""
    echo "Current cron jobs:"
    crontab -l | grep -i paperpulse
    exit 1
fi

# Add to crontab
(crontab -l 2>/dev/null
echo ""
echo "# PaperPulse daily digest at 6am"
echo "$DAILY_CMD"
echo ""
echo "# PaperPulse Saturday wrap-up at 9am"
echo "$SATURDAY_CMD"
) | crontab -

echo "✅ Cron jobs installed!"
echo ""
echo "To verify: crontab -l"
echo "To remove: crontab -e (delete the PaperPulse lines)"
echo ""
echo "Logs:"
echo "  Daily:    $LOG_DIR/daily_digest.log"
echo "  Saturday: $LOG_DIR/saturday_wrapup.log"
echo ""
echo "⚠️  IMPORTANT: For feedback buttons to work, run the feedback server:"
echo "   ./scripts/run_feedback_server.sh"
echo ""
echo "   Or use ngrok for external access:"
echo "   ngrok http 8765"
echo "   Then set FEEDBACK_URL in .env to your ngrok URL"
