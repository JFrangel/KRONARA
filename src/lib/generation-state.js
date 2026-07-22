import { writable } from 'svelte/store';

export const GENERATION_STAGES = [
  { key: 'investigacion', label: 'Investigacion', detail: 'Buscando senales, revisando hilos completos, consultando RAG y descartando lo que no pasa filtros.', icon: 'search', at: 0 },
  { key: 'concepto', label: 'Concepto', detail: 'Convirtiendo la senal aprobada en una premisa original con plantilla del programa.', icon: 'wand', at: 25 },
  { key: 'guion', label: 'Guion', detail: 'Armando beats, escenas navegables, gancho, claridad, tension, payoff y anclas visuales.', icon: 'list', at: 70 },
  { key: 'critica', label: 'Critica', detail: 'Revalidando derechos, originalidad, estructura, duracion, genero del programa y reparaciones necesarias.', icon: 'check', at: 130 },
  { key: 'narracion', label: 'Narracion', detail: 'Midiendo voz premium por escena, ritmo, pausas, duracion real y marcas para SFX.', icon: 'clock', at: 180 },
  { key: 'produccion', label: 'Produccion', detail: 'Generando portada obligatoria, imagenes consistentes con la historia, musica/SFX, video vertical y QC.', icon: 'film', at: 260 },
  { key: 'guardando', label: 'Guardando', detail: 'Registrando guion, video, portada, musica, SFX, evidencia y diagnostico en la biblioteca local.', icon: 'folder', at: 1800 },
];

const STAGE_INDEX_BY_KEY = Object.fromEntries(GENERATION_STAGES.map((stage, index) => [stage.key, index]));
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
    message: 'El backend local esta trabajando.',
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
  return phase?.detail || stage.detail;
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
