export function createOperationsState(overrides = {}) {
  return {
    connection: 'disconnected',
    chatStatus: 'idle',
    messages: [],
    toolEvents: [],
    traceIds: [],
    pendingAction: null,
    activeRun: null,
    ...overrides,
  };
}

export function applyProgressEvent(state, event) {
  if (!event?.event_id) return state;
  const existing = state.toolEvents.findIndex((item) => item.event_id === event.event_id);
  const toolEvents = [...state.toolEvents];
  if (existing === -1) toolEvents.push({ ...event });
  else toolEvents[existing] = { ...toolEvents[existing], ...event };
  return { ...state, toolEvents };
}

export function appendChatResponse(state, response) {
  const traceIds = [...new Set([...state.traceIds, ...(response.tool_trace_ids ?? [])])];
  return {
    ...state,
    chatStatus: response.status ?? 'completed',
    traceIds,
    pendingAction: response.action_intent ?? null,
    messages: [
      ...state.messages,
      {
        role: 'assistant',
        content: response.answer,
        citations: response.citations ?? [],
        traceIds: response.tool_trace_ids ?? [],
        // Fase 1f guided flow: quick-reply chips for this assistant turn.
        options: response.options ?? [],
      },
    ],
  };
}

export function appendUserMessage(state, content) {
  return {
    ...state,
    chatStatus: 'thinking',
    messages: [...state.messages, { role: 'user', content, citations: [], traceIds: [] }],
  };
}
