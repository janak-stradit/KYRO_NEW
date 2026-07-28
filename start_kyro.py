#!/usr/bin/env python3
"""
KYRO AML Dashboard - Complete Startup Script
Initializes database and starts both backend and frontend servers
"""

import subprocess
import sys
import time
import threading
import webbrowser
from pathlib import Path

def run_init_db():
    """Initialize the database"""
    print("🗄️ Initializing database...")
    try:
        result = subprocess.run([sys.executable, "init_db.py"], 
                              capture_output=True, text=True, check=True)
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Database initialization failed: {e.stderr}")
        return False

def start_backend():
    """Start the backend server in a separate process"""
    print("🚀 Starting backend server...")
    return subprocess.Popen([sys.executable, "start_server.py"])

def start_frontend():
    """Start the frontend server in a separate process"""
    print("🌐 Starting frontend server...")
    time.sleep(2)  # Wait for backend to start
    return subprocess.Popen([sys.executable, "serve_frontend.py"])

def main():
    """Main startup function"""
    print("=" * 60)
    print("  🟠 KYRO AML Dashboard - Complete Setup 🟠")
    print("=" * 60)
    
    # Change to script directory
    script_dir = Path(__file__).parent
    original_dir = Path.cwd()
    
    try:
        import os
        os.chdir(script_dir)
        
        # Initialize database
        if not run_init_db():
            return 1
            
        # Start servers
        processes = []
        
        backend_process = start_backend()
        processes.append(backend_process)
        
        frontend_process = start_frontend()
        processes.append(frontend_process)
        
        # Wait for servers to start
        time.sleep(5)
        
        print("\n" + "="*60)
        print("✅ KYRO AML Dashboard is ready!")
        print("="*60)
        print("🌐 Frontend: http://localhost:3000")
        print("📊 Backend API: http://localhost:8000")
        print("📝 API Docs: http://localhost:8000/docs") 
        print("\n💡 Usage:")
        print("1. Open http://localhost:3000 in your browser")
        print("2. Click 'Kyro Chat' in the navigation")
        print("3. Try starting the autonomous agent")
        print("4. Ask questions about compliance cases")
        print("\nPress Ctrl+C to stop all services")
        print("="*60)
        
        # Open browser automatically
        def open_browser():
            time.sleep(2)
            try:
                webbrowser.open("http://localhost:3000")
            except Exception:
                pass
                
        browser_thread = threading.Thread(target=open_browser, daemon=True)
        browser_thread.start()
        
        # Keep running until interrupted
        try:
            while True:
                # Check if processes are still alive
                for i, process in enumerate(processes):
                    if process.poll() is not None:
                        print(f"\n❌ Server {i+1} stopped unexpectedly")
                        return 1
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Shutting down KYRO Dashboard...")
            
    except Exception as e:
        print(f"❌ Startup error: {e}")
        return 1
        
    finally:
        # Cleanup
        for process in processes:
            try:
                process.terminate()
                process.wait(timeout=5)
            except (subprocess.TimeoutExpired, AttributeError):
                try:
                    process.kill()
                except (ProcessLookupError, AttributeError):
                    pass
                    
        # Change back to original directory  
        os.chdir(original_dir)
        print("✅ All services stopped")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())