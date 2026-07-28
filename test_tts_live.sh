#!/bin/bash
# Test ElevenLabs TTS with live API

echo "🔊 Testing KYRO TTS System..."
echo "================================"

# Check if API is running
echo ""
echo "1️⃣ Checking if API is running..."
if curl -s http://localhost:8010/docs > /dev/null; then
    echo "✓ API is running on port 8010"
else
    echo "❌ API is NOT running!"
    echo "   Start it with: ./start_manual.sh"
    exit 1
fi

# Check TTS endpoint
echo ""
echo "2️⃣ Testing TTS endpoint..."
RESPONSE=$(curl -s -o test_audio.mp3 -w "%{http_code}" \
    -X POST "http://localhost:8010/api/v1/tts/speak" \
    -H "Content-Type: application/json" \
    -d '{"text":"Hello, this is a test from Kyro AML system."}')

echo "   HTTP Status: $RESPONSE"

if [ "$RESPONSE" = "200" ]; then
    echo "✅ TTS API is working!"
    echo ""
    echo "3️⃣ Audio file created: test_audio.mp3"
    ls -lh test_audio.mp3
    echo ""
    echo "🔊 Playing audio..."
    
    # Try different audio players
    if command -v mpv &> /dev/null; then
        mpv test_audio.mp3
    elif command -v vlc &> /dev/null; then
        vlc --play-and-exit test_audio.mp3
    elif command -v aplay &> /dev/null; then
        aplay test_audio.mp3
    elif command -v ffplay &> /dev/null; then
        ffplay -nodisp -autoexit test_audio.mp3
    else
        echo "⚠️  No audio player found. Install mpv or vlc to play."
        echo "   Audio file saved as: test_audio.mp3"
    fi
else
    echo "❌ TTS API failed with status: $RESPONSE"
    echo ""
    echo "Checking API logs..."
    tail -20 api.log 2>/dev/null || echo "No api.log found"
fi

echo ""
echo "================================"
echo "✅ Test complete!"
