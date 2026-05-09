#!/bin/bash
# JARVIS Hand Gesture Control System — Linux/macOS launcher

echo ""
echo "  ============================================"
echo "   J.A.R.V.I.S  Hand Gesture Control System"
echo "  ============================================"
echo ""

if [ -d "venv" ]; then
    echo "  [INFO] Activating virtual environment..."
    source venv/bin/activate
else
    echo "  [WARN] No venv found - using system Python"
fi

echo "  [INFO] Starting JARVIS..."
echo ""

python main.py "$@"

echo ""
echo "  [INFO] JARVIS has shut down."
