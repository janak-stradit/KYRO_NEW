# KYRO TTS (Text-to-Speech) Setup Guide

## Current Status
The TTS service is **configured but not functional** because required packages are not installed.

## Configuration
The `.env` file has ElevenLabs configured:
- `TTS_PROVIDER=elevenlabs`
- `ELEVENLABS_API_KEY=sk_e16c5fd0475b727c564a4ca2c6eccc269a065f2b9f8dfeaf`
- `ELEVENLABS_VOICE_ID=pNInz6obpgDQGcFmaJgB`

## Issue
The `elevenlabs` Python package is not installed, causing 503 errors.

## Solution Options

### Option 1: Install ElevenLabs Package
```bash
# Activate your virtual environment first
source venv/bin/activate  # or: venv\Scripts\activate on Windows

# Install ElevenLabs
pip install elevenlabs

# Restart the FastAPI server
```

### Option 2: Use OpenAI TTS (Alternative)
If you have an OpenAI API key:
```bash
# Install OpenAI
pip install openai

# Update .env
TTS_PROVIDER=openai
OPENAI_API_KEY=your_openai_key_here
```

### Option 3: Use Browser TTS (Current Fallback)
The system already falls back to browser's built-in speech synthesis when the API is unavailable. This works without any installation but uses the browser's native voice.

## Testing TTS After Installation

1. Install the package (Option 1 or 2 above)
2. Restart the FastAPI server
3. Go to Kyro Chat and enable voice
4. You should hear Kyro's voice using the configured TTS service

## Add to requirements-api.txt
To make this permanent, add to `requirements-api.txt`:
```
# ── TTS (Text-to-Speech) ──────────────────────────────────────
elevenlabs>=1.0.0
# OR
openai>=1.0.0
```

## Current Behavior
- ✅ Kyro Chat works with browser TTS fallback
- ❌ Custom voice (ElevenLabs) returns 503 error
- ✅ Graceful degradation - no functionality broken
