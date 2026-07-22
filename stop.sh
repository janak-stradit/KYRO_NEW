#!/bin/bash
# KYRO AML - Stop Script

echo "🛑 Stopping KYRO AML System..."

# Kill by PIDs if available
if [ -f .api.pid ]; then
    API_PID=$(cat .api.pid)
    kill $API_PID 2>/dev/null && echo "✓ Stopped API (PID: $API_PID)"
    rm .api.pid
fi

if [ -f .frontend.pid ]; then
    FRONTEND_PID=$(cat .frontend.pid)
    kill $FRONTEND_PID 2>/dev/null && echo "✓ Stopped Frontend (PID: $FRONTEND_PID)"
    rm .frontend.pid
fi

# Kill by process name
pkill -9 -f "uvicorn.*app.main" 2>/dev/null && echo "✓ Killed uvicorn processes"
pkill -9 -f "python3 -m http.server 3000" 2>/dev/null && echo "✓ Killed frontend server"

# Free ports
fuser -k 8010/tcp 2>/dev/null && echo "✓ Freed port 8010"
fuser -k 3000/tcp 2>/dev/null && echo "✓ Freed port 3000"

echo ""
echo "✅ KYRO AML stopped successfully!"
