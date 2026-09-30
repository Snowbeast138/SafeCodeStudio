"""Optional demo: python3 server.py; visit http://127.0.0.1:8101."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        api = self.path == "/api/status"
        body = (json.dumps({"language": "Python", "ok": True}) if api else
                '<!doctype html><meta charset="utf-8"><h1>SafeCode · Python</h1><a href="/api/status">Ver JSON</a>').encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json" if api else "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8101), Handler).serve_forever()
