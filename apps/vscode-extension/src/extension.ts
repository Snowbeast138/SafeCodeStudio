import * as fs from 'node:fs';
import * as path from 'node:path';
import * as vscode from 'vscode';
import { publishDiagnostics } from './diagnostics';
import { GraphViewProvider } from './graphView';
import { byteColumnToUtf16 } from './positions';
import { FileTreeProvider, FindingsTreeProvider } from './tree';
import { findingHtml, OverviewProvider, reportHtml } from './panels';
import { resolvePython } from './pythonRuntime';
import { AnalysisResult, Finding, GraphSnapshot } from './types';
import { WorkerClient } from './worker';
import { Language, resolveLanguage, tx } from './i18n';

class SafeCodeController implements vscode.Disposable {
  private readonly files = new FileTreeProvider();
  private readonly findings = new FindingsTreeProvider();
  private readonly graph = new GraphViewProvider();
  private readonly logo: string;
  private readonly overview: OverviewProvider;
  private readonly diagnostics = vscode.languages.createDiagnosticCollection('SafeCode');
  private readonly output = vscode.window.createOutputChannel('SafeCode');
  private readonly status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left);
  private readonly disposables: vscode.Disposable[] = [];
  private folder?: vscode.WorkspaceFolder;
  private worker?: WorkerClient;
  private workerPromise?: Promise<WorkerClient>;
  private version = 0;
  private generation = 0;
  private lastResult?: AnalysisResult;
  private lastSnapshot?: GraphSnapshot;
  private detailPanel?: vscode.WebviewPanel;
  private lastFinding?: Finding;
  private language: Language = 'es';
  private fileView?: vscode.TreeView<any>;
  private findingView?: vscode.TreeView<any>;

  constructor(private readonly context: vscode.ExtensionContext) {
    this.files.setIconRoot(path.join(context.extensionPath, 'media'));
    this.language = this.readLanguage();
    this.files.setLanguage(this.language); this.findings.setLanguage(this.language); this.graph.setLanguage(this.language);
    this.logo = 'data:image/svg+xml,' + encodeURIComponent(fs.readFileSync(path.join(context.extensionPath, 'media', 'safecode.svg'), 'utf8'));
    this.overview = new OverviewProvider(this.logo, this.language);
    const fileView = vscode.window.createTreeView('safecode.files', { treeDataProvider: this.files });
    const findingView = vscode.window.createTreeView('safecode.findings', { treeDataProvider: this.findings });
    this.fileView = fileView; this.findingView = findingView;
    this.refreshViewTitles();
    this.disposables.push(fileView, findingView, this.diagnostics, this.output, this.status,
      vscode.window.registerWebviewViewProvider('safecode.graph', this.graph),
      vscode.window.registerWebviewViewProvider('safecode.overview', this.overview),
      vscode.commands.registerCommand('safecode.analyze', () => this.analyze()),
      vscode.commands.registerCommand('safecode.selectPython', () => this.selectPython()),
      vscode.commands.registerCommand('safecode.exportReport', () => this.exportReport()),
      vscode.commands.registerCommand('safecode.chooseLanguage', () => this.chooseLanguage()),
      vscode.commands.registerCommand('safecode.selectWorkspace', () => this.selectWorkspace()),
      vscode.commands.registerCommand('safecode.openFile', (relative: string) => this.openFile(relative)),
      vscode.commands.registerCommand('safecode.openFinding', (finding: Finding) => this.openFinding(finding)),
      vscode.commands.registerCommand('safecode.focusGraph', (item: unknown) => {
        const node = item as { node?: { path?: string } };
        if (node?.node?.path) this.graph.focus(node.node.path);
      }),
      vscode.workspace.onDidSaveTextDocument(document => {
        if (this.folder && this.isInside(document.uri, this.folder) &&
            vscode.workspace.getConfiguration('safecode').get<boolean>('analyzeOnSave', true)) void this.analyze();
      }),
      vscode.workspace.onDidChangeWorkspaceFolders(() => {
        if (!this.folder) { this.folder = vscode.workspace.workspaceFolders?.[0]; if (this.folder) void this.analyze(); return; }
        if (this.folder && !vscode.workspace.workspaceFolders?.some(item => item.uri.toString() === this.folder?.uri.toString())) {
          this.restart(); this.folder = vscode.workspace.workspaceFolders?.[0]; void this.analyze();
        }
      }),
      vscode.workspace.onDidChangeConfiguration(event => {
        if (event.affectsConfiguration('safecode.language')) this.applyLanguage();
        if (['pythonPath', 'baselinePath', 'policyPath'].some(key => event.affectsConfiguration('safecode.' + key))) {
          this.restart(); void this.analyze();
        }
      }),
    );
    this.status.command = 'safecode.analyze';
    this.status.text = '$(shield) SafeCode';
    this.status.tooltip = tx(this.language, 'Analizar la carpeta con SafeCode', 'Analyze the folder with SafeCode');
    this.status.show();
    this.folder = vscode.workspace.workspaceFolders?.[0];
    this.overview.update(undefined, this.folder?.name);
    if (this.folder) void this.analyze();
  }

  private readLanguage(): Language {
    return resolveLanguage(vscode.workspace.getConfiguration('safecode').get<string>('language', 'auto'), vscode.env.language);
  }

  private refreshViewTitles(): void {
    if (this.fileView) this.fileView.title = tx(this.language, 'Archivos y relaciones', 'Files and relationships');
    if (this.findingView) this.findingView.title = tx(this.language, 'Hallazgos', 'Findings');
  }

  private applyLanguage(): void {
    this.language = this.readLanguage();
    this.refreshViewTitles();
    this.files.setLanguage(this.language); this.findings.setLanguage(this.language);
    this.graph.setLanguage(this.language); this.overview.setLanguage(this.language);
    this.worker?.setLanguage(this.language);
    if (this.lastResult && this.folder) {
      void publishDiagnostics(this.diagnostics, this.folder, this.lastResult.findings, this.language);
      this.status.text = `$(shield) SafeCode: ${this.lastResult.metrics.findings} ${tx(this.language, 'hallazgos', 'findings')}`;
      this.status.tooltip = `${this.folder.name}: ${this.lastResult.metrics.files} ${tx(this.language, 'archivos', 'files')} · ${this.lastResult.status === 'complete' ? tx(this.language, 'completo', 'complete') : tx(this.language, 'parcial', 'partial')}`;
    } else this.status.tooltip = tx(this.language, 'Analizar la carpeta con SafeCode', 'Analyze the folder with SafeCode');
    if (this.lastFinding && this.detailPanel) this.detailPanel.webview.html = findingHtml(this.logo, this.lastFinding, this.lastSnapshot, this.language);
  }

  private async chooseLanguage(): Promise<void> {
    const options = [
      { label: tx(this.language, 'Automático (idioma de VS Code)', 'Automatic (VS Code display language)'), value: 'auto' },
      { label: 'Español', value: 'es' },
      { label: 'English', value: 'en' },
    ];
    const chosen = await vscode.window.showQuickPick(options, { placeHolder: tx(this.language, 'Idioma de SafeCode Studio', 'SafeCode Studio language') });
    if (!chosen) return;
    await vscode.workspace.getConfiguration('safecode').update('language', chosen.value, vscode.ConfigurationTarget.Global);
    this.applyLanguage();
  }

  private isInside(uri: vscode.Uri, folder: vscode.WorkspaceFolder): boolean {
    if (uri.scheme !== 'file') return false;
    const relative = path.relative(folder.uri.fsPath, uri.fsPath);
    return relative !== '' && !relative.startsWith('..') && !path.isAbsolute(relative);
  }

  private configuredPath(value: string, root: string): string | undefined {
    if (!value.trim()) return undefined;
    return path.isAbsolute(value) ? value : path.resolve(root, value);
  }

  private async selectPython(): Promise<void> {
    const selection = await vscode.window.showOpenDialog({ canSelectFiles: true, canSelectFolders: false, canSelectMany: false,
      title: tx(this.language, 'Selecciona Python del entorno de SafeCode', 'Select Python from the SafeCode environment'), openLabel: tx(this.language, 'Usar este Python', 'Use this Python') });
    if (!selection?.[0]) return;
    await vscode.workspace.getConfiguration('safecode').update('pythonPath', selection[0].fsPath, vscode.ConfigurationTarget.Global);
    this.restart();
    await this.analyze();
  }

  private async selectWorkspace(): Promise<void> {
    const folders = vscode.workspace.workspaceFolders || [];
    if (!folders.length) { void vscode.window.showInformationMessage(tx(this.language, 'Abre una carpeta en VS Code para analizarla.', 'Open a folder in VS Code to analyze it.')); return; }
    const choice = await vscode.window.showQuickPick(folders.map(folder => ({ label: folder.name, description: folder.uri.fsPath, folder })));
    if (!choice) return;
    if (this.folder?.uri.toString() !== choice.folder.uri.toString()) { this.restart(); this.folder = choice.folder; }
    await this.analyze();
  }

  private restart(): void {
    this.stopWorker();
    this.files.clear(); this.findings.clear(); this.graph.clear(); this.diagnostics.clear();
    this.lastResult = undefined; this.lastSnapshot = undefined;
    this.overview.update(undefined, this.folder?.name);
  }

  private stopWorker(): void {
    this.generation += 1;
    this.worker?.dispose(); this.worker = undefined; this.workerPromise = undefined; this.version = 0;
  }

  private async ensureWorker(folder: vscode.WorkspaceFolder): Promise<WorkerClient> {
    if (this.worker) return this.worker;
    if (this.workerPromise) return this.workerPromise;
    const generation = this.generation;
    this.workerPromise = this.createWorker(folder).then(worker => {
      if (generation !== this.generation) { worker.dispose(); throw new Error(tx(this.language, 'Análisis reemplazado.', 'Analysis superseded.')); }
      this.worker = worker;
      return worker;
    }).finally(() => { this.workerPromise = undefined; });
    return this.workerPromise;
  }

  private async createWorker(folder: vscode.WorkspaceFolder): Promise<WorkerClient> {
    const config = vscode.workspace.getConfiguration('safecode', folder.uri);
    const baseline = this.configuredPath(config.get<string>('baselinePath', ''), folder.uri.fsPath);
    const policy = this.configuredPath(config.get<string>('policyPath', ''), folder.uri.fsPath);
    if (policy && !baseline) throw new Error(tx(this.language, 'Configura safecode.baselinePath para usar una política de capas.', 'Set safecode.baselinePath to use a layer policy.'));
    const python = await resolvePython(folder.uri.fsPath, this.context.extensionPath, config.get<string>('pythonPath', ''), this.language);
    return new WorkerClient(folder.uri.fsPath, python,
      this.context.extensionPath, baseline, policy, this.output, this.language);
  }

  private async analyze(): Promise<void> {
    const folder = this.folder || vscode.workspace.workspaceFolders?.[0];
    if (!folder) { void vscode.window.showInformationMessage(tx(this.language, 'Abre una carpeta en VS Code para analizarla.', 'Open a folder in VS Code to analyze it.')); return; }
    this.folder = folder;
    let worker: WorkerClient;
    try { worker = await this.ensureWorker(folder); }
    catch (error) { this.status.text = '$(error) SafeCode: error'; this.overview.update(undefined, folder.name, error instanceof Error ? error.message : String(error)); this.reportError(error); return; }
    const version = ++this.version;
    const generation = this.generation;
    this.status.text = `$(sync~spin) SafeCode: ${tx(this.language, 'analizando', 'analyzing')}`;
    try {
      const result = await worker.request<AnalysisResult>('analyze', { version });
      if (this.generation !== generation || version !== this.version || worker !== this.worker) return;
      await publishDiagnostics(this.diagnostics, folder, result.findings, this.language);
      if (this.generation !== generation || version !== this.version || worker !== this.worker) return;
      this.findings.update(result.findings, result.coverage);
      const [snapshot, html] = await Promise.all([
        worker.request<GraphSnapshot>('graph'), worker.request<string>('graphHtml'),
      ]);
      if (this.generation !== generation || version !== this.version || worker !== this.worker) return;
      this.files.update(snapshot, result.findings);
      this.graph.update(html);
      this.lastResult = result; this.lastSnapshot = snapshot;
      this.overview.update(result, folder.name);
      this.status.text = `$(shield) SafeCode: ${result.metrics.findings} ${tx(this.language, 'hallazgos', 'findings')}`;
      this.status.tooltip = `${folder.name}: ${result.metrics.files} ${tx(this.language, 'archivos', 'files')} · ${result.status === 'complete' ? tx(this.language, 'completo', 'complete') : tx(this.language, 'parcial', 'partial')} · ${result.metrics.parsed_files} ${tx(this.language, 'CST actualizados', 'CSTs updated')}`;
      this.output.appendLine(tx(this.language, `Versión ${version}: ${result.metrics.files} archivos, ${result.metrics.findings} hallazgos, ${result.metrics.parsed_files} CST actualizados.`, `Version ${version}: ${result.metrics.files} files, ${result.metrics.findings} findings, ${result.metrics.parsed_files} CSTs updated.`));
    } catch (error) {
      if (this.generation !== generation || version !== this.version) return;
      this.status.text = '$(error) SafeCode: error';
      this.overview.update(undefined, folder.name, error instanceof Error ? error.message : String(error));
      this.reportError(error);
      this.stopWorker(); // Keep the last verified findings visible after a worker failure.
    }
  }

  private reportError(error: unknown): void {
    const message = error instanceof Error ? error.message : String(error);
    this.output.appendLine(message);
    const pythonProblem = /Python|tree.sitter|networkx|gramáticas|grammars/i.test(message);
    const choose = tx(this.language, 'Elegir Python', 'Choose Python');
    const show = tx(this.language, 'Ver salida', 'Show output');
    void vscode.window.showErrorMessage(`SafeCode: ${message}`, ...(pythonProblem ? [choose, show] : [show])).then(choice => {
      if (choice === show) this.output.show();
      if (choice === choose) void this.selectPython();
    });
  }

  private async exportReport(): Promise<void> {
    if (!this.lastResult || !this.folder) { void vscode.window.showInformationMessage(tx(this.language, 'Analiza primero la carpeta para exportar el reporte.', 'Analyze the folder before exporting a report.')); return; }
    const target = await vscode.window.showSaveDialog({ defaultUri: vscode.Uri.file(path.join(this.folder.uri.fsPath, 'safecode-report.html')),
      filters: { HTML: ['html'] }, saveLabel: tx(this.language, 'Guardar reporte SafeCode', 'Save SafeCode report') });
    if (!target) return;
    await vscode.workspace.fs.writeFile(target, Buffer.from(reportHtml(this.logo, this.folder.name, this.lastResult, this.language), 'utf8'));
    await vscode.commands.executeCommand('vscode.open', target);
  }

  private async openFile(relative: string): Promise<void> {
    if (!this.folder) return;
    const target = path.resolve(this.folder.uri.fsPath, relative);
    const check = path.relative(this.folder.uri.fsPath, target);
    if (check.startsWith('..') || path.isAbsolute(check)) return;
    await vscode.window.showTextDocument(vscode.Uri.file(target), { preview: true });
  }

  private async openFinding(finding: Finding): Promise<void> {
    if (!this.folder) return;
    const target = path.resolve(this.folder.uri.fsPath, finding.path);
    const check = path.relative(this.folder.uri.fsPath, target);
    if (check.startsWith('..') || path.isAbsolute(check)) return;
    const document = await vscode.workspace.openTextDocument(vscode.Uri.file(target));
    const line = Math.max(0, Math.min((finding.start?.line ?? 1) - 1, document.lineCount - 1));
    const column = byteColumnToUtf16(document.lineAt(line).text, finding.start?.byte_column ?? 0);
    const position = new vscode.Position(line, column);
    await vscode.window.showTextDocument(document, { preview: true, selection: new vscode.Range(position, position) });
    if (!this.detailPanel) {
      this.detailPanel = vscode.window.createWebviewPanel('safecode.findingDetail', tx(this.language, 'SafeCode · detalle', 'SafeCode · details'), vscode.ViewColumn.Beside,
        { enableScripts: false, retainContextWhenHidden: true });
      this.detailPanel.onDidDispose(() => { this.detailPanel = undefined; });
    }
    this.detailPanel.title = `${finding.rule_id} · ${path.basename(finding.path)}`;
    this.lastFinding = finding;
    this.detailPanel.webview.html = findingHtml(this.logo, finding, this.lastSnapshot, this.language);
    this.detailPanel.reveal(vscode.ViewColumn.Beside, true);
  }

  dispose(): void { this.restart(); for (const disposable of this.disposables) disposable.dispose(); }
}

export function activate(context: vscode.ExtensionContext): void {
  context.subscriptions.push(new SafeCodeController(context));
}

export function deactivate(): void { /* ExtensionContext disposes the controller. */ }
