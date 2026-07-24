import { createReadStream, existsSync, readFileSync, statSync } from 'node:fs';
import { spawn } from 'node:child_process';
import crypto from 'node:crypto';
import path from 'node:path';
import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import tailwindcss from '@tailwindcss/vite';

const LOCAL_ASSET_PREFIX = '/__kronara_asset';
const LOCAL_RPC_PATH = '/__kronara_rpc';
const ALLOWED_RPC_METHODS = new Set([
  'operations.chat',
  'operations.context',
  'operations.control_snapshot',
  'tools.timeline',
  'memory.search',
  'rag.retrieve_v3',
  'story.test',
  'content.run',
  'performance.learn',
  'run.diagnostics',
  'run.cancel',
  'run.progress',
  'agent.capabilities',
  'programs.list',
  'programs.template.save',
  'programs.template.reset',
  'programs.resources.save',
  'programs.resources.reset',
  'styles.list',
  'styles.upsert',
  'styles.delete',
  'voice.profiles',
  'voice.clone',
  'voice.delete_profile',
  'episodes.list',
  'episodes.get',
  'episodes.delete',
  'schedule.tick',
  'action.approve',
]);
const ALLOWED_AUTHORITY_TOOLS = new Set([
  'model.health',
  'model.complete',
  'reddit.list_signals',
  'meta.metrics.read',
  'pexels.search_videos',
  'voice.synthesize',
  'publication.publish',
]);
const ALLOWED_MODELS = new Set([
  'qwen/qwen3-235b-a22b',
  'moonshotai/kimi-k2',
  'nvidia/nemotron-3-ultra-550b-a55b:free',
  'nvidia/nemotron-3-super-120b-a12b:free',
  'tencent/hy3:free',
  'openai/gpt-oss-120b',
  'llama-3.3-70b-versatile',
  'qwen/qwen3.6-27b',
]);
const MIME_TYPES = {
  '.jpeg': 'image/jpeg',
  '.jpg': 'image/jpeg',
  '.mp4': 'video/mp4',
  '.png': 'image/png',
  '.webm': 'video/webm',
};

function localAssetPath(requestPath) {
  const root = path.resolve(process.cwd(), '.kronara', 'runtime');
  const candidate = path.isAbsolute(requestPath)
    ? path.resolve(requestPath)
    : path.resolve(root, requestPath);
  const relative = path.relative(root, candidate);
  if (!relative || relative.startsWith('..') || path.isAbsolute(relative)) return null;
  return candidate;
}

function serveLocalAsset(req, res, next) {
  const url = new URL(req.url, 'http://localhost');
  if (url.pathname !== LOCAL_ASSET_PREFIX) return next();

  const filePath = localAssetPath(url.searchParams.get('path') ?? '');
  if (!filePath || !existsSync(filePath)) {
    res.statusCode = 404;
    res.end('Local asset not found');
    return;
  }

  const size = statSync(filePath).size;
  const contentType = MIME_TYPES[path.extname(filePath).toLowerCase()] ?? 'application/octet-stream';
  const range = req.headers.range;
  let start = 0;
  let end = size - 1;
  if (range) {
    const match = /^bytes=(\d*)-(\d*)$/.exec(range);
    if (!match) {
      res.statusCode = 416;
      res.setHeader('Content-Range', `bytes */${size}`);
      res.end();
      return;
    }
    if (match[1]) {
      start = Number(match[1]);
      end = match[2] ? Number(match[2]) : size - 1;
    } else {
      const suffixLength = Number(match[2]);
      start = Math.max(size - suffixLength, 0);
      end = size - 1;
    }
    if (start > end || start >= size) {
      res.statusCode = 416;
      res.setHeader('Content-Range', `bytes */${size}`);
      res.end();
      return;
    }
    end = Math.min(end, size - 1);
    res.statusCode = 206;
    res.setHeader('Content-Range', `bytes ${start}-${end}/${size}`);
  } else {
    res.statusCode = 200;
  }

  res.setHeader('Accept-Ranges', 'bytes');
  res.setHeader('Content-Type', contentType);
  res.setHeader('Content-Length', String(end - start + 1));
  if (req.method === 'HEAD') {
    res.end();
    return;
  }
  createReadStream(filePath, { start, end }).pipe(res);
}

function localAssetPlugin() {
  return {
    name: 'kronara-local-assets',
    configureServer(server) {
      server.middlewares.use(serveLocalAsset);
    },
  };
}

function loadLocalEnv() {
  const envPath = path.resolve(process.cwd(), '.env');
  if (!existsSync(envPath)) return {};
  const values = {};
  for (const rawLine of readFileSync(envPath, 'utf8').split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const index = line.indexOf('=');
    if (index === -1) continue;
    const key = line.slice(0, index).trim();
    let value = line.slice(index + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    values[key] = value;
  }
  return values;
}

function configuredModelProviders(env) {
  const providers = [];
  for (const key of ['KRONARA_OPENROUTER_API_KEY', 'KRONARA_OPENROUTER_API_KEY_2', 'KRONARA_OPENROUTER_API_KEY_3']) {
    if (env[key]) providers.push({ provider: 'openrouter', apiKey: env[key], endpoint: 'https://openrouter.ai/api/v1/chat/completions' });
  }
  for (const legacy of [
    ['KRONARA_QWEN_API_KEY', 'KRONARA_QWEN_BASE_URL'],
    ['KRONARA_KIMI_API_KEY', 'KRONARA_KIMI_BASE_URL'],
  ]) {
    const [key, baseUrl] = legacy;
    if (env[key] && (env[baseUrl] ?? '').replace(/\/$/, '') === 'https://openrouter.ai/api/v1') {
      providers.push({ provider: 'openrouter', apiKey: env[key], endpoint: 'https://openrouter.ai/api/v1/chat/completions' });
    }
  }
  for (const key of ['KRONARA_GROQ_API_KEY', 'KRONARA_GROQ_API_KEY_2', 'KRONARA_GROQ_API_KEY_3']) {
    if (env[key]) providers.push({ provider: 'groq', apiKey: env[key], endpoint: 'https://api.groq.com/openai/v1/chat/completions' });
  }
  return providers;
}

function modelHealth(providers) {
  const health = {};
  if (providers.some((item) => item.provider === 'openrouter')) {
    for (const model of [
      'qwen/qwen3-235b-a22b',
      'moonshotai/kimi-k2',
      'nvidia/nemotron-3-ultra-550b-a55b:free',
      'nvidia/nemotron-3-super-120b-a12b:free',
      'tencent/hy3:free',
    ]) {
      health[model] = 'degraded';
    }
  }
  if (providers.some((item) => item.provider === 'groq')) {
    for (const model of ['openai/gpt-oss-120b', 'llama-3.3-70b-versatile', 'qwen/qwen3.6-27b']) {
      health[model] = 'degraded';
    }
  }
  return health;
}

function payloadMatchesSchema(payload, schema) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return false;
  const required = Array.isArray(schema?.required) ? schema.required : [];
  return required.every((field) => Object.prototype.hasOwnProperty.call(payload, field));
}

async function completeModel(argumentsValue, providers, health) {
  if (!providers.length) throw new Error('models_disabled_missing_credential');
  const request = argumentsValue ?? {};
  if (
    !request.task
    || typeof request.system !== 'string'
    || !request.input
    || typeof request.input !== 'object'
    || !request.response_schema
    || typeof request.response_schema !== 'object'
    || !Array.isArray(request.candidates)
    || request.candidates.length === 0
    || request.candidates.length > 5
    || !Number.isInteger(request.max_tokens)
    || request.max_tokens < 1
    || request.max_tokens > 8192
  ) {
    throw new Error('invalid bounded model request');
  }

  let lastError = 'no configured provider for model route';
  let attemptIndex = 0;
  for (const candidate of request.candidates) {
    if (!ALLOWED_MODELS.has(candidate.model_id)) {
      throw new Error(`model is not allowlisted: ${candidate.model_id}`);
    }
    const matches = providers.filter((item) => item.provider === candidate.provider);
    if (!matches.length) {
      lastError = `provider unavailable: ${candidate.provider}`;
      continue;
    }
    const responseFormat = candidate.model_id === 'tencent/hy3:free' || !request.response_schema.properties
      ? { type: 'json_object' }
      : {
          type: 'json_schema',
          json_schema: {
            name: `kronara_${String(request.task).replace(/[^A-Za-z0-9]/g, '_')}`,
            strict: true,
            schema: request.response_schema,
          },
        };
    const body = {
      model: candidate.model_id,
      messages: [
        { role: 'system', content: request.system },
        { role: 'user', content: JSON.stringify(request.input) },
      ],
      response_format: responseFormat,
      max_tokens: request.max_tokens,
      temperature: 0.7,
      stream: false,
    };
    if (candidate.provider === 'openrouter') body.reasoning = { enabled: false };

    for (const provider of matches) {
      attemptIndex += 1;
      try {
        const response = await fetch(provider.endpoint, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${provider.apiKey}`,
            'Content-Type': 'application/json',
            'X-OpenRouter-Title': 'Kronara',
          },
          body: JSON.stringify(body),
        });
        const json = await response.json();
        if (!response.ok) {
          lastError = `model provider failed with status ${response.status}`;
          continue;
        }
        const content = json?.choices?.[0]?.message?.content;
        const payload = typeof content === 'string' ? JSON.parse(content) : content;
        if (!payloadMatchesSchema(payload, request.response_schema)) {
          lastError = 'model structured payload failed schema validation';
          continue;
        }
        health[candidate.model_id] = 'healthy';
        return {
          payload,
          provider: provider.provider,
          model: candidate.model_id,
          fallback_used: attemptIndex > 1,
          usage: json?.usage ?? {},
        };
      } catch (error) {
        lastError = error instanceof Error ? error.message : 'model provider is unavailable';
      }
    }
  }
  throw new Error(lastError);
}

function jsonRpcResult(id, result) {
  return { jsonrpc: '2.0', id, result };
}

function jsonRpcError(id, code, message) {
  return { jsonrpc: '2.0', id, error: { code, message } };
}

class LocalSidecarHost {
  constructor() {
    this.env = { ...process.env, ...loadLocalEnv() };
    this.providers = configuredModelProviders(this.env);
    this.health = modelHealth(this.providers);
    this.token = crypto.randomUUID().replace(/-/g, '');
    this.child = null;
    this.buffer = '';
    this.nextId = 1;
    this.pending = new Map();
    this.startPromise = null;
    this.queue = Promise.resolve();
  }

  async call(method, params = {}) {
    if (!ALLOWED_RPC_METHODS.has(method)) {
      throw new Error('RPC method is not authorized locally');
    }
    if (!params || typeof params !== 'object' || Array.isArray(params)) {
      throw new Error('RPC params must be an object');
    }
    const run = () => this.request(method, params);
    this.queue = this.queue.then(run, run);
    return this.queue;
  }

  async start() {
    if (this.child) return;
    if (this.startPromise) return this.startPromise;
    this.startPromise = this.spawn();
    try {
      await this.startPromise;
    } finally {
      this.startPromise = null;
    }
  }

  async spawn() {
    const runtimeDir = path.resolve(process.cwd(), '.kronara', 'runtime');
    const python = this.env.KRONARA_SIDECAR_DEV_PYTHON || this.env.PYTHON || 'python';
    const args = [
      '-m',
      'kronara.sidecar',
      '--token',
      this.token,
      '--data-dir',
      runtimeDir,
      '--embedding-alias',
      this.env.KRONARA_EMBEDDING_ALIAS || 'bge_m3',
      '--reranker-alias',
      this.env.KRONARA_RERANKER_ALIAS || 'bge_reranker_v2_m3',
    ];
    this.child = spawn(python, args, {
      cwd: process.cwd(),
      env: {
        ...this.env,
        PYTHONPATH: path.resolve(process.cwd(), 'python'),
        KRONARA_RPC_SESSION_TOKEN: this.token,
      },
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    });
    this.child.stdout.setEncoding('utf8');
    this.child.stdout.on('data', (chunk) => this.handleStdout(chunk));
    this.child.stderr.setEncoding('utf8');
    this.child.stderr.on('data', (chunk) => process.stderr.write(`[kronara-sidecar] ${chunk}`));
    this.child.on('exit', () => this.handleExit());
    const handshake = await this.request('handshake', { token: this.token, protocol_version: 1 }, { skipStart: true });
    if (handshake.protocol_version !== 1) throw new Error('sidecar protocol handshake failed');
  }

  handleStdout(chunk) {
    this.buffer += chunk;
    let newline = this.buffer.indexOf('\n');
    while (newline !== -1) {
      const line = this.buffer.slice(0, newline).trim();
      this.buffer = this.buffer.slice(newline + 1);
      if (line) this.handleLine(line);
      newline = this.buffer.indexOf('\n');
    }
  }

  async handleLine(line) {
    let message;
    try {
      message = JSON.parse(line);
    } catch {
      this.rejectAll('invalid RPC response');
      return;
    }
    if (message.method === 'authority.invoke') {
      const response = await this.dispatchAuthority(message);
      this.write(response);
      return;
    }
    const pending = this.pending.get(message.id);
    if (!pending) return;
    this.pending.delete(message.id);
    if (message.error) {
      pending.reject(new Error(message.error.message || 'RPC request failed'));
      return;
    }
    pending.resolve(message.result);
  }

  handleExit() {
    this.child = null;
    this.rejectAll('cognitive sidecar closed unexpectedly');
  }

  rejectAll(message) {
    for (const pending of this.pending.values()) pending.reject(new Error(message));
    this.pending.clear();
  }

  async request(method, params, options = {}) {
    if (!options.skipStart) await this.start();
    const id = this.nextId++;
    const request = { jsonrpc: '2.0', id, method, params };
    const promise = new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
    });
    this.write(request);
    return promise;
  }

  write(message) {
    if (!this.child?.stdin?.writable) throw new Error('sidecar input is unavailable');
    this.child.stdin.write(`${JSON.stringify(message)}\n`);
  }

  async dispatchAuthority(request) {
    const id = request.id ?? null;
    const params = request.params ?? {};
    const toolId = params.tool_id;
    const args = params.arguments;
    if (!ALLOWED_AUTHORITY_TOOLS.has(toolId)) {
      return jsonRpcError(id, -32601, 'authority tool is not allowed');
    }
    if (!args || typeof args !== 'object' || Array.isArray(args)) {
      return jsonRpcError(id, -32602, 'authority arguments must be an object');
    }
    try {
      if (toolId === 'model.health') return jsonRpcResult(id, { schema_version: 1, models: this.health });
      if (toolId === 'model.complete') return jsonRpcResult(id, await completeModel(args, this.providers, this.health));
      if (toolId === 'reddit.list_signals') throw new Error('reddit_disabled_by_policy');
      if (toolId === 'meta.metrics.read') throw new Error('meta_disabled_by_policy');
      if (toolId === 'pexels.search_videos') throw new Error('pexels_disabled_by_policy');
      if (toolId === 'voice.synthesize') throw new Error('voice_authority_unavailable_in_web_mode');
      if (toolId === 'publication.publish') return jsonRpcResult(id, { status: 'not_configured', external_effect: false });
      return jsonRpcError(id, -32601, 'authority tool is not allowed');
    } catch (error) {
      return jsonRpcError(id, -32020, error instanceof Error ? error.message : 'authority invocation failed');
    }
  }
}

function readRequestBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.setEncoding('utf8');
    req.on('data', (chunk) => {
      body += chunk;
      // 25 MB: base64-encoded voice-clone reference audio (voice.clone RPC)
      // rides in the JSON body and inflates ~33%; a few-second clip is well
      // under this, VoiceBox's own 50 MB upload cap is the real ceiling.
      if (body.length > 25_000_000) {
        reject(new Error('request body is too large'));
        req.destroy();
      }
    });
    req.on('end', () => resolve(body));
    req.on('error', reject);
  });
}

function localRpcPlugin() {
  const host = new LocalSidecarHost();
  async function serveLocalRpc(req, res, next) {
    const url = new URL(req.url, 'http://localhost');
    if (url.pathname !== LOCAL_RPC_PATH) return next();
    if (req.method !== 'POST') {
      res.statusCode = 405;
      res.end('Method not allowed');
      return;
    }
    try {
      const body = JSON.parse(await readRequestBody(req) || '{}');
      const result = await host.call(String(body.method ?? ''), body.params ?? {});
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify({ result }));
    } catch (error) {
      res.statusCode = 500;
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify({ error: { message: error instanceof Error ? error.message : 'local RPC failed' } }));
    }
  }
  return {
    name: 'kronara-local-rpc',
    configureServer(server) {
      server.middlewares.use(serveLocalRpc);
    },
  };
}

export default defineConfig({
  plugins: [tailwindcss(), svelte(), localAssetPlugin(), localRpcPlugin()],
  clearScreen: false,
  server: {
    watch: {
      // Generated runtime/media and build scratch dirs are not frontend source.
      ignored: [
        '**/.kronara/**',
        '**/.pyinstaller-build/**',
        '**/.pyinstaller-spec/**',
        '**/src-tauri/target/**',
        '**/src-tauri/gen/**',
      ],
    },
  },
});
