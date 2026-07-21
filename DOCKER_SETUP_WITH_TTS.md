# KYRO Docker Setup with ElevenLabs TTS

## Current Environment Status

✅ `.env` file configured with:
- **ElevenLabs API Key**: `sk_e519f6fff0e4869e1a7bf9f91520d7611fb88af278430619`
- **Voice ID**: `pNInz6obpgDQGcFmaJgB` (Adam - Male)
- **Model**: `eleven_turbo_v2`
- **Provider**: `elevenlabs`

## Docker Setup Commands

### 1. Stop Any Running Servers
```bash
# Kill any uvicorn processes
pkill -9 -f uvicorn

# Free port 8010
fuser -k 8010/tcp

# Stop any Docker containers
docker-compose down
```

### 2. Build and Start with Docker Compose
```bash
cd ~/Desktop/KYRO_New/KYRO_NEW

# Build all services
docker-compose build

# Start all services
docker-compose up -d

# Or start specific services
docker-compose up -d postgres redis api frontend
```

### 3. Check Services Status
```bash
# View running containers
docker-compose ps

# Check logs
docker-compose logs -f api      # API logs
docker-compose logs -f frontend # Frontend logs

# Check if API is healthy
curl http://localhost:8010/docs
```

### 4. Access the Application

- **Frontend**: http://localhost:3000
- **API Docs**: http://localhost:8010/docs
- **pgAdmin**: http://localhost:5050
- **TTS Endpoint**: http://localhost:8010/api/v1/tts/speak

### 5. Test TTS

```bash
# Test TTS endpoint
curl -X POST "http://localhost:8010/api/v1/tts/speak" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"text":"Hello from Kyro"}' \
  --output test.mp3

# Play the audio
mpv test.mp3  # or vlc test.mp3
```

## Environment Variables for Docker

The API service needs TTS environment variables. Update `docker-compose.yml`:

```yaml
api:
  environment:
    # ... existing vars ...
    ELEVENLABS_API_KEY: ${ELEVENLABS_API_KEY}
    ELEVENLABS_VOICE_ID: ${ELEVENLABS_VOICE_ID}
    ELEVENLABS_MODEL_ID: ${ELEVENLABS_MODEL_ID}
    TTS_PROVIDER: ${TTS_PROVIDER}
```

## Troubleshooting

### Port Already in Use
```bash
# Check what's using port 8010
sudo lsof -i :8010

# Kill it
sudo fuser -k 8010/tcp
```

### TTS Not Working
```bash
# Check API logs
docker-compose logs api | grep -i tts

# Check if elevenlabs package is installed
docker-compose exec api pip list | grep elevenlabs

# Rebuild API container
docker-compose build api
docker-compose up -d api
```

### Recreate Everything
```bash
# Stop and remove all containers
docker-compose down -v

# Rebuild from scratch
docker-compose build --no-cache

# Start fresh
docker-compose up -d
```

## Production Checklist

- [ ] Change `SECRET_KEY` in `.env`
- [ ] Change `DB_PASSWORD` in `.env`
- [ ] Change `PGADMIN_PASSWORD` in `.env`
- [ ] Use proper domain names (not localhost)
- [ ] Enable HTTPS/SSL
- [ ] Set up proper firewall rules
- [ ] Enable database backups
- [ ] Monitor TTS API usage (ElevenLabs has limits)

## Quick Start (Fresh Setup)

```bash
cd ~/Desktop/KYRO_New/KYRO_NEW

# Clean slate
docker-compose down -v
pkill -9 -f uvicorn

# Start everything
docker-compose up -d

# Wait for services to be ready (30 seconds)
sleep 30

# Open browser
xdg-open http://localhost:3000
```

## API Ports

- `8010` → API (FastAPI/Uvicorn)
- `3000` → Frontend (Nginx)
- `5434` → PostgreSQL
- `5050` → pgAdmin
- `6380` → Redis

All services run in Docker network `kyro_net`.
