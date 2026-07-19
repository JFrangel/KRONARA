import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('Tauri configuration packages the Vite frontend and Python sidecar', async () => {
  const config = JSON.parse(await readFile(new URL('../src-tauri/tauri.conf.json', import.meta.url)));

  assert.equal(config.build.frontendDist, '../dist');
  assert.equal(config.productName, 'Kronara OS');
  assert.ok(config.bundle.externalBin.includes('binaries/kronara-sidecar'));
});

