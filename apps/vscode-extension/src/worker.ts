import { ChildProcessWithoutNullStreams, spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import * as path from 'node:path';
import * as vscode from 'vscode';
import { PythonRuntime } from './pythonRuntime';
import { Language, tx } from './i18n';

type Pending = { resolve: (result: unknown) => void; reject: (reason: Error) => void; timer: NodeJS.Timeout };

export class WorkerClient implements vscode.Disposable {
  private process: ChildProcessWithoutNullStreams;
  private pending = new Map<string, Pending>();
  private nextId = 0;
  private disposed = false;

  constructor(
    root: string, python: PythonRuntime, extensionPath: string,
    baseline: string | undefined, policy: string | undefined,
    private readonly output: vscode.OutputChannel,
    private language: Language = 'es',
  ) {
    const args = ['-u', '-m', 'safecode_core.workspace_cli', root];
    if (baseline) args.push('--baseline', baseline);
    if (policy) args.push('--policy', policy);
    const bundled = path.join(extensionPath, 'python');
    const development = path.resolve(extensionPath, '../../packages/core/src');
    const modulePath = require('node:fs').existsSync(bundled) ? bundled : development;
    const env = { ...process.env, PYTHONPATH: [modulePath, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
      PYTHONDONTWRITEBYTECODE: '1' };
    const command = python.host ? 'flatpak-spawn' : python.executable;
    const commandArgs = python.host
      ? ['--host', `--directory=${root}`, `--env=PYTHONPATH=${env.PYTHONPATH}`, '--env=PYTHONDONTWRITEBYTECODE=1', python.executable, ...args]
      : args;
    this.output.appendLine(`${tx(this.language, 'Motor Python', 'Python engine')}: ${python.executable}${python.host ? tx(this.language, ' (host de Flatpak)', ' (Flatpak host)') : ''}`);
    this.process = spawn(command, commandArgs, { cwd: root, env, stdio: 'pipe' });
    this.process.stdout.setEncoding('utf8');
    this.process.stderr.setEncoding('utf8');
    createInterface({ input: this.process.stdout }).on('line', line => this.receive(line));
    this.process.stderr.on('data', text => this.output.append(String(text)));
    this.process.on('error', error => this.failAll(error));
    this.process.on('exit', (code, signal) => this.failAll(new Error(tx(this.language,
      `El motor de SafeCode terminó (${code ?? signal}). Revisa la salida de SafeCode.`,
      `The SafeCode engine exited (${code ?? signal}). Check the SafeCode output.`))));
  }

  setLanguage(language: Language): void { this.language = language; }

  request<T>(method: string, params: Record<string, unknown> = {}, timeoutMs = 120_000): Promise<T> {
    if (this.disposed || !this.process.stdin.writable) return Promise.reject(new Error(tx(this.language, 'El motor de SafeCode no está disponible.', 'The SafeCode engine is unavailable.')));
    const id = `vscode-${++this.nextId}`;
    return new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(tx(this.language, `Tiempo de espera agotado para ${method}.`, `Timed out waiting for ${method}.`)));
      }, timeoutMs);
      this.pending.set(id, { resolve: result => resolve(result as T), reject, timer });
      this.process.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n', error => {
        if (error) {
          const waiting = this.pending.get(id);
          if (waiting) { clearTimeout(waiting.timer); this.pending.delete(id); waiting.reject(error); }
        }
      });
    });
  }

  private receive(line: string): void {
    let response: { id?: unknown; result?: unknown; error?: { message?: string } };
    try { response = JSON.parse(line); }
    catch { this.output.appendLine(`${tx(this.language, 'Respuesta inválida del motor', 'Invalid engine response')}: ${line.slice(0, 300)}`); return; }
    if (typeof response.id !== 'string') return;
    const pending = this.pending.get(response.id);
    if (!pending) return;
    this.pending.delete(response.id);
    clearTimeout(pending.timer);
    if (response.error) pending.reject(new Error(response.error.message || tx(this.language, 'Error del motor de SafeCode.', 'SafeCode engine error.')));
    else pending.resolve(response.result);
  }

  private failAll(error: Error): void {
    for (const pending of this.pending.values()) { clearTimeout(pending.timer); pending.reject(error); }
    this.pending.clear();
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.failAll(new Error(tx(this.language, 'La sesión de SafeCode se cerró.', 'The SafeCode session was closed.')));
    this.process.kill();
  }
}
