#!/bin/bash
# Check KYRO System Status

echo "🔍 KYRO System Status Check"
echo "============================"

# Check API
echo ""
echo "API Server (Port 8010):"
if curl -s http://localhost:8010/docs > /dev/null; then
    echo "  ✅ RUNNING"
    
    # Check TTS endpoint specifically
    TTS_CHECK=$(curl -s -w "%{http_code}" -o /dev/null http://localhost:8010/docs | grep -q "200" && echo "OK" || echo "ERROR")
    echo "  TTS Endpoint: Check at http://localhost:8010/docs"
else
    echo "  ❌ NOT RUNNING"
    echo "  Start with: ./start_manual.sh"
fi

# Check Frontend
echo ""
echo "Frontend (Port 3000):"
if curl -s http://localhost:3000 > /dev/null; then
    echo "  ✅ RUNNING"
    echo "  Access at: http://localhost:3000"
else
    echo "  ❌ NOT RUNNING"
fi

# Check processes
echo ""
echo "Running Processes:"
UVICORN_PID=$(pgrep -f "uvicorn.*app.main" || echo "none")
FRONTEND_PID=$(pgrep -f "python3 -m http.server 3000" || echo "none")
echo "  API PID: $UVICORN_PID"
echo "  Frontend PID: $FRONTEND_PID"

# Check .env
echo ""
echo "Environment Config:"
if [ -f ".env" ]; then
    echo "  ✅ .env file exists"
    if grep -q "ELEVENLABS_API_KEY" .env; then
        KEY=$(grep "ELEVENLABS_API_KEY" .env | cut -d= -f2 | cut -c1-20)
        echo "  API Key: ${KEY}..."
    fi
    if grep -q "ELEVENLABS_VOICE_ID" .env; then
        VOICE=$(grep "ELEVENLABS_VOICE_ID" .env | cut -d= -f2)
        echo "  Voice ID: $VOICE"
    fi
else
    echo "  ❌ .env file NOT found!"
fi

# Check logs
echo ""
echo "Recent Logs:"
if [ -f "api.log" ]; then
    echo "  API Log (last 5 lines):"
    tail -5 api.log | sed 's/^/    /'
else
    echo "  ⚠️  No api.log found"
fi

echo ""
echo "============================"
echo "💡 Quick Actions:"
echo "   Start:  ./start_manual.sh"
echo "   Stop:   ./stop.sh"
echo "   Test:   ./test_tts_live.sh"
