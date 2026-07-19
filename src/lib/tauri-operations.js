import { invoke } from '@tauri-apps/api/core';

export function callOperations(method, params = {}) {
  return invoke('operations_rpc', { method, params });
}

export function getControlState() {
  return invoke('get_control_state');
}

export function setGlobalPause(paused) {
  return invoke('set_global_pause', { paused });
}
