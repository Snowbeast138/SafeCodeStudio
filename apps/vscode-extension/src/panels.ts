import * as vscode from 'vscode';
import { AnalysisResult, Finding, GraphSnapshot } from './types';
import { Language, localizeFinding, statusLabel, tx } from './i18n';

const escape = (value: unknown): string => String(value ?? '').replace(/[&<>"']/g, char =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]!));

const style = `
  :root{color-scheme:light dark}*{box-sizing:border-box}body{margin:0;font:13px var(--vscode-font-family);color:var(--vscode-foreground);background:var(--vscode-editor-background)}
  .wrap{padding:16px;max-width:980px;margin:auto}.brand{display:flex;align-items:center;gap:12px}.brand img{width:42px;height:42px;object-fit:contain}
  h1{font-size:20px;margin:0;color:var(--vscode-textLink-foreground)}h2{font-size:15px;margin:0 0 10px}p{line-height:1.5;margin:8px 0}.muted{color:var(--vscode-descriptionForeground)}
  .toolbar{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}.button{border:1px solid var(--vscode-button-border,transparent);background:var(--vscode-button-background);color:var(--vscode-button-foreground);padding:8px 12px;border-radius:7px;cursor:pointer}.secondary{background:var(--vscode-button-secondaryBackground);color:var(--vscode-button-secondaryForeground)}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:9px}.card{border:1px solid var(--vscode-panel-border);background:var(--vscode-editorWidget-background);border-radius:10px;padding:12px;margin:10px 0}.metric strong{font-size:20px;display:block;margin-top:6px}.label{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--vscode-descriptionForeground)}
  .alert{border-left:4px solid var(--vscode-errorForeground);background:var(--vscode-inputValidation-errorBackground,var(--vscode-editorWidget-background))}.alert h2{color:var(--vscode-errorForeground)}.warn{border-left:4px solid var(--vscode-editorWarning-foreground)}
  pre{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--vscode-textCodeBlock-background);padding:12px;border-radius:6px;border-left:3px solid var(--vscode-textLink-foreground)}
  .links{display:flex;gap:7px;flex-wrap:wrap}.chip{border:1px solid var(--vscode-panel-border);padding:5px 7px;border-radius:6px;overflow-wrap:anywhere}.good{color:var(--vscode-testing-iconPassed)}
`;

function document(body: string, language: Language): string {
  return `<!doctype html><html lang="${language}"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline';"><meta name="viewport" content="width=device-width,initial-scale=1"><style>${style}</style></head><body>${body}<script>const vscode=typeof acquireVsCodeApi==='function'?acquireVsCodeApi():null;if(vscode)document.querySelectorAll('[data-command]').forEach(el=>el.addEventListener('click',()=>vscode.postMessage({command:el.dataset.command})));</script></body></html>`;
}

function brand(logo: string, language: Language): string { return `<div class="brand"><img src="${logo}" alt=""><div><h1>SafeCode Studio</h1><div class="muted">${tx(language, 'Análisis local de código y relaciones', 'Local code and dependency analysis')}</div></div></div>`; }

export function overviewHtml(logo: string, result?: AnalysisResult, project?: string, message?: string, language: Language = 'es'): string {
  const guidance = result?.coverage['ARQ-01'] === 'skipped'
    ? `<div class="card warn"><h2>${tx(language, 'ARQ-01 aún no se evaluó', 'ARQ-01 has not been evaluated')}</h2><p>${tx(language, 'Selecciona una revisión en Base Git. SafeCode comparará esa versión con los archivos actuales; cambiar de rama en VS Code no configura la base automáticamente.', 'Select a revision under Git baseline. SafeCode compares it with the current files; switching branches in VS Code does not configure the baseline automatically.')}</p><button class="button" data-command="baseline">${tx(language, 'Configurar base Git', 'Configure Git baseline')}</button></div>`
    : result?.coverage['ARQ-02'] === 'skipped'
      ? `<div class="card warn"><h2>${tx(language, 'ARQ-02 aún no se evaluó', 'ARQ-02 has not been evaluated')}</h2><p>${tx(language, 'La base ya está activa. Define qué carpetas no deben depender entre sí para evaluar la regla de capas.', 'The baseline is active. Define which folders must not depend on each other to evaluate the layer rule.')}</p><button class="button" data-command="policy">${tx(language, 'Configurar política', 'Configure policy')}</button></div>`
      : '';
  const status = result ? `<div class="grid"><div class="card metric"><span class="label">${tx(language, 'Archivos', 'Files')}</span><strong>${result.metrics.files}</strong></div><div class="card metric"><span class="label">${tx(language, 'Hallazgos', 'Findings')}</span><strong>${result.metrics.findings}</strong></div></div><p class="muted">${tx(language, 'Estado', 'Status')}: ${statusLabel(language, result.status)} · ${Object.values(result.coverage).filter(value => value === 'analyzed').length}/5 ${tx(language, 'reglas ejecutadas', 'rules evaluated')}</p><div class="card"><span class="label">${tx(language, 'Base de comparación', 'Comparison baseline')}</span><p>${result.baseline?.kind === 'git' ? `${escape(result.baseline.ref)} · ${escape(result.baseline.commit.slice(0, 8))}` : result.baseline?.kind === 'directory' ? escape(result.baseline.path) : tx(language, 'Sin configurar', 'Not configured')}</p><span class="label">${tx(language, 'Política de capas', 'Layer policy')}</span><p>${result.coverage['ARQ-02'] === 'analyzed' ? tx(language, 'Activa', 'Active') : tx(language, 'Pendiente', 'Pending')}</p></div>`
    : `<p class="muted">${escape(message || tx(language, 'Abre una carpeta y analiza el proyecto para ver su estado.', 'Open a folder and analyze the project to see its status.'))}</p>`;
  return document(`<div class="wrap">${brand(logo, language)}<p class="muted">${escape(project || tx(language, 'Sin proyecto abierto', 'No project open'))}</p><div class="toolbar"><button class="button" data-command="analyze">▶ ${tx(language, 'Analizar', 'Analyze')}</button><button class="button secondary" data-command="baseline">◫ ${tx(language, 'Base Git', 'Git baseline')}</button><button class="button secondary" data-command="policy">⇄ ${tx(language, 'Política de capas', 'Layer policy')}</button><button class="button secondary" data-command="export">↓ ${tx(language, 'Exportar reporte', 'Export report')}</button><button class="button secondary" data-command="python">⚙ Python</button><button class="button secondary" data-command="language">🌐 ${tx(language, 'Idioma', 'Language')}</button></div>${status}${guidance}<p class="muted">${tx(language, 'ARQ-01 y ARQ-02 reportan cambios nuevos respecto de la base; cero hallazgos significa que se evaluaron sin detectar esos cambios.', 'ARQ-01 and ARQ-02 report new changes relative to the baseline; zero findings means they were evaluated without detecting those changes.')}</p></div>`, language);
}

export function findingHtml(logo: string, finding: Finding, snapshot?: GraphSnapshot, language: Language = 'es'): string {
  finding = localizeFinding(finding, language);
  const related = snapshot?.edges.filter(edge => edge.source === `file:${finding.path}` || edge.target === `file:${finding.path}`) || [];
  const nodeById = new Map(snapshot?.nodes.map(node => [node.id, node.path]) || []);
  const dependencies = related.slice(0, 14).map(edge => {
    const other = edge.source === `file:${finding.path}` ? edge.target : edge.source;
    return `<span class="chip">${escape(nodeById.get(other) || other)}</span>`;
  }).join('');
  const high = finding.severity === 'high';
  const severity = high ? tx(language, 'Alta', 'High') : tx(language, 'Media', 'Medium');
  const line = finding.start?.line ?? '—';
  return document(`<div class="wrap">${brand(logo, language)}<div class="card ${high ? 'alert' : 'warn'}"><span class="label">${tx(language, 'Hallazgo detectado', 'Finding detected')}</span><h2>${escape(finding.title)}</h2><p>${escape(finding.explanation)}</p></div><div class="grid"><div class="card"><span class="label">${tx(language, 'Regla', 'Rule')}</span><p><strong>${escape(finding.rule_id)}</strong></p></div><div class="card"><span class="label">${tx(language, 'Severidad', 'Severity')}</span><p><strong>${severity}</strong></p></div><div class="card"><span class="label">${tx(language, 'Análisis', 'Analysis')}</span><p><strong>${tx(language, 'Determinista', 'Deterministic')}</strong></p></div></div><section class="card"><h2>${tx(language, 'Evidencia', 'Evidence')}</h2><pre>${escape(finding.evidence)}</pre><p class="muted">${escape(finding.path)} · ${tx(language, 'línea', 'line')} ${line}</p></section><section class="card"><h2>${tx(language, 'Dependencias relacionadas', 'Related dependencies')}</h2><div class="links">${dependencies || `<span class="muted">${tx(language, 'Sin relaciones directas en el grafo.', 'No direct relationships in the graph.')}</span>`}</div></section><p class="muted">${tx(language, 'Este hallazgo procede de las reglas locales de SafeCode. Revisa el contexto antes de corregirlo.', 'This finding comes from SafeCode local rules. Review the context before fixing it.')}</p></div>`, language);
}

export function reportHtml(logo: string, project: string, result: AnalysisResult, language: Language = 'es'): string {
  const findings = result.findings.map(raw => { const finding = localizeFinding(raw, language); return `<section class="card ${finding.severity === 'high' ? 'alert' : 'warn'}"><span class="label">${escape(finding.rule_id)} · ${finding.severity === 'high' ? tx(language, 'alta', 'high') : tx(language, 'media', 'medium')}</span><h2>${escape(finding.title)}</h2><p>${escape(finding.explanation)}</p><pre>${escape(finding.evidence)}</pre><p class="muted">${escape(finding.path)}:${finding.start?.line ?? '—'}</p></section>`; }).join('');
  return document(`<div class="wrap">${brand(logo, language)}<h2>${tx(language, 'Reporte de análisis', 'Analysis report')} · ${escape(project)}</h2><p>${result.metrics.files} ${tx(language, 'archivos', 'files')} · ${result.metrics.findings} ${tx(language, 'hallazgos', 'findings')} · ${tx(language, 'estado', 'status')} ${statusLabel(language, result.status)}</p><p>${tx(language, 'Base de comparación', 'Comparison baseline')}: ${result.baseline?.kind === 'git' ? `${escape(result.baseline.ref)} (${escape(result.baseline.commit)})` : result.baseline?.kind === 'directory' ? escape(result.baseline.path) : tx(language, 'sin configurar', 'not configured')}</p>${findings || `<p class="good">${tx(language, 'Sin hallazgos en las reglas ejecutadas.', 'No findings in the evaluated rules.')}</p>`}<section class="card"><h2>${tx(language, 'Cobertura de reglas', 'Rule coverage')}</h2>${Object.entries(result.coverage).map(([key, value]) => `<p>${escape(key)}: ${value === 'skipped' ? tx(language, 'omitida', 'skipped') : tx(language, 'analizada', 'analyzed')}</p>`).join('')}</section></div>`, language);
}

export class OverviewProvider implements vscode.WebviewViewProvider {
  private view?: vscode.WebviewView;
  private result?: AnalysisResult;
  private project?: string;
  private message?: string;
  constructor(private readonly logo: string, private language: Language = 'es') {}
  setLanguage(language: Language): void { this.language = language; if (this.view) this.view.title = tx(language, 'Resumen', 'Overview'); this.refresh(); }
  resolveWebviewView(view: vscode.WebviewView): void {
    this.view = view;
    view.title = tx(this.language, 'Resumen', 'Overview');
    view.webview.options = { enableScripts: true, localResourceRoots: [] };
    view.webview.onDidReceiveMessage(message => {
      const commands: Record<string, string> = { analyze: 'safecode.analyze', baseline: 'safecode.configureGitBaseline', policy: 'safecode.configureLayerPolicy', export: 'safecode.exportReport', python: 'safecode.selectPython', language: 'safecode.chooseLanguage' };
      if (typeof message?.command === 'string' && commands[message.command]) void vscode.commands.executeCommand(commands[message.command]);
    });
    this.refresh();
  }
  update(result: AnalysisResult | undefined, project?: string, message?: string): void {
    this.result = result; this.project = project; this.message = message; this.refresh();
  }
  private refresh(): void { if (this.view) this.view.webview.html = overviewHtml(this.logo, this.result, this.project, this.message, this.language); }
}
