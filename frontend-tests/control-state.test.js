import assert from 'node:assert/strict';
import test from 'node:test';

import { createControlState, togglePause } from '../src/lib/control-state.js';

test('full_auto is the default autonomy mode', () => {
  assert.equal(createControlState().mode, 'full_auto');
});

test('global pause toggles without changing the autonomy mode', () => {
  const state = togglePause(createControlState());
  assert.equal(state.paused, true);
  assert.equal(state.mode, 'full_auto');
});

