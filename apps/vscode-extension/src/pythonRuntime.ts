import { spawn } from 'node:child_process';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { Language, tx } from './i18n';

export interface PythonRuntime { executable: string; host: boolean }

export function isFlatpak(): boolean {
  return Boolean(process.env.FLATPAK_ID) || fs.existsSync('/.flatpak-info');
}

export function pythonCandidates(root: string, extensionPath: string, configured: string): string[] {
  const executable = process.platform === 'win32' ? path.join('Scripts', 'python.exe') : path.join('bin', 'python');
  const candidate = configured.trim();
  if (candidate) return [path.isAbsolute(candidate) ? candidate : path.resolve(root, candidate)];
  return [...new Set([
    path.join(root, '.venv', executable),
    path.resolve(extensionPath, '../../.venv', executable),
    path.join(path.dirname(root), 'SafeCode', '.venv', executable),
    path.join(path.dirname(root), 'safecode', '.venv', executable),
    process.platform === 'win32' ? 'python' : 'python3',
  ])];
}

function probe(python: string, host: boolean): Promise<boolean> {
  return new Promise(resolve => {
    const command = host ? 'flatpak-spawn' : python;
    const args = host ? ['--host', python, '-c', 'import tree_sitter, tree_sitter_python, tree_sitter_javascript, tree_sitter_typescript, networkx']
      : ['-c', 'import tree_sitter, tree_sitter_python, tree_sitter_javascript, tree_sitter_typescript, networkx'];
    let settled = false;
    const finish = (ok: boolean) => { if (!settled) { settled = true; clearTimeout(timer); resolve(ok); } };
    const child = spawn(command, args, { stdio: 'ignore' });
    const timer = setTimeout(() => { child.kill(); finish(false); }, 5000);
    child.on('error', () => finish(false));
    child.on('exit', code => finish(code === 0));
  });
}

export async function resolvePython(root: string, extensionPath: string, configured: string, language: Language = 'es'): Promise<PythonRuntime> {
  const host = isFlatpak();
  const candidates = pythonCandidates(root, extensionPath, configured);
  for (const executable of candidates) {
    if (path.isAbsolute(executable) && !fs.existsSync(executable)) continue;
    if (await probe(executable, host)) return { executable, host };
  }
  throw new Error(configured.trim()
    ? tx(language, `El Python configurado (${candidates[0]}) no puede importar tree-sitter, sus gramáticas y networkx. Elige otro intérprete de SafeCode.`,
      `The configured Python (${candidates[0]}) cannot import tree-sitter, its grammars, and networkx. Choose another SafeCode interpreter.`)
    : tx(language, 'No encontré un Python con tree-sitter, sus gramáticas y networkx. Elige el entorno virtual de SafeCode.',
      'No Python with tree-sitter, its grammars, and networkx was found. Choose the SafeCode virtual environment.'));
}
