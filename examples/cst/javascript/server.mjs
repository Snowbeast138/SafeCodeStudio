// Optional demo: node server.mjs; visit http://127.0.0.1:8102.
import { createServer } from "node:http";
createServer((request, response) => {
  const api = request.url === "/api/status";
  response.setHeader("Content-Type", api ? "application/json" : "text/html; charset=utf-8");
  response.end(api ? JSON.stringify({ language: "JavaScript", ok: true }) :
    '<!doctype html><meta charset="utf-8"><h1>SafeCode · JavaScript</h1><a href="/api/status">Ver JSON</a>');
}).listen(8102, "127.0.0.1");
