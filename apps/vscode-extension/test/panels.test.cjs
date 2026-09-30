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
