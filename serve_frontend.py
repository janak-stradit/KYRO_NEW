#!/usr/bin/env python3
"""
KYRO Frontend Server
Serves the frontend dashboard files
"""

import http.server
import socketserver
import os
import sys
from pathlib import Path

def main():
    """Start the frontend server"""
    frontend_dir = Path(__file__).parent / "frontend" / "phase3"
    
    if not frontend_dir.exists():
        print(f"❌ Frontend directory not found: {frontend_dir}")
        return 1
    
    os.chdir(frontend_dir)
    
    PORT = 3000
    
    class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
        def translate_path(self, path):
            clean_path = path.split('?')[0].split('#')[0]
            if clean_path == '/':
                path = '/landing.html'
            elif clean_path == '/login':
                path = '/login.html'
            elif clean_path in ['/dashboard', '/periodic-reviews', '/cases', '/patterns', '/kyrochat']:
                path = '/index.html'
            return super().translate_path(path)

        def end_headers(self):
            # Add CORS headers
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
            # Disable caching
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            super().end_headers()
            
        def do_OPTIONS(self):
            self.send_response(200)
            self.end_headers()
    
    print(f"🌐 Starting KYRO Frontend Server...")
    print(f"📊 Dashboard available at: http://localhost:{PORT}")
    print(f"📁 Serving files from: {frontend_dir}")
    print("\nPress Ctrl+C to stop the server\n")
    
    try:
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(("", PORT), MyHTTPRequestHandler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Frontend server stopped")
    except Exception as e:
        print(f"❌ Error starting frontend server: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())