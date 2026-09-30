import { randomBytes } from 'node:crypto';
import * as vscode from 'vscode';
import { withWebviewCsp } from './webviewHtml';
import { Language, localizeGraphHtml, tx } from './i18n';

export class GraphViewProvider implements vscode.WebviewViewProvider {
  private view?: vscode.WebviewView;
  private content?: string;
  private focusedPath?: string;
  constructor(private language: Language = 'es') {}
  setLanguage(language: Language): void { this.language = language; if (this.view) this.view.title = tx(language, 'Grafo del proyecto', 'Project graph'); this.refresh(); }

  private refresh(): void {
    if (this.view) this.view.webview.html = this.content
      ? withWebviewCsp(localizeGraphHtml(this.content, this.language), randomBytes(16).toString('hex'))
      : `<!doctype html><html lang="${this.language}"><meta charset="utf-8"><body style="font:14px system-ui;padding:16px;color:#9fb5cc;background:#101a28">${tx(this.language, 'Analiza la carpeta abierta para explorar su grafo.', 'Analyze the open folder to explore its graph.')}</body></html>`;
  }

  resolveWebviewView(view: vscode.WebviewView): void {
    this.view = view;
    view.title = tx(this.language, 'Grafo del proyecto', 'Project graph');
    view.webview.options = { enableScripts: true, localResourceRoots: [] };
    this.refresh();
    if (this.focusedPath) setTimeout(() => this.postFocus(), 250);
  }

  update(html: string): void {
    this.content = html;
    this.refresh();
    if (this.view && this.focusedPath) setTimeout(() => this.postFocus(), 250);
  }

  focus(relativePath: string): void {
    this.focusedPath = relativePath;
    void vscode.commands.executeCommand('safecode.graph.focus').then(() => {
      this.view?.show(true);
      setTimeout(() => this.postFocus(), 100);
    });
  }

  private postFocus(): void {
    if (this.view && this.focusedPath) void this.view.webview.postMessage({ type: 'focus', id: 'file:' + this.focusedPath });
  }

  clear(): void { this.content = undefined; this.focusedPath = undefined; this.refresh(); }
}
