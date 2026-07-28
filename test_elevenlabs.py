#!/usr/bin/env python3
"""
Test ElevenLabs API key and voice configuration
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")
ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")

print("=" * 60)
print("ElevenLabs TTS Configuration Test")
print("=" * 60)
print(f"\n✓ API Key: {ELEVENLABS_API_KEY[:20]}...{ELEVENLABS_API_KEY[-10:]}")
print(f"✓ Voice ID: {ELEVENLABS_VOICE_ID}")
print(f"✓ Model ID: {ELEVENLABS_MODEL_ID}")

# Test API connection
try:
    from elevenlabs import VoiceSettings
    from elevenlabs.client import ElevenLabs
    
    print("\n✓ ElevenLabs package installed")
    
    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    print("✓ Client initialized")
    
    # Try to get voices to verify API key
    print("\nTesting API key validity...")
    voices = client.voices.get_all()
    print(f"✓ API key is VALID! Found {len(voices.voices)} available voices")
    
    # Check if the configured voice exists
    voice_found = any(v.voice_id == ELEVENLABS_VOICE_ID for v in voices.voices)
    if voice_found:
        print(f"✓ Voice ID '{ELEVENLABS_VOICE_ID}' is VALID")
    else:
        print(f"✗ Voice ID '{ELEVENLABS_VOICE_ID}' NOT FOUND")
        print("\nAvailable voices:")
        for v in voices.voices[:5]:  # Show first 5
            print(f"  - {v.name} (ID: {v.voice_id})")
    
    # Test generating speech
    print("\nGenerating test audio...")
    audio_generator = client.text_to_speech.convert(
        text="Hello, this is a test from Kyro.",
        voice_id=ELEVENLABS_VOICE_ID,
        model_id=ELEVENLABS_MODEL_ID,
        voice_settings=VoiceSettings(
            stability=0.71,
            similarity_boost=0.85,
            style=0.15,
            use_speaker_boost=True,
        ),
    )
    
    # Consume the generator
    audio_bytes = b"".join(audio_generator)
    print(f"✓ Successfully generated {len(audio_bytes)} bytes of audio")
    
    print("\n" + "=" * 60)
    print("✓ ALL TESTS PASSED! TTS is ready to use.")
    print("=" * 60)
    
except ImportError:
    print("\n✗ ElevenLabs package not installed")
    print("  Install with: pip install elevenlabs")
    
except Exception as e:
    print(f"\n✗ Error: {e}")
    print("\nPossible issues:")
    print("  - API key is invalid or expired")
    print("  - Voice ID doesn't exist")
    print("  - Network connectivity issues")
    print("  - ElevenLabs API is down")
