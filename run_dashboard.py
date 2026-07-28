#!/usr/bin/env python3
"""
KYRO AML Data Generator - Dashboard Launcher
Starts both the Flask backend and serves the frontend dashboard
"""

import os
import sys
import time
import signal
import subprocess
import threading
from pathlib import Path

def start_backend():
    """Start the Flask backend server"""
    print("🚀 Starting KYRO AML Backend Server...")
    backend_process = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=Path(__file__).parent,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent)}
    )
    return backend_process

def start_frontend():
    """Start the frontend development server"""
    print("🎨 Starting KYRO Frontend Dashboard...")
    frontend_process = subprocess.Popen(
        [sys.executable, "-m", "http.server", "3000"],
        cwd=Path(__file__).parent / "frontend"
    )
    return frontend_process

def main():
    """Main launcher function"""
    print("=" * 60)
    print("  🟠 KYRO AML Data Generator Dashboard 🟠")
    print("=" * 60)
    
    processes = []
    
    try:
        # Start backend
        backend = start_backend()
        processes.append(backend)
        
        # Wait a moment for backend to start
        time.sleep(3)
        
        # Start frontend
        frontend = start_frontend()
        processes.append(frontend)
        
        print("\n✅ Dashboard is starting up...")
        print("📊 Backend API: http://localhost:5050")
        print("🌐 Frontend Dashboard: http://localhost:3000")
        print("\n📋 Usage Instructions:")
        print("1. Open http://localhost:3000 in your browser")
        print("2. Check system health in the Dashboard section")
        print("3. Use the Generator section to create data")
        print("4. Preview sample data in the Preview section")
        print("\nPress Ctrl+C to stop all services\n")
        
        # Keep the main process running
        while True:
            # Check if processes are still running
            for i, process in enumerate(processes):
                if process.poll() is not None:
                    print(f"❌ Process {i+1} has stopped unexpectedly")
                    return 1
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Shutting down KYRO Dashboard...")
        
    except Exception as e:
        print(f"❌ Error starting dashboard: {e}")
        return 1
        
    finally:
        # Clean up processes
        for process in processes:
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        print("✅ All services stopped")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())