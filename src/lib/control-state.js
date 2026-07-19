export function createControlState(overrides = {}) {
  return {
    mode: 'full_auto',
    paused: false,
    dailyPublicationLimit: 3,
    maxDailyCostUsd: 5,
    ...overrides,
  };
}

export function togglePause(state) {
  return { ...state, paused: !state.paused };
}

