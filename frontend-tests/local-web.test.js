import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

import { assetSrc } from '../src/lib/local-operations.js';


test('assetSrc serves local media through the web asset bridge', () => {
  const source = assetSrc('D:\\Proyecto Redit\\.kronara\\runtime\\images\\cover.png');
  assert.equal(
    source,
    '/__kronara_asset?path=D%3A%5CProyecto%20Redit%5C.kronara%5Cruntime%5Cimages%5Ccover.png',
  );
});

test('episode player exposes browser playback controls and the correct vertical format', () => {
  const source = fs.readFileSync('src/lib/views/Programas.svelte', 'utf8');

  assert.match(source, /controls/);
  assert.match(source, /preload="metadata"/);
  assert.match(source, /playsinline/);
  assert.match(source, /type="video\/mp4"/);
  assert.match(source, /Video 9:16/);
  assert.match(source, /connection !== 'connected' \|\| !selected/);
  assert.doesNotMatch(source, new RegExp('pre' + 'view'));
});

test('failed local generation can be retried instead of force-approved', () => {
  const source = fs.readFileSync('src/lib/views/Programas.svelte', 'utf8');

  assert.match(source, /Reintentar/);
  assert.match(source, /Reintentar produccion/);
  assert.match(source, /no queda aprobado para publicar/);
  assert.match(source, /videoNeedsRetry/);
});

test('frontend uses only the local web operations bridge', () => {
  const source = fs.readFileSync('src/lib/local-operations.js', 'utf8');

  assert.match(source, /__kronara_rpc/);
  assert.match(source, /__kronara_asset/);
  assert.doesNotMatch(source, new RegExp('@' + 'ta' + 'uri-apps/api'));
  assert.doesNotMatch(source, new RegExp('pre' + 'viewOperations'));
  assert.doesNotMatch(source, new RegExp('pre' + 'view_mode'));
});
