"""Simple server to serve the static web UI.

Run from the project root (PowerShell):
  python serve.py

Then open http://localhost:8000 in your browser.
"""
from http.server import HTTPServer, SimpleHTTPRequestHandler
import os

WEB_DIR = os.path.join(os.path.dirname(__file__), 'web')
PORT = 8000

os.chdir(WEB_DIR)
print(f"Serving {WEB_DIR} at http://localhost:{PORT}")
httpd = HTTPServer(('0.0.0.0', PORT), SimpleHTTPRequestHandler)
try:
    httpd.serve_forever()
except KeyboardInterrupt:
    print('\nServer stopped')
