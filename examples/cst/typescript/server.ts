// Optional demo: node --experimental-strip-types server.ts
// Visit http://127.0.0.1:8103. Node strips types, it does not type-check them.
import { createServer } from "node:http";
type Status = { language: string; ok: boolean };
createServer((request, response) => {
  const status: Status = { language: "TypeScript", ok: true };
  const api: boolean = request.url === "/api/status";
  response.setHeader("Content-Type", api ? "application/json" : "text/html; charset=utf-8");
  response.end(api ? JSON.stringify(status) :
    '<!doctype html><meta charset="utf-8"><h1>SafeCode · TypeScript</h1><a href="/api/status">Ver JSON</a>');
}).listen(8103, "127.0.0.1");
