import { writable } from 'svelte/store';

export const GENERATION_STAGES = [
  { key: 'investigacion', label: 'Investigación', detail: 'Buscando señales, revisando hilos completos, consultando RAG y descartando lo que no pasa filtros.', icon: 'search', at: 0 },
  { key: 'concepto', label: 'Concepto', detail: 'Convirtiendo la señal aprobada en una premisa original con plantilla del programa.', icon: 'wand', at: 25 },
  { key: 'guion', label: 'Guion', detail: 'Armando beats, escenas navegables, gancho, claridad, tensión, payoff y anclas visuales.', icon: 'list', at: 70 },
  { key: 'critica', label: 'Crítica', detail: 'Revalidando derechos, originalidad, estructura, duración, género del programa y reparaciones necesarias.', icon: 'check', at: 130 },
  { key: 'narracion', label: 'Narración', detail: 'Midiendo voz premium por escena, ritmo, pausas, duración real y marcas para SFX.', icon: 'clock', at: 180 },
  { key: 'produccion', label: 'Producción', detail: 'Generando portada obligatoria, imágenes consistentes con la historia, música/SFX, video vertical y QC.', icon: 'film', at: 260 },
  { key: 'guardando', label: 'Guardando', detail: 'Registrando guion, video, portada, música, SFX, evidencia y diagnóstico en la biblioteca local.', icon: 'folder', at: 1800 },
];

const STAGE_INDEX_BY_KEY = Object.fromEntries(GENERATION_STAGES.map((stage, index) => [stage.key, index]));
const LIVE_STAGE_DETAILS = {
  investigacion: [
    [0, 'Investigación: consultando fuentes públicas, hilos completos, memoria RAG y oportunidades recientes.'],
    [10, 'Investigación: separando señales útiles, continuaciones de historias y material que no sirve.'],
    [20, 'Investigación: registrando evidencia y preparando la mejor señal para Concepto.'],
  ],
  concepto: [
    [0, 'Concepto: convirtiendo la señal elegida en una premisa propia del programa.'],
    [18, 'Concepto: comparando plantillas RAG, tono del día y conflicto central.'],
    [35, 'Concepto: dejando claro protagonista, deseo, amenaza, costo y promesa del episodio.'],
  ],
  guion: [
    [0, 'Guion: armando beats, escenas separadas, gancho inicial y payoff final.'],
    [25, 'Guion: reforzando claridad, escalada, pregunta dramática y anclas visuales por escena.'],
    [50, 'Guion: preparando marcas para voz, storyboard, música y SFX.'],
  ],
  critica: [
    [0, 'Crítica: revisando originalidad, derechos, plantilla del programa y claridad narrativa.'],
    [20, 'Crítica: si encuentra fallos, pide reparaciones concretas antes de producir.'],
    [40, 'Crítica: revalidando estructura, duración, género y consistencia visual.'],
  ],
  narracion: [
    [0, 'Narración: midiendo voz premium, pausas y duración real del guion.'],
    [45, 'Narración: marcando escenas navegables, respiraciones, silencios y puntos de SFX.'],
    [90, 'Narración: comparando duración real contra el objetivo del programa.'],
  ],
  produccion: [
    [0, 'Producción: generando portada obligatoria y fijando personaje, lugar, paleta y amenaza.'],
    [90, 'Producción: preparando tandas de imágenes consistentes con la historia completa.'],
    [180, 'Producción: revisando recursos visuales, música, SFX y composición vertical.'],
    [360, 'Producción: ensamblando video 9:16 y comprobando que las escenas no pierdan contexto.'],
    [720, 'Producción: ejecutando QC visual/audio antes de permitir que pase a Guardando.'],
  ],
  guardando: [
    [0, 'Guardando: registrando guion, portada, video, música, SFX, evidencias y diagnóstico local.'],
    [45, 'Guardando: verificando archivos finales y actualizando la biblioteca del programa.'],
    [90, 'Guardando: cerrando metadatos para que el episodio aparezca en Programas y Biblioteca.'],
  ],
};
const TOOL_LABELS = {
  'model.complete': 'Modelo',
  'model.health': 'Salud de modelos',
  'reddit.list_signals': 'Investigación en Reddit',
  'knowledge.retrieve': 'RAG',
  'voice.synthesize': 'Voz',
  'pexels.search_videos': 'Video de apoyo',
  'publication.publish': 'Publicación',
  'meta.metrics.read': 'Métricas',
};
const AGENT_LABELS = {
  writer_room: 'Guionista',
  automated_qc: 'Crítica automática',
  voice_director: 'Director de voz',
  visual_director: 'Director visual',
  story_critic: 'Crítico narrativo',
  'story.critic': 'Crítico narrativo',
};
const STORAGE_KEY = 'kronara.episodeGeneration.v1';
const RESTORED_GENERATION = loadStoredGeneration();

export const episodeGeneration = writable(RESTORED_GENERATION);

let timer = null;

if (RESTORED_GENERATION?.status === 'running') {
  startGenerationTimer();
}

episodeGeneration.subscribe((run) => {
  if (typeof localStorage === 'undefined') return;
  if (!run) {
    localStorage.removeItem(STORAGE_KEY);
    return;
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(run));
});

export function startEpisodeGeneration({ programId, programName, storyId }) {
  stopGenerationTimer();
  episodeGeneration.set({
    programId,
    programName,
    storyId,
    startedAt: Date.now(),
    elapsedSeconds: 0,
    stageIndex: 0,
    status: 'running',
    title: 'Generando episodio',
    message: 'El backend local está trabajando.',
    diagnostics: null,
  });
  startGenerationTimer();
}

export function completeEpisodeGeneration(result = {}) {
  episodeGeneration.update((run) => run && ({
    ...run,
    elapsedSeconds: Math.floor((Date.now() - run.startedAt) / 1000),
    stageIndex: GENERATION_STAGES.length - 1,
    status: 'completed',
    title: result.story?.title ?? 'Episodio creado',
    message: 'Episodio guardado. Actualizando la biblioteca local.',
    diagnostics: result.diagnostics ?? run.diagnostics ?? null,
  }));
  stopGenerationTimer();
  setTimeout(() => {
    episodeGeneration.update((run) => (run?.status === 'completed' ? null : run));
  }, 4500);
}

export function failEpisodeGeneration(message, diagnostics = null) {
  episodeGeneration.update((run) => run && ({
    ...run,
    elapsedSeconds: Math.floor((Date.now() - run.startedAt) / 1000),
    stageIndex: failedStageIndex(diagnostics, run.stageIndex),
    status: 'failed',
    message,
    diagnostics: diagnostics ?? run.diagnostics ?? null,
  }));
  stopGenerationTimer();
}

export function updateEpisodeGenerationDiagnostics(diagnostics) {
  if (!diagnostics) return;
  episodeGeneration.update((run) => run && ({
    ...run,
    diagnostics,
    stageIndex: diagnosticStageIndex(diagnostics, run.stageIndex),
    message: diagnosticMessage(diagnostics) ?? run.message,
  }));
}

export function clearEpisodeGeneration() {
  stopGenerationTimer();
  episodeGeneration.set(null);
}

export function generationPercent(run) {
  if (!run) return 0;
  if (run.status === 'completed') return 100;
  if (run.status === 'failed') return Math.max(8, Math.round((run.stageIndex / GENERATION_STAGES.length) * 100));
  const stage = GENERATION_STAGES[run.stageIndex];
  const next = GENERATION_STAGES[run.stageIndex + 1];
  if (!next) return 94;
  const local = Math.max(0, Math.min(1, (run.elapsedSeconds - stage.at) / (next.at - stage.at)));
  return Math.min(94, Math.round(((run.stageIndex + local) / GENERATION_STAGES.length) * 100));
}

export function formatElapsed(seconds) {
  const safe = Math.max(0, Number(seconds) || 0);
  const minutes = Math.floor(safe / 60);
  const rest = safe % 60;
  return `${minutes}:${rest.toString().padStart(2, '0')}`;
}

export function currentGenerationStage(run) {
  return GENERATION_STAGES[run?.stageIndex ?? 0] ?? GENERATION_STAGES[0];
}

export function currentGenerationDetail(run) {
  const stage = currentGenerationStage(run);
  const phase = run?.diagnostics?.phases?.find((item) => item.key === stage.key);
  return latestDiagnosticText(run) || phase?.detail || liveStageDetail(run, stage) || stage.detail;
}

function stageIndexForElapsed(elapsedSeconds) {
  let index = 0;
  for (let i = 0; i < GENERATION_STAGES.length; i += 1) {
    if (elapsedSeconds >= GENERATION_STAGES[i].at) index = i;
  }
  return Math.min(index, GENERATION_STAGES.length - 1);
}

function diagnosticStageIndex(diagnostics, fallback) {
  const phases = diagnostics?.phases ?? [];
  const failed = phases.find((phase) => phase.status === 'failed');
  if (failed?.key && STAGE_INDEX_BY_KEY[failed.key] != null) return STAGE_INDEX_BY_KEY[failed.key];
  const latest = [...phases].reverse().find((phase) => ['running', 'completed'].includes(phase.status));
  if (latest?.key && STAGE_INDEX_BY_KEY[latest.key] != null) return STAGE_INDEX_BY_KEY[latest.key];
  return fallback ?? 0;
}

function failedStageIndex(diagnostics, fallback) {
  const failed = diagnostics?.phases?.find((phase) => phase.status === 'failed');
  if (failed?.key && STAGE_INDEX_BY_KEY[failed.key] != null) return STAGE_INDEX_BY_KEY[failed.key];
  return fallback ?? 0;
}

function diagnosticMessage(diagnostics) {
  const failed = diagnostics?.phases?.find((phase) => phase.status === 'failed');
  if (failed?.detail) return failed.detail;
  const latest = [...(diagnostics?.phases ?? [])].reverse().find((phase) => phase.detail);
  return latest?.detail ?? null;
}

function liveStageDetail(run, stage) {
  const details = LIVE_STAGE_DETAILS[stage.key] ?? [];
  const relative = Math.max(0, Number(run?.elapsedSeconds ?? 0) - Number(stage.at ?? 0));
  let selected = null;
  for (const [at, text] of details) {
    if (relative >= at) selected = text;
  }
  return selected;
}

function latestDiagnosticText(run) {
  const tool = [...(run?.diagnostics?.tool_events ?? [])]
    .reverse()
    .find((event) => event.summary);
  if (tool?.summary) return `${friendlyToolLabel(tool.tool_id)}: ${tool.summary}`;
  const agent = [...(run?.diagnostics?.agent_logs ?? [])]
    .reverse()
    .find((event) => event.detail);
  if (agent?.detail) return `${friendlyAgentLabel(agent.agent_id)}: ${agent.detail}`;
  return null;
}

function friendlyToolLabel(toolId) {
  return TOOL_LABELS[toolId] ?? 'Herramienta';
}

function friendlyAgentLabel(agentId) {
  return AGENT_LABELS[agentId] ?? 'Agente';
}

function stopGenerationTimer() {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
}

function startGenerationTimer() {
  stopGenerationTimer();
  timer = setInterval(() => {
    episodeGeneration.update((run) => {
      if (!run || run.status !== 'running') return run;
      const elapsedSeconds = Math.floor((Date.now() - run.startedAt) / 1000);
      return { ...run, elapsedSeconds, stageIndex: stageIndexForElapsed(elapsedSeconds) };
    });
  }, 1000);
}

function loadStoredGeneration() {
  if (typeof localStorage === 'undefined') return null;
  try {
    const run = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
    if (!run || !run.startedAt) return null;
    const elapsedSeconds = Math.floor((Date.now() - run.startedAt) / 1000);
    if (elapsedSeconds > 60 * 60 * 6) return null;
    if (run.status === 'completed') return null;
    return {
      ...run,
      elapsedSeconds: Math.max(0, elapsedSeconds),
      stageIndex: run.status === 'running'
        ? stageIndexForElapsed(elapsedSeconds)
        : run.stageIndex,
    };
  } catch {
    localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}
