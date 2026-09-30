const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { byteColumnToUtf16 } = require('../out/positions.js');
const { withWebviewCsp } = require('../out/webviewHtml.js');
const { WorkerClient } = require('../out/worker.js');
const { pythonCandidates } = require('../out/pythonRuntime.js');
const { resolveLanguage, localizeFinding, localizeGraphHtml } = require('../out/i18n.js');

test('Tree-sitter byte columns become VS Code UTF-16 columns', () => {
  assert.equal(byteColumnToUtf16('a😀é', 1), 1);
  assert.equal(byteColumnToUtf16('a😀é', 5), 3);
  assert.equal(byteColumnToUtf16('a😀é', 7), 4);
});

test('graph webview gets a restrictive CSP and focus bridge', () => {
  const html = withWebviewCsp('<html><meta charset="utf-8"><style>x{}</style><script>go()</script></html>', 'testnonce');
  assert.match(html, /default-src 'none'/);
  assert.match(html, /style-src 'nonce-testnonce'/);
  assert.match(html, /<script nonce="testnonce">go\(\)/);
  assert.match(html, /event\.data\.id/);
});

test('manifest contributes sidebar graph, files, findings and commands', () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, '../package.json')));
  assert.deepEqual(manifest.contributes.views.safecode.map(view => view.id),
    ['safecode.overview', 'safecode.files', 'safecode.graph', 'safecode.findings']);
  assert.ok(manifest.contributes.commands.some(command => command.command === 'safecode.analyze'));
  assert.ok(manifest.contributes.commands.some(command => command.command === 'safecode.selectPython'));
  assert.ok(manifest.contributes.commands.some(command => command.command === 'safecode.chooseLanguage'));
  assert.deepEqual(manifest.contributes.configuration.properties['safecode.language'].enum, ['auto', 'es', 'en']);
  assert.equal(manifest.contributes.viewsContainers.activitybar[0].icon, 'media/safecode.svg');
  for (const severity of ['error', 'warning']) {
    for (const theme of ['light', 'dark']) {
      const icon = path.join(__dirname, `../media/folder-${severity}-${theme}.svg`);
      assert.ok(fs.existsSync(icon), `missing folder badge ${severity}/${theme}`);
    }
  }
});

test('language setting overrides VS Code locale and localizes deterministic findings', () => {
  assert.equal(resolveLanguage('auto', 'es-MX'), 'es');
  assert.equal(resolveLanguage('auto', 'en-US'), 'en');
  assert.equal(resolveLanguage('en', 'es-MX'), 'en');
  const original = { rule_id: 'SEG-03', title: 'Credencial literal', explanation: 'Texto español', evidence: 'api_key = [valor omitido]' };
  const english = localizeFinding(original, 'en');
  assert.equal(english.title, 'Hard-coded credential');
  assert.match(english.explanation, /secure configuration/);
  assert.equal(english.evidence, 'api_key = [value redacted]');
  assert.equal(localizeFinding(original, 'es'), original);
});

test('graph translation preserves the embedded analysis data', () => {
  const html = '<html lang="es"><h1>Relaciones entre archivos</h1><script type="application/json" id="data">{"path":"Relaciones entre archivos"}</script><script>const label="Lo importan";</script></html>';
  const english = localizeGraphHtml(html, 'en');
  assert.match(english, /<html lang="en">/);
  assert.match(english, /<h1>File relationships<\/h1>/);
  assert.match(english, /"path":"Relaciones entre archivos"/);
  assert.match(english, /const label="Imported by"/);
  assert.equal(localizeGraphHtml(html, 'es'), html);
});

test('Python discovery finds a sibling SafeCode environment for another open repository', () => {
  const candidates = pythonCandidates('/home/example/Projects/menasa', '/tmp/ext', '');
  assert.ok(candidates.includes('/home/example/Projects/SafeCode/.venv/bin/python'));
});

const python = process.env.SAFECODE_TEST_PYTHON || path.resolve(__dirname, '../../../.venv/bin/python');
test('extension worker keeps one Python session and updates findings', { skip: !fs.existsSync(python) }, async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'safecode-vscode-'));
  fs.writeFileSync(path.join(root, 'app.py'), "api_key = 'synthetic-integration-token'\n");
  const logs = [];
  const worker = new WorkerClient(root, { executable: python, host: false }, path.resolve(__dirname, '..'), undefined, undefined,
    { append: text => logs.push(text), appendLine: text => logs.push(text) });
  try {
    const first = await worker.request('analyze', { version: 1 }, 30_000);
    assert.equal(first.metrics.parsed_files, 1);
    assert.deepEqual(first.findings.map(f => f.rule_id), ['SEG-03']);
    const graph = await worker.request('graph');
    assert.equal(graph.nodes.length, 1);
    const html = await worker.request('graphHtml');
    assert.match(html, /Relaciones entre archivos/);
    fs.writeFileSync(path.join(root, 'app.py'), "api_key = settings['API_KEY']\n");
    const second = await worker.request('analyze', { version: 2 }, 30_000);
    assert.equal(second.metrics.parsed_files, 1);
    assert.equal(second.findings.length, 0);
    assert.equal(second.findings_delta.resolved.length, 1);
    const third = await worker.request('analyze', { version: 3 }, 30_000);
    assert.equal(third.metrics.parsed_files, 0);
  } finally {
    worker.dispose();
    fs.rmSync(root, { recursive: true, force: true });
  }
});
