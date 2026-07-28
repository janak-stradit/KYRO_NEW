# KYRO AML - Quick Start Guide

## Prerequisites
- Python 3.12+
- PostgreSQL 16
- Redis (optional, for Celery)
- Docker & Docker Compose (for containerized setup)

---

## Option 1: Docker Setup (RECOMMENDED)

### 1. Install Requirements
```bash
# Install Docker if not already installed
sudo apt update
sudo apt install docker.io docker-compose
sudo usermod -aG docker $USER
# Logout and login again
```

### 2. Configure Environment
```bash
cd ~/Desktop/KYRO_New/KYRO_NEW

# Copy .env.example if needed (already have .env)
# The .env file is already configured with:
# - Database credentials
# - ElevenLabs TTS API key
# - Redis settings
```

### 3. Start Services
```bash
# Stop any existing processes
docker-compose down -v
pkill -9 -f uvicorn
fuser -k 8010/tcp

# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f api
```

### 4. Access Application
- **Frontend**: http://localhost:3000
- **API Docs**: http://localhost:8010/docs
- **pgAdmin**: http://localhost:5050
  - Email: admin@kyro.com
  - Password: admin123

---

## Option 2: Manual Setup (Development)

### 1. Install Python Dependencies
```bash
cd ~/Desktop/KYRO_New/KYRO_NEW

# Create virtual environment (if not exists)
python3 -m venv venv

# Activate
source venv/bin/activate

# Install API dependencies (includes elevenlabs)
pip install -r requirements-api.txt

# Install pipeline dependencies
pip install -r requirements-pipeline.txt
```

### 2. Setup Database
```bash
# Start PostgreSQL (if not running)
sudo systemctl start postgresql

# Create database
sudo -u postgres psql -c "CREATE DATABASE kyro_aml;"
sudo -u postgres psql -c "CREATE USER kyro_user WITH PASSWORD 'kyro_pass';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE kyro_aml TO kyro_user;"

# Run migrations
cd ~/Desktop/KYRO_New/KYRO_NEW
./venv/bin/alembic upgrade head

# Initialize data
./venv/bin/python init_db.py
```

### 3. Start Redis (Optional, for background tasks)
```bash
# Using Docker
docker run -d -p 6380:6379 --name kyro_redis redis:7-alpine

# Or install locally
sudo apt install redis-server
sudo systemctl start redis
```

### 4. Start API Server
```bash
cd ~/Desktop/KYRO_New/KYRO_NEW

# Method 1: Using uvicorn directly
./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload

# Method 2: Using start script
./venv/bin/python start_kyro.py

# Method 3: Background process
nohup ./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload > api.log 2>&1 &
```

### 5. Start Frontend
```bash
# The frontend is static files, serve with any web server

# Option 1: Python HTTP server
cd ~/Desktop/KYRO_New/KYRO_NEW/frontend/phase3
python3 -m http.server 3000

# Option 2: Nginx (if installed)
# Point nginx to frontend/phase3 directory

# Option 3: Open directly in browser
xdg-open ~/Desktop/KYRO_New/KYRO_NEW/frontend/phase3/index.html
```

---

## Verify Installation

### 1. Check API Health
```bash
# API docs
curl http://localhost:8010/docs

# Health endpoint
curl http://localhost:8010/api/v1/dashboard/health

# Test TTS
curl -X POST "http://localhost:8010/api/v1/tts/speak" \
  -H "Content-Type: application/json" \
  -d '{"text":"Testing Kyro voice"}' \
  --output test.mp3
```

### 2. Access Frontend
- Open http://localhost:3000
- Login with default credentials:
  - Username: `analyst`
  - Password: `analyst123`

### 3. Test Features
- ✅ Dashboard - View KPIs and charts
- ✅ Review Cases - Browse AML cases
- ✅ Patterns - Behavioral analysis
- ✅ Periodic Reviews - Schedule KYC reviews
- ✅ Kyro Chat - AI assistant with voice

---

## Troubleshooting

### Port Already in Use (8010)
```bash
# Find and kill process
sudo lsof -i :8010
sudo fuser -k 8010/tcp

# Or use different port
./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8011 --reload
```

### Database Connection Error
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check connection
psql -h localhost -p 5434 -U kyro_user -d kyro_aml

# Update .env if needed
DB_HOST=localhost
DB_PORT=5434
```

### TTS Not Working
```bash
# Check elevenlabs is installed
pip list | grep elevenlabs

# Reinstall if needed
pip install elevenlabs

# Check API key in .env
cat .env | grep ELEVENLABS

# View API logs
docker-compose logs api | grep -i tts
```

### Frontend 404 Errors
```bash
# Check if API is running
curl http://localhost:8010/docs

# Update API URL in frontend
# Edit: frontend/phase3/js/api.js
# baseUrl: "http://localhost:8010/api/v1"
```

---

## File Structure

```
KYRO_NEW/
├── .env                          # Environment variables
├── docker-compose.yml            # Docker services
├── requirements-api.txt          # API dependencies (includes elevenlabs)
├── requirements-pipeline.txt     # Pipeline dependencies
├── app/                          # FastAPI application
│   ├── main.py                  # API entry point
│   ├── routers/                 # API endpoints
│   │   ├── tts.py              # ElevenLabs TTS endpoint
│   │   ├── kyrochat.py         # Chat interface
│   │   └── ...
│   └── models/                  # Database models
├── frontend/phase3/             # React-like frontend
│   ├── index.html              # Main entry
│   ├── js/                     # JavaScript modules
│   └── css/                    # Stylesheets
├── init_db.py                   # Database initialization
└── start_kyro.py               # Development server script
```

---

## Production Deployment

### Security Checklist
- [ ] Change `SECRET_KEY` in `.env`
- [ ] Change all default passwords
- [ ] Use HTTPS/SSL certificates
- [ ] Enable firewall (ufw/iptables)
- [ ] Set up database backups
- [ ] Configure reverse proxy (Nginx)
- [ ] Enable rate limiting
- [ ] Monitor API usage (ElevenLabs limits)

### Performance Tips
- Use PostgreSQL connection pooling
- Enable Redis for caching
- Use CDN for frontend assets
- Enable gzip compression
- Configure proper logging
- Set up monitoring (Prometheus/Grafana)

---

## Support & Documentation

- **API Documentation**: http://localhost:8010/docs
- **Frontend**: http://localhost:3000
- **Setup Guide**: `DOCKER_SETUP_WITH_TTS.md`
- **TTS Guide**: `TTS_SETUP.md`

## Common Commands

```bash
# Start everything (Docker)
docker-compose up -d

# Stop everything
docker-compose down

# View logs
docker-compose logs -f

# Restart API only
docker-compose restart api

# Rebuild API
docker-compose build api
docker-compose up -d api

# Database backup
docker-compose exec postgres pg_dump -U kyro_user kyro_aml > backup.sql

# Check running containers
docker-compose ps
```
