export function isLocalWeb() {
  return typeof window !== 'undefined';
}

async function callLocalOperations(method, params = {}) {
  let response;
  try {
    response = await fetch('/__kronara_rpc', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ method, params }),
    });
  } catch {
    throw new Error('Servidor local apagado o reiniciandose. Vuelve a iniciar la web local y reintenta.');
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.error) {
    throw new Error(payload.error?.message ?? `Local RPC failed: ${response.status}`);
  }
  return payload.result;
}

export async function callOperations(method, params = {}) {
  return callLocalOperations(method, params);
}

// Local file paths (a cover image, a rendered episode video) can't be used as
// <img>/<video> src directly in the browser. The local Vite server exposes a
// bounded media route for files under .kronara/runtime.
export function assetSrc(path) {
  if (!path) return null;
  if (/^(?:data:|blob:|https?:\/\/)/i.test(path)) return path;
  return `/__kronara_asset?path=${encodeURIComponent(path)}`;
}

export async function getControlState() {
  const context = await callOperations('operations.context', {});
  return {
    paused: Boolean(context.workflow_snapshot?.paused),
    autonomy_mode: context.workflow_snapshot?.mode ?? 'full_auto',
  };
}

export function setGlobalPause(paused) {
  return callOperations('operations.control_snapshot', { paused });
}
