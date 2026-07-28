#!/bin/bash
# KYRO AML - Manual Start (No Docker)

set -e

echo "🚀 Starting KYRO AML System (Manual Mode)..."
echo "============================================="

cd "$(dirname "$0")"

# Clean up
echo "🧹 Cleaning up existing processes..."
pkill -9 -f uvicorn 2>/dev/null || true
pkill -9 -f "python3 -m http.server" 2>/dev/null || true
fuser -k 8010/tcp 2>/dev/null || true
fuser -k 3000/tcp 2>/dev/null || true
sleep 2

# Activate venv
echo "🐍 Activating virtual environment..."
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "   Create it with: python3 -m venv venv"
    exit 1
fi

source venv/bin/activate
echo "✓ Virtual environment activated"

# Check elevenlabs
if ! pip list 2>/dev/null | grep -q elevenlabs; then
    echo "📦 Installing elevenlabs..."
    pip install elevenlabs
fi

# Start API
echo ""
echo "🚀 Starting API server on port 8010..."
nohup ./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload > api.log 2>&1 &
API_PID=$!
echo "   API PID: $API_PID"

# Wait for API
echo "⏳ Waiting for API to start..."
sleep 5

# Test API
if curl -s http://localhost:8010/docs > /dev/null; then
    echo "✓ API is running!"
else
    echo "⚠ API may not be ready yet, check api.log"
fi

# Start frontend
echo ""
echo "🌐 Starting frontend server on port 3000..."
cd frontend/phase3
nohup python3 -m http.server 3000 > ../../frontend.log 2>&1 &
FRONTEND_PID=$!
cd ../..
echo "   Frontend PID: $FRONTEND_PID"

sleep 2

echo ""
echo "✅ KYRO AML is running!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🌐 ACCESS POINTS:"
echo "   Frontend:  http://localhost:3000"
echo "   API Docs:  http://localhost:8010/docs"
echo "   TTS Test:  http://localhost:8010/api/v1/tts/speak"
echo ""
echo "📝 LOGS:"
echo "   API:       tail -f api.log"
echo "   Frontend:  tail -f frontend.log"
echo ""
echo "🛑 TO STOP:"
echo "   kill $API_PID $FRONTEND_PID"
echo "   Or run: pkill -f uvicorn && pkill -f http.server"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Save PIDs
echo "$API_PID" > .api.pid
echo "$FRONTEND_PID" > .frontend.pid

echo "💡 TIP: Open http://localhost:3000 and go to Kyro Chat"
echo "        Voice will use ElevenLabs premium TTS!"
echo ""
