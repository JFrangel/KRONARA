import { convertFileSrc, invoke } from '@tauri-apps/api/core';

export function callOperations(method, params = {}) {
  return invoke('operations_rpc', { method, params });
}

// Local file paths (a cover image, a rendered episode video) can't be used
// as <img>/<video> src directly in the webview -- Tauri's asset protocol
// (scoped to $APPDATA/runtime/** in tauri.conf.json) needs the path
// rewritten into an asset://-style URL first. Returns null for an
// empty/missing path so callers can fall back to a placeholder without a
// try/catch at every call site.
export function assetSrc(path) {
  if (!path) return null;
  try {
    return convertFileSrc(path);
  } catch (error) {
    return null;
  }
}

export function getControlState() {
  return invoke('get_control_state');
}

export function setGlobalPause(paused) {
  return invoke('set_global_pause', { paused });
}
