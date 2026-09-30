import * as vscode from 'vscode';
import * as path from 'node:path';
import { Finding } from './types';
import { byteColumnToUtf16 } from './positions';
import { Language, localizeFinding } from './i18n';

function safeFile(root: vscode.WorkspaceFolder, relative: string): vscode.Uri | undefined {
  const target = path.resolve(root.uri.fsPath, relative);
  const rel = path.relative(root.uri.fsPath, target);
  if (rel.startsWith('..') || path.isAbsolute(rel)) return undefined;
  return vscode.Uri.file(target);
}

export async function publishDiagnostics(
  collection: vscode.DiagnosticCollection, folder: vscode.WorkspaceFolder, findings: Finding[], language: Language = 'es',
): Promise<void> {
  const grouped = new Map<string, { uri: vscode.Uri; findings: Finding[] }>();
  for (const finding of findings) {
    const uri = safeFile(folder, finding.path);
    if (!uri || !finding.start) continue;
    const entry = grouped.get(uri.toString()) || { uri, findings: [] };
    entry.findings.push(finding);
    grouped.set(uri.toString(), entry);
  }
  collection.clear();
  for (const { uri, findings: fileFindings } of grouped.values()) {
    try {
      const document = await vscode.workspace.openTextDocument(uri);
      const diagnostics = fileFindings.map(finding => {
        const startLine = Math.max(0, Math.min(finding.start!.line - 1, document.lineCount - 1));
        const endLine = Math.max(startLine, Math.min((finding.end?.line ?? finding.start!.line) - 1, document.lineCount - 1));
        const start = new vscode.Position(startLine, byteColumnToUtf16(document.lineAt(startLine).text, finding.start!.byte_column));
        const end = new vscode.Position(endLine, byteColumnToUtf16(document.lineAt(endLine).text, finding.end?.byte_column ?? finding.start!.byte_column + 1));
        const range = new vscode.Range(start, end.isAfter(start) ? end : start.translate(0, 1));
        const severity = finding.severity === 'high' ? vscode.DiagnosticSeverity.Error : vscode.DiagnosticSeverity.Warning;
        const localized = localizeFinding(finding, language);
        const diagnostic = new vscode.Diagnostic(range, `${localized.title}. ${localized.explanation}`, severity);
        diagnostic.source = 'SafeCode';
        diagnostic.code = finding.rule_id;
        return diagnostic;
      });
      collection.set(uri, diagnostics);
    } catch {
      // A file may have disappeared between the workspace snapshot and publication.
    }
  }
}
