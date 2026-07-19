import assert from 'node:assert/strict';
import test from 'node:test';

import {
  appendChatResponse,
  applyProgressEvent,
  createOperationsState,
} from '../src/lib/operations-state.js';


test('tool timeline preserves failures and evidence without duplicates', () => {
  const event = {
    event_id: 'tte_1',
    agent_id: 'opportunity_intelligence',
    tool_id: 'reddit.list_signals',
    status: 'failed',
    duration_ms: 320,
    evidence_refs: ['ev_1'],
    result_summary: 'rate limit',
  };

  const once = applyProgressEvent(createOperationsState(), event);
  const twice = applyProgressEvent(once, { ...event, status: 'completed' });

  assert.equal(twice.toolEvents.length, 1);
  assert.equal(twice.toolEvents[0].status, 'completed');
  assert.deepEqual(twice.toolEvents[0].evidence_refs, ['ev_1']);
});


test('chat response keeps citations, trace ids and pending action intent', () => {
  const response = {
    request_id: 'req_1',
    status: 'completed',
    answer: 'La operación está estable.',
    citations: ['kronara://evidence/health'],
    tool_trace_ids: ['tte_1'],
    action_intent: {
      intent_id: 'intent_1',
      kind: 'set_budget',
      status: 'requires_approval',
    },
  };

  const state = appendChatResponse(createOperationsState(), response);

  assert.equal(state.messages.at(-1).content, response.answer);
  assert.deepEqual(state.messages.at(-1).citations, response.citations);
  assert.deepEqual(state.traceIds, ['tte_1']);
  assert.equal(state.pendingAction.intent_id, 'intent_1');
});


test('initial operations state is explicit and safe', () => {
  const state = createOperationsState();

  assert.equal(state.connection, 'disconnected');
  assert.equal(state.chatStatus, 'idle');
  assert.deepEqual(state.toolEvents, []);
  assert.equal(state.pendingAction, null);
});
