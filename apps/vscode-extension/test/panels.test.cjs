const { test } = require('node:test');
const assert = require('node:assert/strict');
const Module = require('node:module');
const originalLoad = Module._load;
Module._load = function(request, parent, isMain) {
  if (request === 'vscode') return {};
  return originalLoad.call(this, request, parent, isMain);
};
const { overviewHtml, findingHtml, reportHtml } = require('../out/panels.js');
Module._load = originalLoad;

const finding = { rule_id: 'SEG-03', title: 'Credencial literal', explanation: 'Se asigna un literal', severity: 'medium', path: 'src/app.py', start: { line: 4 }, evidence: 'api_key = [valor omitido]' };
const result = { metrics: { files: 2, findings: 1 }, status: 'partial', coverage: { 'SEG-03': 'analyzed', 'ARQ-01': 'skipped' }, findings: [finding] };

test('English UI, detail, and exported report use English labels and findings', () => {
  const overview = overviewHtml('', result, 'sample', undefined, 'en');
  const detail = findingHtml('', finding, undefined, 'en');
  const report = reportHtml('', 'sample', result, 'en');
  assert.match(overview, /<html lang="en">/);
  assert.match(overview, /Export report/);
  assert.match(detail, /Hard-coded credential/);
  assert.match(detail, /Related dependencies/);
  assert.match(report, /Analysis report/);
  assert.match(report, /Rule coverage/);
  assert.match(report, /ARQ-01: skipped/);
  assert.doesNotMatch(report, /Credencial literal|Cobertura de reglas|hallazgos/);
});

test('Spanish remains available when selected', () => {
  const html = reportHtml('', 'sample', result, 'es');
  assert.match(html, /<html lang="es">/);
  assert.match(html, /Reporte de análisis/);
  assert.match(html, /Credencial literal/);
});

test('complete-for-supported-scope is not displayed as partial', () => {
  const complete = { ...result, status: 'complete_for_supported_scope', baseline: { kind: 'git', ref: 'HEAD', commit: 'abc123456789' } };
  const overview = overviewHtml('', complete, 'sample', undefined, 'en');
  const report = reportHtml('', 'sample', complete, 'en');
  assert.match(overview, /complete for supported scope/);
  assert.match(overview, /HEAD · abc12345/);
  assert.match(report, /Comparison baseline: HEAD/);
  assert.doesNotMatch(report, /status partial/);
});

test('overview explains which setup is missing for architecture rules', () => {
  const missingBaseline = overviewHtml('', result, 'sample', undefined, 'en');
  assert.match(missingBaseline, /ARQ-01 has not been evaluated/);
  assert.match(missingBaseline, /switching branches in VS Code does not configure the baseline/);
  assert.match(missingBaseline, /data-command="baseline"/);
  const withBaseline = overviewHtml('', { ...result, baseline: { kind: 'git', ref: 'main', commit: 'abc123456789' },
    coverage: { 'SEG-03': 'analyzed', 'ARQ-01': 'analyzed', 'ARQ-02': 'skipped' } }, 'sample', undefined, 'en');
  assert.match(withBaseline, /ARQ-02 has not been evaluated/);
  assert.match(withBaseline, /data-command="policy"/);
});
