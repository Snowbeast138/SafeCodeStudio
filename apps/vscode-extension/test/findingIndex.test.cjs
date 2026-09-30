const { test } = require('node:test');
const assert = require('node:assert/strict');
const { buildFindingIndex } = require('../out/findingIndex.js');

test('nested findings mark every ancestor and errors take priority over warnings', () => {
  const index = buildFindingIndex([
    { path: 'src/ui/card.tsx', severity: 'medium' },
    { path: 'src/ui/card.tsx', severity: 'high' },
    { path: 'src/api/client.ts', severity: 'medium' },
  ]);
  assert.deepEqual(index.files.get('src/ui/card.tsx'), { errors: 1, warnings: 1 });
  assert.deepEqual(index.folders.get('src/ui'), { errors: 1, warnings: 1 });
  assert.deepEqual(index.folders.get('src'), { errors: 1, warnings: 2 });
  assert.deepEqual(index.folders.get('src/api'), { errors: 0, warnings: 1 });
  assert.equal(index.folders.has('.'), false);
});

test('resolved findings and paths outside the project do not leave folder indicators', () => {
  const index = buildFindingIndex([{ path: '../outside.py', severity: 'high' }]);
  assert.equal(index.files.size, 0);
  assert.equal(index.folders.size, 0);
  assert.equal(buildFindingIndex([]).folders.size, 0);
});
