import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';


test('operations UI can launch the governed Reddit production vertical and show its evidence', () => {
  const source = fs.readFileSync('src/lib/views/Estudio.svelte', 'utf8');

  assert.match(source, /runProductionContent/);
  assert.match(source, /content\.run/);
  assert.match(source, /reddit\.list_signals/);
  assert.match(source, /generator_family/);
  assert.match(source, /rag_citations/);
});
