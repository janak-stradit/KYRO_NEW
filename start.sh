#!/bin/bash
# KYRO AML - Quick Start Script

set -e

echo "🚀 Starting KYRO AML System..."
echo "================================"

# Change to script directory
cd "$(dirname "$0")"

# Check if Docker is available
if command -v docker-compose &> /dev/null; then
    echo "✓ Docker Compose found"
    USE_DOCKER=true
else
    echo "⚠ Docker Compose not found, using manual setup"
    USE_DOCKER=false
fi

# Clean up any existing processes
echo ""
echo "🧹 Cleaning up existing processes..."
pkill -9 -f uvicorn 2>/dev/null || true
fuser -k 8010/tcp 2>/dev/null || true
echo "✓ Cleanup complete"

if [ "$USE_DOCKER" = true ]; then
    # Docker setup
    echo ""
    echo "🐳 Starting Docker services..."
    docker-compose down -v 2>/dev/null || true
    docker-compose up -d postgres redis api frontend
    
    echo ""
    echo "⏳ Waiting for services to start (30 seconds)..."
    sleep 30
    
    echo ""
    echo "📊 Service Status:"
    docker-compose ps
    
    echo ""
    echo "✅ KYRO AML is running!"
    echo ""
    echo "🌐 Access Points:"
    echo "   Frontend:  http://localhost:3000"
    echo "   API Docs:  http://localhost:8010/docs"
    echo "   pgAdmin:   http://localhost:5050"
    echo ""
    echo "📝 View logs:"
    echo "   docker-compose logs -f api"
    
else
    # Manual setup
    echo ""
    echo "🐍 Starting with Python virtual environment..."
    
    # Check if venv exists
    if [ ! -d "venv" ]; then
        echo "⚠ Virtual environment not found, creating..."
        python3 -m venv venv
        source venv/bin/activate
        pip install -r requirements-api.txt
    else
        source venv/bin/activate
        echo "✓ Virtual environment activated"
    fi
    
    # Check if elevenlabs is installed
    if ! pip list | grep -q elevenlabs; then
        echo "📦 Installing elevenlabs..."
        pip install elevenlabs
    fi
    
    # Start Redis if Docker is available
    if command -v docker &> /dev/null; then
        echo "🔄 Starting Redis with Docker..."
        docker run -d -p 6380:6379 --name kyro_redis redis:7-alpine 2>/dev/null || \
            docker start kyro_redis 2>/dev/null || true
    fi
    
    # Start API server
    echo ""
    echo "🚀 Starting API server..."
    ./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload &
    API_PID=$!
    
    echo "⏳ Waiting for API to start..."
    sleep 5
    
    # Start frontend
    echo "🌐 Starting frontend server..."
    cd frontend/phase3
    python3 -m http.server 3000 &
    FRONTEND_PID=$!
    cd ../..
    
    echo ""
    echo "✅ KYRO AML is running!"
    echo ""
    echo "🌐 Access Points:"
    echo "   Frontend:  http://localhost:3000"
    echo "   API Docs:  http://localhost:8010/docs"
    echo ""
    echo "📝 Process IDs:"
    echo "   API: $API_PID"
    echo "   Frontend: $FRONTEND_PID"
    echo ""
    echo "🛑 To stop:"
    echo "   kill $API_PID $FRONTEND_PID"
    
    # Keep script running
    wait $API_PID
fi
