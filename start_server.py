#!/usr/bin/env python3
"""
KYRO AML Backend Server Launcher
Starts the FastAPI backend with proper configuration
"""

import uvicorn
import os
import sys
from pathlib import Path

def main():
    """Start the FastAPI server"""
    print("🚀 Starting KYRO AML Backend Server...")
    print("📊 API will be available at: http://localhost:8000")
    print("📝 API Docs available at: http://localhost:8000/docs")
    print("\nPress Ctrl+C to stop the server\n")
    
    # Add current directory to Python path
    current_dir = Path(__file__).parent
    sys.path.insert(0, str(current_dir))
    
    # Load .env variables
    import dotenv
    dotenv.load_dotenv()
    
    # Set environment variables if needed
    os.environ.setdefault("DATABASE_URL", "sqlite:///kyro_aml.db")
    
    try:
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            reload_dirs=[str(current_dir / "app")],
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n🛑 Server stopped")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())