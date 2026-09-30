import * as path from 'node:path';
import * as vscode from 'vscode';
import { Finding, GraphNode, GraphSnapshot } from './types';
import { Language, localizeFinding, tx } from './i18n';
import { buildFindingIndex, FindingCounts, FindingIndex } from './findingIndex';

type FileEntry = { kind: 'file'; node: GraphNode; related: boolean };
type FolderEntry = { kind: 'folder'; path: string };
type RelationEntry = { kind: 'relation'; file: GraphNode; direction: 'incoming' | 'outgoing'; paths: string[] };
type EmptyEntry = { kind: 'empty'; label: string };
type FileTreeEntry = FileEntry | FolderEntry | RelationEntry | EmptyEntry;

export class FileTreeProvider implements vscode.TreeDataProvider<FileTreeEntry> {
  private readonly changed = new vscode.EventEmitter<FileTreeEntry | undefined>();
  readonly onDidChangeTreeData = this.changed.event;
  private snapshot?: GraphSnapshot;
  private index: FindingIndex = buildFindingIndex([]);
  private byId = new Map<string, GraphNode>();
  private iconRoot?: string;
  constructor(private language: Language = 'es') {}
  setLanguage(language: Language): void { this.language = language; this.changed.fire(undefined); }
  setIconRoot(root: string): void { this.iconRoot = root; this.changed.fire(undefined); }

  update(snapshot: GraphSnapshot, findings: Finding[]): void {
    this.snapshot = snapshot;
    this.index = buildFindingIndex(findings);
    this.byId = new Map(snapshot.nodes.map(node => [node.id, node]));
    this.changed.fire(undefined);
  }

  clear(): void { this.snapshot = undefined; this.byId.clear(); this.index = buildFindingIndex([]); this.changed.fire(undefined); }

  private countLabel(counts?: FindingCounts): string | undefined {
    if (!counts) return undefined;
    const count = counts.errors + counts.warnings;
    return `${count} ${tx(this.language, `hallazgo${count === 1 ? '' : 's'}`, `finding${count === 1 ? '' : 's'}`)}`;
  }

  private countTooltip(counts: FindingCounts): string {
    return tx(this.language, `${counts.errors} errores · ${counts.warnings} advertencias`,
      `${counts.errors} errors · ${counts.warnings} warnings`);
  }

  private folderIcon(counts?: FindingCounts): vscode.TreeItem['iconPath'] {
    if (!counts || !this.iconRoot) return new vscode.ThemeIcon('folder');
    const severity = counts.errors ? 'error' : 'warning';
    return {
      light: vscode.Uri.file(path.join(this.iconRoot, `folder-${severity}-light.svg`)),
      dark: vscode.Uri.file(path.join(this.iconRoot, `folder-${severity}-dark.svg`)),
    };
  }

  getChildren(entry?: FileTreeEntry): FileTreeEntry[] {
    if (!this.snapshot) return [{ kind: 'empty', label: tx(this.language, 'Analiza la carpeta para ver sus archivos.', 'Analyze the folder to see its files.') }];
    if (!entry || entry.kind === 'folder') {
      const parent = entry?.kind === 'folder' ? entry.path : '.';
      const folders = this.snapshot.directories.filter(dir => dir.path !== '.' && path.posix.dirname(dir.path) === parent)
        .map(dir => ({ kind: 'folder', path: dir.path } as FolderEntry));
      const files = this.snapshot.nodes.filter(node => node.directory === parent)
        .map(node => ({ kind: 'file', node, related: false } as FileEntry));
      return [...folders, ...files].sort((a, b) => {
        if (a.kind !== b.kind) return a.kind === 'folder' ? -1 : 1;
        return (a.kind === 'folder' ? a.path : a.node.path).localeCompare(b.kind === 'folder' ? b.path : b.node.path);
      });
    }
    if (entry.kind === 'file' && !entry.related) {
      const incoming = new Set<string>(); const outgoing = new Set<string>();
      for (const edge of this.snapshot.edges) {
        if (edge.target === entry.node.id) incoming.add(edge.source);
        if (edge.source === entry.node.id) outgoing.add(edge.target);
      }
      return [
        { kind: 'relation', file: entry.node, direction: 'incoming', paths: [...incoming].sort() },
        { kind: 'relation', file: entry.node, direction: 'outgoing', paths: [...outgoing].sort() },
      ];
    }
    if (entry.kind === 'relation') return entry.paths.map(id => this.byId.get(id)).filter((n): n is GraphNode => Boolean(n))
      .map(node => ({ kind: 'file', node, related: true }));
    return [];
  }

  getTreeItem(entry: FileTreeEntry): vscode.TreeItem {
    if (entry.kind === 'empty') return new vscode.TreeItem(entry.label);
    if (entry.kind === 'folder') {
      const item = new vscode.TreeItem(path.posix.basename(entry.path), vscode.TreeItemCollapsibleState.Collapsed);
      const counts = this.index.folders.get(entry.path);
      item.iconPath = this.folderIcon(counts);
      item.description = this.countLabel(counts);
      item.tooltip = counts ? `${entry.path}\n${this.countTooltip(counts)}` : entry.path;
      return item;
    }
    if (entry.kind === 'relation') {
      const incoming = entry.direction === 'incoming';
      const item = new vscode.TreeItem(`${incoming ? tx(this.language, 'Lo importan', 'Imported by') : tx(this.language, 'Importa a', 'Imports')} (${entry.paths.length})`,
        entry.paths.length ? vscode.TreeItemCollapsibleState.Collapsed : vscode.TreeItemCollapsibleState.None);
      item.iconPath = new vscode.ThemeIcon(incoming ? 'arrow-left' : 'arrow-right');
      return item;
    }
    const item = new vscode.TreeItem(path.posix.basename(entry.node.path),
      entry.related ? vscode.TreeItemCollapsibleState.None : vscode.TreeItemCollapsibleState.Collapsed);
    const counts = this.index.files.get(entry.node.path);
    item.description = this.countLabel(counts) || (entry.related ? entry.node.directory : undefined);
    item.tooltip = `${entry.node.path}\n${entry.node.language || tx(this.language, 'Sin parser', 'No parser')} · ${entry.node.status}${counts ? `\n${this.countTooltip(counts)}` : ''}`;
    item.iconPath = counts?.errors
      ? new vscode.ThemeIcon('error', new vscode.ThemeColor('problemsErrorIcon.foreground'))
      : counts?.warnings
        ? new vscode.ThemeIcon('warning', new vscode.ThemeColor('problemsWarningIcon.foreground'))
        : new vscode.ThemeIcon('file-code');
    item.contextValue = 'safecodeFile';
    item.command = { command: 'safecode.openFile', title: tx(this.language, 'Abrir archivo', 'Open file'), arguments: [entry.node.path] };
    return item;
  }
}

type FindingEntry = { kind: 'finding'; finding: Finding } | { kind: 'rule'; id: string; title: string; findings: Finding[] } | EmptyEntry;
const TITLES_ES: Record<string, string> = {
  'SEG-01': 'SQL con entrada externa', 'SEG-02': 'Comandos de shell', 'SEG-03': 'Credenciales literales',
  'ARQ-01': 'Ciclos nuevos', 'ARQ-02': 'Capas prohibidas',
};
const TITLES_EN: Record<string, string> = {
  'SEG-01': 'SQL with external input', 'SEG-02': 'Shell commands', 'SEG-03': 'Hard-coded credentials',
  'ARQ-01': 'New cycles', 'ARQ-02': 'Forbidden layers',
};

export class FindingsTreeProvider implements vscode.TreeDataProvider<FindingEntry> {
  private readonly changed = new vscode.EventEmitter<FindingEntry | undefined>();
  readonly onDidChangeTreeData = this.changed.event;
  private findings?: Finding[];
  readonly coverage: Record<string, string> = {};
  constructor(private language: Language = 'es') {}
  setLanguage(language: Language): void { this.language = language; this.changed.fire(undefined); }

  update(findings: Finding[], coverage: Record<string, string>): void {
    this.findings = findings;
    Object.keys(this.coverage).forEach(key => delete this.coverage[key]);
    Object.assign(this.coverage, coverage);
    this.changed.fire(undefined);
  }
  clear(): void { this.findings = undefined; this.changed.fire(undefined); }
  getChildren(entry?: FindingEntry): FindingEntry[] {
    if (!this.findings) return [{ kind: 'empty', label: tx(this.language, 'Analiza la carpeta para ver hallazgos.', 'Analyze the folder to see findings.') }];
    if (entry?.kind === 'rule') return entry.findings.map(finding => ({ kind: 'finding', finding }));
    if (entry) return [];
    return Object.entries(this.language === 'es' ? TITLES_ES : TITLES_EN).map(([id, title]) => ({ kind: 'rule', id, title,
      findings: this.findings!.filter(finding => finding.rule_id === id) }));
  }
  getTreeItem(entry: FindingEntry): vscode.TreeItem {
    if (entry.kind === 'empty') return new vscode.TreeItem(entry.label);
    if (entry.kind === 'rule') {
      const status = this.coverage[entry.id] === 'skipped' ? tx(this.language, ' · omitida', ' · skipped') : '';
      const item = new vscode.TreeItem(`${entry.id} · ${entry.title} (${entry.findings.length})${status}`,
        entry.findings.length ? vscode.TreeItemCollapsibleState.Collapsed : vscode.TreeItemCollapsibleState.None);
      item.iconPath = new vscode.ThemeIcon(entry.findings.length ? 'warning' : 'check');
      return item;
    }
    const finding = entry.finding;
    const line = finding.start?.line;
    const item = new vscode.TreeItem(`${finding.path}${line ? `:${line}` : ''}`);
    item.description = finding.severity === 'high' ? tx(this.language, 'error', 'error') : tx(this.language, 'advertencia', 'warning');
    item.iconPath = new vscode.ThemeIcon(finding.severity === 'high' ? 'error' : 'warning');
    const localized = localizeFinding(finding, this.language);
    item.tooltip = `${localized.title}\n${localized.explanation}\n${localized.evidence}`;
    item.command = { command: 'safecode.openFinding', title: tx(this.language, 'Abrir hallazgo', 'Open finding'), arguments: [finding] };
    return item;
  }
}
