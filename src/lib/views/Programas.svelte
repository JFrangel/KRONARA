<script>
  import { onMount } from 'svelte';
  import Card from '../components/Card.svelte';
  import Badge from '../components/Badge.svelte';
  import Icon from '../components/Icon.svelte';
  import { assetSrc, callOperations } from '../local-operations.js';
  import { programGradient } from '../programArt.js';
  import {
    clearEpisodeGeneration,
    episodeGeneration,
    failEpisodeGeneration,
    completeEpisodeGeneration,
    formatElapsed,
    generationPercent,
    GENERATION_STAGES,
    startEpisodeGeneration,
    updateEpisodeGenerationDiagnostics,
  } from '../generation-state.js';

  let { connection = 'disconnected', initialProgramId = null, openToken = 0 } = $props();

  let programs = $state([]);
  let episodes = $state([]);
  let loadError = $state(false);
  let loading = $state(true);
  let selected = $state(null);
  let appliedProgramId = $state(null);
  let appliedOpenToken = $state(null);
  let activeTab = $state('resumen');
  let creating = $state(false);
  let createNotice = $state('');
  let selectedEpisodeId = $state(null);
  let episodeDetailTab = $state('resumen');
  // Keyed by story_id -- episodes.list omits script text so browsing the
  // list never pulls every episode's full script over the wire; the full
  // detail (script, hook, video QC breakdown) is fetched lazily once per
  // episode the moment it's actually selected, then cached here.
  let episodeDetailCache = $state({});
  let episodeDetailLoading = $state(false);
  let mediaErrors = $state({});
  let deletingEpisodeId = $state(null);
  let templateDraft = $state('');
  let templateSaving = $state(false);
  let templateNotice = $state('');
  let storyResourceDraft = $state('');
  let storyResourceSaving = $state(false);
  let storyResourceNotice = $state('');
  const EPISODE_DETAIL_TABS = ['resumen', 'guion', 'recursos', 'produccion', 'distribucion', 'analiticas'];
  const EPISODE_DETAIL_TAB_LABELS = {
    resumen: 'Resumen', guion: 'Guion', recursos: 'Recursos',
    produccion: 'Producción', distribucion: 'Distribución', analiticas: 'Analíticas',
  };

  // Episodios lives here rather than as its own top-level section -- every
  // episode belongs to exactly one program, so browsing them detached from
  // that program threw away the one grouping that actually matters.
  const TABS = ['resumen', 'episodios', 'calendario', 'personajes', 'configuracion', 'analiticas', 'recursos'];
  const TAB_LABELS = {
    resumen: 'Resumen', episodios: 'Episodios', calendario: 'Calendario', personajes: 'Personajes',
    configuracion: 'Configuración', analiticas: 'Analíticas', recursos: 'Recursos',
  };
  const WEEKDAY_LABELS = {
    monday: 'lunes', tuesday: 'martes', wednesday: 'miércoles', thursday: 'jueves',
    friday: 'viernes', saturday: 'sábado', sunday: 'domingo',
  };
  onMount(async () => {
    try {
      const [programsResponse, episodesResponse] = await Promise.all([
        callOperations('programs.list', {}),
        callOperations('episodes.list', { limit: 200 }),
      ]);
      programs = programsResponse.programs ?? [];
      episodes = episodesResponse.episodes ?? [];
      const initialProgram = initialProgramId ? programs.find((program) => program.program_id === initialProgramId) : null;
      if (initialProgram) {
        appliedProgramId = initialProgram.program_id;
        appliedOpenToken = openToken;
        openProgram(initialProgram, tabForProgram(initialProgram.program_id));
      }
    } catch (error) {
      loadError = true;
    } finally {
      loading = false;
    }
  });

  $effect(() => {
    if (!programs.length) return;
    if (initialProgramId && (appliedProgramId !== initialProgramId || appliedOpenToken !== openToken)) {
      const initialProgram = programs.find((program) => program.program_id === initialProgramId);
      if (initialProgram) {
        appliedProgramId = initialProgram.program_id;
        appliedOpenToken = openToken;
        openProgram(initialProgram, tabForProgram(initialProgram.program_id));
      }
    } else if (!initialProgramId && appliedProgramId !== null) {
      appliedProgramId = null;
      appliedOpenToken = null;
      selected = null;
    }
  });

  function openProgram(program, tab = 'resumen') {
    selected = program;
    activeTab = tab;
    createNotice = '';
    templateNotice = '';
    storyResourceNotice = '';
    templateDraft = templateText(program.narrative_template);
    storyResourceDraft = program.story_resource_text ?? '';
    selectedEpisodeId = null;
  }

  function tabForProgram(programId) {
    return $episodeGeneration?.programId === programId ? 'episodios' : 'resumen';
  }

  async function createEpisode(options = {}) {
    if (creating || connection !== 'connected' || !selected) return;
    creating = true;
    createNotice = options.retry
      ? 'Reintentando desde agentes: se volvera a validar investigacion, guion, critica, narracion, produccion y guardado.'
      : '';
    const programId = selected.program_id;
    const storyId = `owned_ui_${Date.now()}`;
    startEpisodeGeneration({ programId, programName: selected.name, storyId });
    activeTab = 'episodios';
    try {
      const result = await callOperations('content.run', {
        program_id: programId,
        story_id: storyId,
      });
      if (result.status === 'completed') {
        completeEpisodeGeneration(result);
        createNotice = `Episodio creado: "${result.story?.title ?? result.run_id}".`;
        activeTab = 'episodios';
        const refreshed = await callOperations('episodes.list', { limit: 200 });
        episodes = refreshed.episodes ?? episodes;
        const created = episodes.find((episode) => episode.story_id === storyId)
          ?? episodes.find((episode) => episode.program_id === programId);
        selectedEpisodeId = created?.story_id ?? null;
      } else {
        const diagnostics = result.diagnostics ?? await loadRunDiagnostics(result.run_id);
        updateEpisodeGenerationDiagnostics(diagnostics);
        const message = generationFailureMessage(result.error_code ?? result.status, diagnostics);
        failEpisodeGeneration(message, diagnostics);
        createNotice = `${message} El vertical no publica nada a menos que Reddit, los modelos, los derechos y la calidad pasen todas las validaciones.`;
      }
    } catch (error) {
      const detail = error instanceof Error && error.message ? ` Detalle: ${error.message}` : '';
      failEpisodeGeneration(`Falló la creación del episodio en la web local.${detail}`);
      createNotice = `Falló la creación del episodio en la web local.${detail}`;
    } finally {
      creating = false;
    }
  }

  async function retrySelectedProgram() {
    if (creating || connection !== 'connected' || !selected) return;
    await createEpisode({ retry: true });
  }

  function episodesFor(programId) {
    return episodes.filter((episode) => episode.program_id === programId);
  }

  function episodeCountFor(programId) {
    return episodesFor(programId).length;
  }

  async function loadRunDiagnostics(runId) {
    if (!runId) return null;
    try {
      return await callOperations('run.diagnostics', { run_id: runId });
    } catch {
      return null;
    }
  }

  function generationFailureMessage(code, diagnostics = null) {
    const quality = diagnostics?.quality_failure;
    const programQuality = diagnostics?.program_quality_failure;
    if (code === 'PROGRAM_QUALITY_FAILED' && programQuality) {
      return `No paso la plantilla del programa: ${formatProgramFindings(programQuality.findings)}.`;
    }
    if (code === 'QUALITY_FAILED' && quality) {
      return `No pasó Crítica: calidad ${quality.quality_total}/110 tras ${quality.revision_count} revisiones. Fallan ${formatDimensions(quality.blocking_dimensions)}.`;
    }
    if (code === 'DURATION_OUT_OF_RANGE') {
      return 'No se pudo completar el episodio: el guion/audio quedó fuera de la duración objetivo.';
    }
    return `No se pudo completar el episodio (${code}).`;
  }

  function formatDimensions(dimensions = []) {
    const labels = {
      hook: 'gancho',
      clarity: 'claridad',
      conflict: 'conflicto',
      escalation: 'escalada',
      agency: 'agencia',
      coherence: 'coherencia',
      credibility: 'credibilidad',
      originality: 'originalidad',
      retention: 'retención',
      payoff: 'payoff',
      production_fit: 'producción',
    };
    return (dimensions ?? []).map((item) => labels[item] ?? item).join(', ') || 'dimensiones sin detalle';
  }

  function formatProgramFindings(findings = []) {
    const labels = {
      missing_clear_paranormal_threat: 'falto una amenaza paranormal clara',
      missing_haunted_place_anchors: 'faltaron anclas visuales del lugar embrujado',
      weak_story_question: 'falto una pregunta dramatica clara',
      abstract_bargain_not_paranormal: 'el conflicto quedo abstracto y no paranormal',
      fragmented_articles: 'quedaron frases cortadas o fragmentos sueltos',
    };
    return (findings ?? []).map((item) => labels[item] ?? item).join(', ') || 'reglas sin detalle';
  }

  function videoNeedsRetry(detail) {
    return detail && (
      detail.video_status === 'failed'
      || detail.video_status === 'qc_failed'
      || detail.video_qc_passed === false
    );
  }

  function phaseForGeneration(run, stage) {
    return run?.diagnostics?.phases?.find((phase) => phase.key === stage.key) ?? null;
  }

  function phaseDetail(run, stage, index = 0) {
    const phase = phaseForGeneration(run, stage);
    if (phase?.detail) return phase.detail;
    const status = phaseStatus(run, stage, index);
    return phaseStatusDetail(stage, status);
  }

  function phaseStatus(run, stage, index) {
    const phase = phaseForGeneration(run, stage);
    if (phase?.status) return phase.status;
    if (run?.status === 'failed' && index === run.stageIndex) return 'failed';
    if (run?.status === 'running' && index === run.stageIndex) return 'running';
    if (run?.status !== 'failed' && index < run?.stageIndex) return 'completed';
    return 'pending';
  }

  function phaseStatusTone(status) {
    if (status === 'completed') return 'success';
    if (status === 'failed') return 'error';
    if (status === 'running') return 'warning';
    if (status === 'skipped') return 'neutral';
    return 'info';
  }

  function phaseCardClass(status) {
    const classes = {
      completed: 'border-success/45 bg-success/10',
      failed: 'border-error/70 bg-error/10',
      running: 'border-ember-400/80 bg-ember-500/15 shadow-[0_0_0_1px_rgba(251,146,60,0.20)]',
      skipped: 'border-line bg-surface-inset opacity-75',
      pending: 'border-line bg-surface-inset',
    };
    return classes[status] ?? classes.pending;
  }

  function phaseBadgeClass(status) {
    const classes = {
      completed: 'bg-success/20 text-success',
      failed: 'bg-error/20 text-error',
      running: 'bg-ember-300 text-black',
      skipped: 'bg-surface-hover text-ink-secondary',
      pending: 'bg-info/15 text-info',
    };
    return classes[status] ?? classes.pending;
  }

  function phaseStatusDetail(stage, status) {
    const detail = {
      investigacion: {
        completed: 'Investigación completada: ya encontró una señal útil y descartó lo que no servía.',
        running: 'Investigando Reddit y la cola local de oportunidades.',
        pending: 'Pendiente: empezará buscando señales útiles para este programa.',
      },
      concepto: {
        completed: 'Concepto completado: la señal ya se convirtió en una premisa original.',
        running: 'Transformando la señal en una idea propia para Kronara.',
        pending: 'Pendiente: espera una señal aprobada de Investigación.',
      },
      guion: {
        completed: 'Guion completado: escenas, gancho y payoff quedaron ensamblados.',
        running: 'Escribiendo y ajustando escenas, gancho, ritmo y payoff.',
        pending: 'Pendiente: arrancará cuando el concepto esté aprobado.',
      },
      critica: {
        completed: 'Crítica completada: originalidad, narrativa y duración pasaron la revisión.',
        running: 'Revisando calidad narrativa; si falla, pide correcciones concretas.',
        pending: 'Pendiente: revisará calidad y derechos antes de producir.',
      },
      narracion: {
        completed: 'Narración completada: voz y duración real ya fueron medidas.',
        running: 'Midiendo voz, pausas y duración real del episodio.',
        pending: 'Pendiente: se medirá después de aprobar Crítica.',
      },
      produccion: {
        completed: 'Producción completada: visuales, video vertical y QC quedaron listos.',
        running: 'Produciendo visuales locales y componiendo video. Puede tardar varios minutos.',
        pending: 'Pendiente: empezará después de medir voz y duración.',
      },
      guardando: {
        completed: 'Guardado completado: el episodio ya quedó en la biblioteca local.',
        running: 'Guardando archivos, portada, metadatos y registro local.',
        pending: 'Pendiente: solo se activa cuando Producción termina.',
      },
    };
    return detail[stage.key]?.[status] ?? stage.detail;
  }

  function phaseStatusLabel(status) {
    const labels = {
      completed: 'Completado',
      failed: 'Falló',
      running: 'En curso',
      skipped: 'Saltado',
      pending: 'Pendiente',
    };
    return labels[status] ?? status;
  }

  function visibleDiagnosticPhases(run) {
    return (run?.diagnostics?.phases ?? []).filter((phase) => phase.status !== 'pending' || phase.detail);
  }

  function recentToolEvents(run) {
    return (run?.diagnostics?.tool_events ?? []).slice(-10).reverse();
  }

  function recentAgentLogs(run) {
    return (run?.diagnostics?.agent_logs ?? []).slice(-12).reverse();
  }

  function averageDuration(episodesList) {
    const durations = episodesList.map((episode) => Number(episode.duration_seconds)).filter(Boolean);
    if (!durations.length) return '—';
    const seconds = Math.round(durations.reduce((sum, item) => sum + item, 0) / durations.length);
    return formatDuration(seconds);
  }

  function formatDuration(seconds) {
    if (!seconds) return '—';
    const minutes = Math.floor(seconds / 60);
    const rest = Math.round(seconds % 60);
    return `${minutes}:${rest.toString().padStart(2, '0')}`;
  }

  function approvedCount(episodesList) {
    return episodesList.filter((episode) => episode.narrative_passed && episode.originality_passed).length;
  }

  function seasonLabel(episode) {
    const part = episode.part_number ?? episodeIndex(episode);
    return `T${episode.season_number ?? 1} · E${part}`;
  }

  function coverFor(programId) {
    const withCover = episodesFor(programId).find((episode) => episode.cover_image_path);
    const program = programs.find((item) => item.program_id === programId);
    return assetSrc(withCover?.cover_image_path ?? program?.cover_image_path);
  }

  function templateText(template = []) {
    return (template ?? []).join('\n');
  }

  function directivesFromDraft() {
    return templateDraft
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);
  }

  function replaceProgramTemplate(programId, template, source) {
    programs = programs.map((program) => (
      program.program_id === programId
        ? { ...program, narrative_template: template, narrative_template_source: source }
        : program
    ));
    if (selected?.program_id === programId) {
      selected = { ...selected, narrative_template: template, narrative_template_source: source };
    }
  }

  function storyResourceItems() {
    return selected?.story_resource_items ?? [];
  }

  function storyResourceWordCount() {
    return storyResourceDraft.trim().split(/\s+/).filter(Boolean).length;
  }

  function replaceProgramStoryResource(programId, result) {
    programs = programs.map((program) => (
      program.program_id === programId
        ? {
            ...program,
            story_resource_text: result.story_resource_text ?? '',
            story_resource_source: result.story_resource_source ?? 'base',
            story_resource_items: result.story_resource_items ?? [],
          }
        : program
    ));
    if (selected?.program_id === programId) {
      selected = {
        ...selected,
        story_resource_text: result.story_resource_text ?? '',
        story_resource_source: result.story_resource_source ?? 'base',
        story_resource_items: result.story_resource_items ?? [],
      };
    }
  }

  async function saveStoryResources() {
    if (!selected || storyResourceSaving) return;
    storyResourceSaving = true;
    storyResourceNotice = '';
    try {
      const result = await callOperations('programs.resources.save', {
        program_id: selected.program_id,
        text: storyResourceDraft,
      });
      replaceProgramStoryResource(selected.program_id, result);
      storyResourceDraft = result.story_resource_text ?? storyResourceDraft;
      storyResourceNotice = 'Historias guardadas en Recursos y actualizadas para el RAG.';
    } catch (error) {
      storyResourceNotice = 'No se pudo guardar. Pega texto util de historias o plantillas antes de guardar.';
    } finally {
      storyResourceSaving = false;
    }
  }

  async function resetStoryResources() {
    if (!selected || storyResourceSaving) return;
    storyResourceSaving = true;
    storyResourceNotice = '';
    try {
      const result = await callOperations('programs.resources.reset', {
        program_id: selected.program_id,
      });
      replaceProgramStoryResource(selected.program_id, result);
      storyResourceDraft = result.story_resource_text ?? '';
      storyResourceNotice = 'Recursos base restaurados para este programa.';
    } catch (error) {
      storyResourceNotice = 'No se pudo restaurar Recursos.';
    } finally {
      storyResourceSaving = false;
    }
  }

  async function saveTemplate() {
    if (!selected || templateSaving) return;
    templateSaving = true;
    templateNotice = '';
    try {
      const result = await callOperations('programs.template.save', {
        program_id: selected.program_id,
        directives: directivesFromDraft(),
      });
      replaceProgramTemplate(selected.program_id, result.narrative_template ?? [], result.narrative_template_source ?? 'manual');
      templateDraft = templateText(result.narrative_template);
      templateNotice = 'Plantilla guardada para las próximas generaciones.';
    } catch (error) {
      templateNotice = 'No se pudo guardar. La plantilla necesita al menos 3 líneas útiles.';
    } finally {
      templateSaving = false;
    }
  }

  async function resetTemplate() {
    if (!selected || templateSaving) return;
    templateSaving = true;
    templateNotice = '';
    try {
      const result = await callOperations('programs.template.reset', {
        program_id: selected.program_id,
      });
      replaceProgramTemplate(selected.program_id, result.narrative_template ?? [], result.narrative_template_source ?? 'base');
      templateDraft = templateText(result.narrative_template);
      templateNotice = 'Plantilla base restaurada.';
    } catch (error) {
      templateNotice = 'No se pudo restaurar la plantilla.';
    } finally {
      templateSaving = false;
    }
  }

  function formatDate(unixSeconds) {
    if (!unixSeconds) return '—';
    return new Date(unixSeconds * 1000).toLocaleDateString('es', { year: 'numeric', month: 'short', day: 'numeric' });
  }

  function statusTone(episode) {
    if (episode.narrative_passed && episode.originality_passed) return 'success';
    if (episode.narrative_passed === false || episode.originality_passed === false) return 'error';
    return 'neutral';
  }

  function selectEpisode(episode) {
    selectedEpisodeId = episode.story_id;
    episodeDetailTab = 'resumen';
  }

  async function deleteEpisode() {
    const episode = selectedEpisode;
    if (!episode || deletingEpisodeId) return;
    const confirmed = typeof window === 'undefined'
      ? true
      : window.confirm(`¿Eliminar el episodio "${episode.title}"? Esta acción también quitará sus archivos locales.`);
    if (!confirmed) return;

    deletingEpisodeId = episode.story_id;
    createNotice = '';
    try {
      const result = await callOperations('episodes.delete', { story_id: episode.story_id });
      if (result.status !== 'deleted') throw new Error(result.error_code ?? 'delete_failed');
      episodes = episodes.filter((item) => item.story_id !== episode.story_id);
      const { [episode.story_id]: _removed, ...remainingDetails } = episodeDetailCache;
      episodeDetailCache = remainingDetails;
      const remainingEpisodes = episodesFor(selected.program_id);
      selectedEpisodeId = remainingEpisodes[0]?.story_id ?? null;
      createNotice = `Episodio eliminado: "${episode.title}".`;
    } catch (error) {
      createNotice = 'No se pudo eliminar el episodio. Revisa la conexión con la web local.';
    } finally {
      deletingEpisodeId = null;
    }
  }

  function markMediaError(storyId) {
    mediaErrors = { ...mediaErrors, [storyId]: true };
  }

  function episodeIndex(episode) {
    // Kronara has no separate "episode number" field -- only created_at --
    // so this derives a real, honest ordinal (oldest = 1) from the
    // program's actual episode list instead of showing nothing.
    const ascending = [...selectedEpisodes].reverse();
    return ascending.findIndex((item) => item.story_id === episode.story_id) + 1;
  }

  const selectedEpisodes = $derived(selected ? episodesFor(selected.program_id) : []);
  const selectedEpisode = $derived(
    selectedEpisodes.find((episode) => episode.story_id === selectedEpisodeId)
      ?? selectedEpisodes[0]
      ?? null
  );
  const selectedEpisodeDetail = $derived(
    selectedEpisode ? episodeDetailCache[selectedEpisode.story_id] : null
  );
  const selectedGeneration = $derived(
    $episodeGeneration && selected && $episodeGeneration.programId === selected.program_id
      ? $episodeGeneration
      : null
  );
  const listGeneration = $derived(
    $episodeGeneration && !selected && (!initialProgramId || initialProgramId === $episodeGeneration.programId)
      ? $episodeGeneration
      : null
  );

  $effect(() => {
    const episode = selectedEpisode;
    if (!episode || episode.story_id in episodeDetailCache) return;
    episodeDetailLoading = true;
    callOperations('episodes.get', { story_id: episode.story_id })
      .then((detail) => {
        episodeDetailCache = { ...episodeDetailCache, [episode.story_id]: detail };
      })
      .catch(() => {
        episodeDetailCache = { ...episodeDetailCache, [episode.story_id]: null };
      })
      .finally(() => {
        episodeDetailLoading = false;
      });
  });
</script>

{#if loadError}
  <p class="text-[13px] text-ink-secondary">No se pudo cargar la parrilla de programas. Inicia la web local y verifica que Python esté conectado.</p>
{:else if selected}
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <button class="flex items-center gap-1.5 text-[12.5px] text-ink-tertiary hover:text-ink" onclick={() => (selected = null)}>
        <Icon name="chevron-left" size={14} /> Programas
      </button>
      <button
        class="flex items-center gap-1.5 rounded-full bg-purple-500 px-4 py-2 text-[12.5px] font-medium text-ink hover:bg-purple-600 disabled:cursor-not-allowed disabled:opacity-40"
        onclick={() => createEpisode()}
        disabled={creating || connection !== 'connected'}
      >
        <Icon name="plus" size={14} />
        {creating ? 'Comprobando generación…' : 'Crear episodio'}
      </button>
    </div>

    {#if createNotice}
      <p class="rounded-lg border border-line bg-surface-inset px-3 py-2 text-[12.5px] text-ink-secondary">{createNotice}</p>
    {/if}

    {#if selectedGeneration}
      <Card>
        {@const activeStage = GENERATION_STAGES[selectedGeneration.stageIndex]}
        {@const percent = generationPercent(selectedGeneration)}
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <span class="live-dot h-2 w-2 rounded-full" class:bg-ember-500={selectedGeneration.status === 'running'} class:bg-success={selectedGeneration.status === 'completed'} class:bg-error={selectedGeneration.status === 'failed'}></span>
              <p class="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-tertiary">{selectedGeneration.status === 'running' ? 'Generando episodio' : selectedGeneration.status === 'completed' ? 'Episodio generado' : 'Generación detenida'}</p>
            </div>
            <h3 class="mt-2 font-display text-lg font-semibold text-ink">{selectedGeneration.title}</h3>
            <p class="mt-1 text-[12.5px] text-ink-secondary">{selectedGeneration.message}</p>
          </div>
          <div class="text-right">
            <p class="font-mono text-lg font-semibold text-ink">{percent}%</p>
            <p class="text-[10.5px] text-ink-tertiary">{formatElapsed(selectedGeneration.elapsedSeconds)}</p>
            {#if selectedGeneration.status === 'failed'}
              <div class="mt-2 flex flex-wrap justify-end gap-1.5">
                <button
                  class="inline-flex items-center gap-1.5 rounded-lg border border-ember-500/40 px-3 py-1.5 text-[11.5px] font-medium text-ember-300 transition hover:bg-ember-500/10 disabled:cursor-not-allowed disabled:opacity-50"
                  onclick={retrySelectedProgram}
                  disabled={creating || connection !== 'connected'}
                >
                  <Icon name="refresh" size={13} />
                  Reintentar
                </button>
                <button
                  class="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-[11.5px] font-medium text-ink-tertiary transition hover:border-ink-tertiary hover:text-ink"
                  onclick={clearEpisodeGeneration}
                >
                  Abandonar
                </button>
              </div>
            {:else if selectedGeneration.status === 'running'}
              <button
                class="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-[11.5px] font-medium text-ink-tertiary transition hover:border-ink-tertiary hover:text-ink"
                onclick={clearEpisodeGeneration}
                title="Solo limpia el indicador local. Si el backend sigue corriendo, mátalo con Get-Process kronara-sidecar."
              >
                Ocultar indicador
              </button>
            {/if}
          </div>
        </div>
        <div class="mt-4 h-1.5 overflow-hidden rounded-full bg-line">
          <div class="h-full rounded-full bg-ember-500 transition-all duration-500" style={`width:${percent}%`}></div>
        </div>
        <div class="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {#each GENERATION_STAGES as stage, index}
            {@const status = phaseStatus(selectedGeneration, stage, index)}
            <div
              class={`rounded-lg border p-2.5 transition ${phaseCardClass(status)}`}
            >
              <div class="flex items-center justify-between gap-2">
                <div class="flex min-w-0 items-center gap-2">
                  <Icon name={stage.icon} size={13} class="text-ink-tertiary" />
                  <p class="truncate text-[11.5px] font-medium text-ink">{stage.label}</p>
                </div>
                <span class={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10.5px] font-semibold ${phaseBadgeClass(status)}`}>{phaseStatusLabel(status)}</span>
              </div>
              <p class="mt-1 line-clamp-3 text-[10.5px] leading-relaxed text-ink-secondary">{phaseDetail(selectedGeneration, stage, index)}</p>
            </div>
          {/each}
        </div>
        {#if selectedGeneration.diagnostics}
          <div class="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-[1.15fr_0.85fr]">
            <div class="rounded-lg border border-line bg-surface-inset p-3">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <p class="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-tertiary">Diagnóstico real del run</p>
                {#if selectedGeneration.diagnostics.program_quality_failure}
                  <Badge tone="error">Plantilla del programa</Badge>
                {:else if selectedGeneration.diagnostics.quality_failure}
                  <Badge tone="error">Calidad {selectedGeneration.diagnostics.quality_failure.quality_total}/110</Badge>
                {/if}
              </div>
              {#if selectedGeneration.diagnostics.program_quality_failure}
                {@const programQuality = selectedGeneration.diagnostics.program_quality_failure}
                <div class="mt-3 rounded-lg border border-error/30 bg-error/10 px-3 py-2">
                  <p class="text-[10px] uppercase tracking-wide text-error">Reglas del programa que no pasaron</p>
                  <p class="mt-1 text-[12px] leading-relaxed text-ink">{formatProgramFindings(programQuality.findings)}</p>
                  <p class="mt-1 text-[11px] text-ink-tertiary">Este bloqueo ocurre en Critica: el guion puede tener voz medida, pero todavia no respeta la plantilla narrativa del programa.</p>
                </div>
              {:else if selectedGeneration.diagnostics.quality_failure}
                {@const quality = selectedGeneration.diagnostics.quality_failure}
                <div class="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
                  <div class="rounded-lg border border-line bg-surface px-3 py-2">
                    <p class="text-[10px] uppercase tracking-wide text-ink-tertiary">Revisiones</p>
                    <p class="mt-1 text-[13px] font-semibold text-ink">{quality.revision_count}</p>
                  </div>
                  <div class="rounded-lg border border-line bg-surface px-3 py-2 sm:col-span-2">
                    <p class="text-[10px] uppercase tracking-wide text-ink-tertiary">Dimensiones que no pasaron</p>
                    <p class="mt-1 text-[12px] text-ink">{formatDimensions(quality.blocking_dimensions)}</p>
                  </div>
                </div>
                <div class="mt-2 rounded-lg border border-line bg-surface px-3 py-2">
                  <p class="text-[10px] uppercase tracking-wide text-ink-tertiary">Lo que pidió corregir Crítica</p>
                  <p class="mt-1 text-[12px] leading-relaxed text-ink-secondary">{(quality.issues ?? []).join(' ') || 'No llegaron problemas textuales del modelo; se usaron los puntajes por dimensión para guiar la revisión.'}</p>
                </div>
              {:else}
                <p class="mt-2 text-[12px] text-ink-secondary">No hubo bloqueo de calidad registrado para este run.</p>
              {/if}
              <ul class="mt-3 space-y-1.5">
                {#each visibleDiagnosticPhases(selectedGeneration) as phase}
                  <li class="flex items-start justify-between gap-3 rounded-lg border border-line bg-surface px-3 py-2">
                    <div class="min-w-0">
                      <p class="text-[12px] font-medium text-ink">{phase.label}</p>
                      <p class="mt-0.5 text-[11px] leading-relaxed text-ink-tertiary">{phase.detail || 'Sin detalle todavía.'}</p>
                    </div>
                    <Badge tone={phaseStatusTone(phase.status)}>{phaseStatusLabel(phase.status)}</Badge>
                  </li>
                {/each}
              </ul>
            </div>
            <div class="rounded-lg border border-line bg-surface-inset p-3">
              <p class="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-tertiary">Decisiones de agentes</p>
              {#if recentAgentLogs(selectedGeneration).length === 0}
                <p class="mt-2 text-[12px] text-ink-tertiary">Sin decisiones estructuradas para este run todavía.</p>
              {:else}
                <ul class="mt-3 space-y-1.5">
                  {#each recentAgentLogs(selectedGeneration) as log}
                    <li class="rounded-lg border border-line bg-surface px-3 py-2">
                      <div class="flex items-center justify-between gap-2">
                        <p class="truncate text-[12px] font-medium text-ink">{log.agent_id}</p>
                        <span class="rounded-full bg-purple-500/15 px-2 py-0.5 text-[10px] font-medium text-purple-300">{log.action}</span>
                      </div>
                      <p class="mt-0.5 line-clamp-2 text-[11px] leading-relaxed text-ink-tertiary">{log.detail || 'sin detalle'}</p>
                    </li>
                  {/each}
                </ul>
              {/if}
              <p class="mt-4 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-tertiary">Modelos y herramientas</p>
              {#if recentToolEvents(selectedGeneration).length === 0}
                <p class="mt-2 text-[12px] text-ink-tertiary">Sin trazas visibles para este run.</p>
              {:else}
                <ul class="mt-3 space-y-1.5">
                  {#each recentToolEvents(selectedGeneration) as event}
                    <li class="rounded-lg border border-line bg-surface px-3 py-2">
                      <div class="flex items-center justify-between gap-2">
                        <p class="truncate text-[12px] font-medium text-ink">{event.tool_id}</p>
                        <Badge tone={event.status === 'completed' ? 'success' : event.status === 'failed' || event.status === 'blocked' ? 'error' : 'neutral'}>{event.status}</Badge>
                      </div>
                      <p class="mt-0.5 truncate text-[11px] text-ink-tertiary">{event.agent_id} · {event.summary || 'sin resumen'}</p>
                    </li>
                  {/each}
                </ul>
              {/if}
            </div>
          </div>
        {/if}
      </Card>
    {/if}

    <Card>
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div class="flex items-start gap-3.5">
          {#if coverFor(selected.program_id)}
            <img src={coverFor(selected.program_id)} alt="" class="h-14 w-14 shrink-0 rounded-xl object-cover" />
          {:else}
            <span
              class="grid h-14 w-14 shrink-0 place-items-center rounded-xl font-display text-lg font-bold text-ink"
              style={`background:${programGradient(selected.program_id)}`}
            >{selected.name.charAt(0)}</span>
          {/if}
          <div>
            <Badge tone="purple">{selected.genre}</Badge>
            <h2 class="mt-2 font-display text-xl font-bold text-ink">{selected.name}</h2>
            <p class="mt-1 max-w-xl text-[13px] text-ink-secondary">{selected.description}</p>
          </div>
        </div>
        <dl class="grid grid-cols-2 gap-3 text-right sm:grid-cols-4">
          <div><dt class="text-[10.5px] text-ink-tertiary">Día</dt><dd class="mt-0.5 text-[12.5px] capitalize text-ink">{selected.weekday}</dd></div>
          <div><dt class="text-[10.5px] text-ink-tertiary">Duración objetivo</dt><dd class="mt-0.5 text-[12.5px] text-ink">{selected.target_duration_seconds}s</dd></div>
          <div><dt class="text-[10.5px] text-ink-tertiary">Episodios</dt><dd class="mt-0.5 text-[12.5px] text-ink">{episodeCountFor(selected.program_id)}</dd></div>
          <div><dt class="text-[10.5px] text-ink-tertiary">Estado</dt><dd class="mt-0.5"><Badge tone="success">Activo</Badge></dd></div>
        </dl>
      </div>
    </Card>

    <div class="flex gap-1 overflow-x-auto border-b border-line">
      {#each TABS as tab}
        <button
          class="shrink-0 border-b-2 px-3 py-2 text-[12.5px] font-medium transition-colors"
          class:border-purple-500={activeTab === tab}
          class:text-ink={activeTab === tab}
          class:border-transparent={activeTab !== tab}
          class:text-ink-tertiary={activeTab !== tab}
          onclick={() => (activeTab = tab)}
        >
          {TAB_LABELS[tab]}
        </button>
      {/each}
    </div>

    <div class="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_300px]">
      <Card subtitle={activeTab === 'episodios' && selectedEpisodes.length ? `${selectedEpisodes.length} episodio(s)` : undefined}>
        {#if activeTab === 'resumen'}
          {#if selectedEpisodes.length > 0}
            <div class="space-y-4">
              <div class="grid grid-cols-2 gap-2 lg:grid-cols-4">
                <div class="rounded-lg border border-line bg-surface-inset px-3 py-2.5">
                  <p class="text-[10px] uppercase tracking-wide text-ink-tertiary">Episodios</p>
                  <p class="mt-1 font-display text-xl font-semibold text-ink">{selectedEpisodes.length}</p>
                  <p class="mt-1 text-[10.5px] text-success">Temporada 1</p>
                </div>
                <div class="rounded-lg border border-line bg-surface-inset px-3 py-2.5">
                  <p class="text-[10px] uppercase tracking-wide text-ink-tertiary">Aprobados</p>
                  <p class="mt-1 font-display text-xl font-semibold text-ink">{approvedCount(selectedEpisodes)}</p>
                  <p class="mt-1 text-[10.5px] text-ink-tertiary">Crítica y originalidad</p>
                </div>
                <div class="rounded-lg border border-line bg-surface-inset px-3 py-2.5">
                  <p class="text-[10px] uppercase tracking-wide text-ink-tertiary">Duración promedio</p>
                  <p class="mt-1 font-display text-xl font-semibold text-ink">{averageDuration(selectedEpisodes)}</p>
                  <p class="mt-1 text-[10.5px] text-ink-tertiary">Voz medida</p>
                </div>
                <div class="rounded-lg border border-line bg-surface-inset px-3 py-2.5">
                  <p class="text-[10px] uppercase tracking-wide text-ink-tertiary">Estado</p>
                  <p class="mt-1 font-display text-xl font-semibold text-ink">{selectedGeneration ? 'Produciendo' : 'Activo'}</p>
                  <p class="mt-1 text-[10.5px]" class:text-ember-400={selectedGeneration} class:text-success={!selectedGeneration}>{selectedGeneration ? GENERATION_STAGES[selectedGeneration.stageIndex].label : 'Listo para nuevo episodio'}</p>
                </div>
              </div>
              <div class="grid grid-cols-1 gap-3 lg:grid-cols-[1.2fr_0.8fr]">
                <div class="rounded-lg border border-line bg-surface-inset p-3">
                  <div class="flex items-center justify-between gap-2">
                    <p class="text-[12px] font-semibold text-ink">Episodios recientes</p>
                    <button class="text-[11px] font-medium text-purple-300 hover:text-purple-200" onclick={() => (activeTab = 'episodios')}>Ver todos</button>
                  </div>
                  <ul class="mt-3 divide-y divide-line-subtle">
                    {#each selectedEpisodes.slice(0, 4) as episode}
                      <li class="flex items-center gap-3 py-2">
                        {#if assetSrc(episode.cover_image_path)}
                          <img src={assetSrc(episode.cover_image_path)} alt="" class="h-10 w-12 shrink-0 rounded-md object-cover" />
                        {:else}
                          <span class="grid h-10 w-12 shrink-0 place-items-center rounded-md bg-surface text-ink-tertiary">
                            <Icon name="film" size={14} />
                          </span>
                        {/if}
                        <div class="min-w-0 flex-1">
                          <p class="truncate text-[12.5px] font-medium text-ink">{episode.title}</p>
                          <p class="mt-0.5 text-[10.5px] text-ink-tertiary">{seasonLabel(episode)} · {formatDate(episode.created_at)}</p>
                        </div>
                        <Badge tone={statusTone(episode)}>{episode.narrative_passed && episode.originality_passed ? 'Aprobado' : 'Revisar'}</Badge>
                      </li>
                    {/each}
                  </ul>
                </div>
                <div class="rounded-lg border border-line bg-surface-inset p-3">
                  <p class="text-[12px] font-semibold text-ink">Temporada actual</p>
                  <div class="mt-3 space-y-2">
                    <div class="flex items-center justify-between text-[12px]"><span class="text-ink-tertiary">Programa</span><span class="font-medium text-ink">{selected.name}</span></div>
                    <div class="flex items-center justify-between text-[12px]"><span class="text-ink-tertiary">Día</span><span class="font-medium capitalize text-ink">{selected.weekday}</span></div>
                    <div class="flex items-center justify-between text-[12px]"><span class="text-ink-tertiary">Objetivo</span><span class="font-medium text-ink">{selected.target_duration_seconds}s</span></div>
                    <div class="flex items-center justify-between text-[12px]"><span class="text-ink-tertiary">Siguiente número</span><span class="font-medium text-ink">E{selectedEpisodes.length + 1}</span></div>
                  </div>
                </div>
              </div>
            </div>
          {:else}
            <p class="text-[13px] text-ink-secondary">Sin episodios publicados aún para {selected.name}. Créalos desde Estudio o espera a que el Agente B (parrilla automática) los produzca en su horario.</p>
          {/if}
        {:else if activeTab === 'episodios'}
          {#if loading}
            <p class="text-[13px] text-ink-secondary">Cargando…</p>
          {:else if selectedGeneration && selectedEpisodes.length === 0}
            <div class="rounded-lg border border-ember-500/35 bg-ember-500/10 px-3 py-2.5">
              <p class="text-[12.5px] font-medium text-ink">Generación en curso para {selected.name}</p>
              <p class="mt-1 text-[11.5px] text-ink-tertiary">El episodio aparecerá aquí cuando el backend termine. Fase actual: {GENERATION_STAGES[selectedGeneration.stageIndex].label}.</p>
            </div>
          {:else if selectedEpisodes.length === 0}
            <p class="text-[13px] text-ink-secondary">
              Sin episodios todavía para {selected.name}. Créalos desde Estudio ("Crear historia gobernada") o espera a que el Agente B produzca la parrilla automáticamente.
            </p>
          {:else}
            <div class="overflow-x-auto">
              <table class="w-full text-left text-[12.5px]">
                <thead>
                  <tr class="border-b border-line text-[10.5px] uppercase tracking-wide text-ink-tertiary">
                    <th class="pb-2 pr-4 font-medium">Episodio</th>
                    <th class="pb-2 pr-4 font-medium">Fecha</th>
                    <th class="pb-2 pr-4 font-medium">Duración</th>
                    <th class="pb-2 pr-4 font-medium">Generador / Crítico</th>
                    <th class="pb-2 font-medium">Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {#if selectedGeneration}
                    <tr class="border-b border-ember-500/30 bg-ember-500/10">
                      <td class="py-2.5 pr-4 text-ink">
                        <div class="flex items-center gap-2.5">
                          <span class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-ember-500/15 text-ember-400">
                            <Icon name={GENERATION_STAGES[selectedGeneration.stageIndex].icon} size={14} />
                          </span>
                          <span class="truncate">Generando: {selectedGeneration.programName ?? selected.name}</span>
                        </div>
                      </td>
                      <td class="py-2.5 pr-4 text-ink-tertiary">{formatElapsed(selectedGeneration.elapsedSeconds)}</td>
                      <td class="py-2.5 pr-4 text-ink-tertiary">{generationPercent(selectedGeneration)}%</td>
                      <td class="py-2.5 pr-4 text-ink-tertiary">{GENERATION_STAGES[selectedGeneration.stageIndex].label}</td>
                      <td class="py-2.5"><Badge tone={selectedGeneration.status === 'failed' ? 'error' : 'neutral'}>{selectedGeneration.status === 'failed' ? 'Falló' : 'En curso'}</Badge></td>
                    </tr>
                  {/if}
                  {#each selectedEpisodes as episode (episode.story_id)}
                    <tr
                      class="cursor-pointer border-b border-line-subtle transition-colors hover:bg-surface-inset"
                      class:bg-surface-inset={selectedEpisode?.story_id === episode.story_id}
                      onclick={() => selectEpisode(episode)}
                    >
                      <td class="py-2.5 pr-4 text-ink">
                        <div class="flex items-center gap-2.5">
                          {#if assetSrc(episode.cover_image_path)}
                            <img src={assetSrc(episode.cover_image_path)} alt="" class="h-9 w-9 shrink-0 rounded-lg object-cover" />
                          {:else}
                            <span class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-surface-inset text-ink-tertiary">
                              <Icon name="film" size={14} />
                            </span>
                          {/if}
                          <span class="truncate">{episode.title}</span>
                        </div>
                      </td>
                      <td class="py-2.5 pr-4 text-ink-tertiary">{formatDate(episode.created_at)}</td>
                      <td class="py-2.5 pr-4 text-ink-tertiary">{episode.duration_seconds ? `${Math.round(episode.duration_seconds)}s` : '—'}</td>
                      <td class="py-2.5 pr-4 font-mono text-ink-tertiary">{episode.generator_family ?? '—'} / {episode.critic_family ?? '—'}</td>
                      <td class="py-2.5">
                        <Badge tone={statusTone(episode)}>
                          {episode.narrative_passed && episode.originality_passed ? 'Aprobado' : 'Revisar'}
                        </Badge>
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {/if}
        {:else if activeTab === 'calendario'}
          <div class="space-y-3">
            <div class="rounded-lg border border-line bg-surface-inset p-3">
              <p class="text-[11px] text-ink-tertiary">Horario recurrente</p>
              <p class="mt-1 text-[13px] capitalize text-ink">Cada {WEEKDAY_LABELS[selected.weekday] ?? selected.weekday}, vía la parrilla automática (Agente B).</p>
            </div>
            {#if selectedEpisodes.length === 0}
              <p class="text-[13px] text-ink-secondary">Sin episodios todavía -- aquí aparecerá la fecha de cada uno en cuanto se creen.</p>
            {:else}
              <ul class="space-y-2">
                {#each selectedEpisodes as episode (episode.story_id)}
                  <li class="flex items-center justify-between rounded-lg border border-line bg-surface-inset px-3 py-2.5 text-[12.5px]">
                    <span class="text-ink">{episode.title}</span>
                    <span class="text-ink-tertiary">{formatDate(episode.created_at)}</span>
                  </li>
                {/each}
              </ul>
            {/if}
          </div>
        {:else if activeTab === 'configuracion'}
          <dl class="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div class="rounded-lg border border-line bg-surface-inset p-3">
              <dt class="text-[10.5px] text-ink-tertiary">program_id</dt>
              <dd class="mt-1 font-mono text-[12.5px] text-ink">{selected.program_id}</dd>
            </div>
            <div class="rounded-lg border border-line bg-surface-inset p-3">
              <dt class="text-[10.5px] text-ink-tertiary">Estilo visual</dt>
              <dd class="mt-1 font-mono text-[12.5px] text-ink">{selected.visual_style_id}</dd>
            </div>
            <div class="rounded-lg border border-line bg-surface-inset p-3">
              <dt class="text-[10.5px] text-ink-tertiary">Duración objetivo</dt>
              <dd class="mt-1 text-[12.5px] text-ink">{selected.target_duration_seconds} segundos</dd>
            </div>
            <div class="rounded-lg border border-line bg-surface-inset p-3">
              <dt class="text-[10.5px] text-ink-tertiary">Día de publicación</dt>
              <dd class="mt-1 text-[12.5px] capitalize text-ink">{selected.weekday}</dd>
            </div>
          </dl>
          <div class="mt-4 rounded-lg border border-line bg-surface-inset p-3">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p class="font-display text-[14px] font-semibold text-ink">Plantilla narrativa</p>
                <p class="mt-1 text-[11px] text-ink-tertiary">Origen: {selected.narrative_template_source === 'manual' ? 'manual guardada' : 'base del programa'}</p>
              </div>
              <Badge tone={selected.narrative_template_source === 'manual' ? 'success' : 'neutral'}>
                {selected.narrative_template_source === 'manual' ? 'Manual' : 'Base'}
              </Badge>
            </div>
            <textarea
              bind:value={templateDraft}
              class="mt-3 min-h-64 w-full resize-y rounded-lg border border-line bg-surface px-3 py-2.5 font-mono text-[12px] leading-relaxed text-ink outline-none transition focus:border-purple-500"
              spellcheck="false"
            ></textarea>
            <div class="mt-3 flex flex-wrap items-center justify-between gap-3">
              <p class="text-[11px] text-ink-tertiary">{directivesFromDraft().length} regla(s)</p>
              <div class="flex items-center gap-2">
                <button class="rounded-lg border border-line px-3 py-2 text-[12px] font-medium text-ink-secondary transition hover:border-purple-500 hover:text-ink disabled:opacity-50" onclick={resetTemplate} disabled={templateSaving}>
                  Restaurar base
                </button>
                <button class="rounded-lg bg-purple-500 px-3 py-2 text-[12px] font-semibold text-ink transition hover:bg-purple-400 disabled:opacity-50" onclick={saveTemplate} disabled={templateSaving || directivesFromDraft().length < 3}>
                  {templateSaving ? 'Guardando...' : 'Guardar plantilla'}
                </button>
              </div>
            </div>
            {#if templateNotice}
              <p class="mt-3 rounded-lg border border-line bg-surface px-3 py-2 text-[11.5px] text-ink-secondary">{templateNotice}</p>
            {/if}
          </div>
        {:else if activeTab === 'personajes'}
          <p class="text-[13px] text-ink-secondary">La portada premium ya funciona como referencia visual del episodio: el pipeline la pasa a las imágenes de escena para mantener personaje, lugar, paleta y amenaza alineados con el guion completo.</p>
        {:else if activeTab === 'analiticas'}
          <p class="text-[13px] text-ink-secondary">Reproducciones, retención y suscriptores de {selected.name} aparecerán aquí en cuanto Kronara Pulse pueda leer métricas reales de las plataformas conectadas. Hoy no hay ninguna cuenta de YouTube/Spotify/Meta enlazada, así que no hay nada real que mostrar todavía.</p>
        {:else if activeTab === 'recursos'}
          <div class="space-y-4">
            <div>
              <div class="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p class="font-display text-[14px] font-semibold text-ink">Plantillas RAG del programa</p>
                  <p class="mt-1 text-[12px] text-ink-secondary">Historias ejemplo y moldes que los agentes consultan como referencia de estructura, tono y anclas visuales.</p>
                </div>
                <Badge tone={selected.story_resource_source === 'manual' ? 'success' : 'neutral'}>
                  {selected.story_resource_source === 'manual' ? 'Manual' : 'Base'}
                </Badge>
              </div>
            </div>
            <div class="grid grid-cols-1 gap-2">
              {#each storyResourceItems() as template}
                <article class="rounded-lg border border-line bg-surface-inset p-3">
                  <div class="flex flex-wrap items-center justify-between gap-2">
                    <p class="text-[12.5px] font-semibold text-ink">{template.title}</p>
                    <Badge tone="neutral">{template.length}</Badge>
                  </div>
                  <p class="mt-1 text-[11.5px] leading-relaxed text-ink-secondary">{template.focus}</p>
                </article>
              {/each}
            </div>
            <div class="rounded-lg border border-line bg-surface-inset p-3">
              <div class="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p class="font-medium text-[12px] text-ink">Editor manual para RAG</p>
                  <p class="mt-1 text-[11.5px] text-ink-secondary">Pega aqui historias completas o ajusta las existentes. Al guardar, quedan disponibles para las proximas generaciones.</p>
                </div>
                <span class="font-mono text-[11px] text-ink-tertiary">{storyResourceWordCount()} palabras</span>
              </div>
              <textarea
                bind:value={storyResourceDraft}
                class="mt-3 min-h-96 w-full resize-y rounded-lg border border-line bg-surface px-3 py-2.5 font-mono text-[12px] leading-relaxed text-ink outline-none transition focus:border-purple-500"
                spellcheck="false"
              ></textarea>
              <div class="mt-3 flex flex-wrap items-center justify-between gap-3">
                <p class="text-[11px] text-ink-tertiary">Se guarda como recurso propio, no como copia obligatoria del guion.</p>
                <div class="flex items-center gap-2">
                  <button class="rounded-lg border border-line px-3 py-2 text-[12px] font-medium text-ink-secondary transition hover:border-purple-500 hover:text-ink disabled:opacity-50" onclick={resetStoryResources} disabled={storyResourceSaving}>
                    Restaurar base
                  </button>
                  <button class="rounded-lg bg-purple-500 px-3 py-2 text-[12px] font-semibold text-ink transition hover:bg-purple-400 disabled:opacity-50" onclick={saveStoryResources} disabled={storyResourceSaving || storyResourceDraft.trim().length < 80}>
                    {storyResourceSaving ? 'Guardando...' : 'Guardar en RAG'}
                  </button>
                </div>
              </div>
              {#if storyResourceNotice}
                <p class="mt-3 rounded-lg border border-line bg-surface px-3 py-2 text-[11.5px] text-ink-secondary">{storyResourceNotice}</p>
              {/if}
            </div>
            <div class="rounded-lg border border-line bg-surface-inset p-3">
              <p class="font-medium text-[12px] text-ink">Musica y SFX</p>
              <p class="mt-1 text-[12px] text-ink-secondary">Se muestran cuando el episodio trae voz por escena, storyboard, biblioteca de recursos y mezcla final; si falta algo, el detalle del episodio enseña las etiquetas pedidas y las que no se resolvieron.</p>
            </div>
          </div>
        {/if}
      </Card>
      <div class="space-y-4">
        {#if activeTab === 'episodios' && selectedEpisode}
          <Card title="Episodio seleccionado">
            {#if !mediaErrors[selectedEpisode.story_id] && assetSrc(selectedEpisode.video_path)}
              <!-- svelte-ignore a11y_media_has_caption -->
              <video
                src={assetSrc(selectedEpisode.video_path)}
                poster={assetSrc(selectedEpisode.cover_image_path) ?? undefined}
                type="video/mp4"
                controls
                preload="metadata"
                playsinline
                onerror={() => markMediaError(selectedEpisode.story_id)}
                class="w-full rounded-lg bg-black"
              ></video>
            {:else if assetSrc(selectedEpisode.cover_image_path)}
              <img src={assetSrc(selectedEpisode.cover_image_path)} alt="" class="w-full rounded-lg object-cover" />
            {:else}
              <div class="grid aspect-video place-items-center rounded-lg bg-surface-inset text-ink-tertiary">
                <Icon name="film" size={22} />
              </div>
            {/if}
            <div class="mt-3 flex items-start justify-between gap-2">
              <p class="font-display text-[13px] font-semibold text-ink">{selectedEpisode.title}</p>
              <Badge tone={statusTone(selectedEpisode)}>#{episodeIndex(selectedEpisode)}</Badge>
            </div>
            <dl class="mt-2 grid grid-cols-2 gap-2 text-[11.5px]">
              <div><dt class="text-ink-tertiary">Fecha</dt><dd class="text-ink">{formatDate(selectedEpisode.created_at)}</dd></div>
              <div><dt class="text-ink-tertiary">Duración real / objetivo</dt><dd class="text-ink">{selectedEpisode.duration_seconds ? `${Math.round(selectedEpisode.duration_seconds)}s` : '—'} / {selected.target_duration_seconds}s</dd></div>
              <div><dt class="text-ink-tertiary">Formato</dt><dd class="text-ink">{selectedEpisode.video_status === 'completed' ? 'Video 9:16' : 'Solo guion'}</dd></div>
              <div><dt class="text-ink-tertiary">Video</dt><dd class="text-ink">{selectedEpisode.video_status ?? 'no_configurado'}</dd></div>
            </dl>

            <div class="mt-3 flex flex-wrap gap-1 border-t border-line pt-3">
              {#each EPISODE_DETAIL_TABS as tab}
                <button
                  class="rounded-full px-2.5 py-1 text-[10.5px] font-medium transition-colors"
                  class:bg-purple-500={episodeDetailTab === tab}
                  class:text-ink={episodeDetailTab === tab}
                  class:text-ink-tertiary={episodeDetailTab !== tab}
                  class:hover:bg-surface-inset={episodeDetailTab !== tab}
                  onclick={() => (episodeDetailTab = tab)}
                >
                  {EPISODE_DETAIL_TAB_LABELS[tab]}
                </button>
              {/each}
            </div>

            <div class="mt-3">
              {#if episodeDetailLoading && !selectedEpisodeDetail}
                <p class="text-[12px] text-ink-tertiary">Cargando detalle…</p>
              {:else if selectedEpisodeDetail === null}
                <p class="text-[12px] text-ink-tertiary">No se pudo cargar el detalle de este episodio.</p>
              {:else if selectedEpisodeDetail}
                {#if episodeDetailTab === 'resumen'}
                  {#if selectedEpisodeDetail.hook}
                    <p class="text-[12px] leading-relaxed text-ink-secondary">{selectedEpisodeDetail.hook}</p>
                  {:else}
                    <p class="text-[12px] text-ink-tertiary">Sin sinopsis guardada para este episodio.</p>
                  {/if}
                  <dl class="mt-2 grid grid-cols-2 gap-2 text-[11px]">
                    <div><dt class="text-ink-tertiary">Guion</dt><dd><Badge tone={selectedEpisodeDetail.narrative_passed ? 'success' : 'error'}>{selectedEpisodeDetail.narrative_passed ? 'Aprobado' : 'Revisar'}</Badge></dd></div>
                    <div><dt class="text-ink-tertiary">Originalidad</dt><dd><Badge tone={selectedEpisodeDetail.originality_passed ? 'success' : 'error'}>{selectedEpisodeDetail.originality_passed ? 'Aprobada' : 'Revisar'}</Badge></dd></div>
                  </dl>
                {:else if episodeDetailTab === 'guion'}
                  <p class="max-h-80 overflow-y-auto whitespace-pre-wrap text-[11.5px] leading-relaxed text-ink-secondary">{selectedEpisodeDetail.script}</p>
                {:else if episodeDetailTab === 'recursos'}
                  {#if Object.keys(selectedEpisodeDetail.video_source_kind_counts ?? {}).length > 0}
                    <p class="text-[11px] text-ink-tertiary">Mezcla de fuentes visuales de este episodio:</p>
                    <div class="mt-2 flex flex-wrap gap-1.5">
                      {#each Object.entries(selectedEpisodeDetail.video_source_kind_counts) as [kind, count]}
                        <span class="rounded-full border border-line bg-surface-inset px-2 py-0.5 text-[10.5px] text-ink-tertiary">{kind}: {count}</span>
                      {/each}
                    </div>
                  {:else}
                    <p class="text-[12px] text-ink-tertiary">Sin recursos visuales registrados (episodio de solo texto, o generado antes de esta métrica).</p>
                  {/if}
                  <div class="mt-3 space-y-3">
                    <div class="rounded-lg border border-line bg-surface-inset p-3">
                      <p class="font-medium text-[12px] text-ink">MÃºsica</p>
                      {#if selectedEpisodeDetail.music_path}
                        <p class="mt-1 truncate font-mono text-[10.5px] text-ink-tertiary">{selectedEpisodeDetail.music_path}</p>
                      {:else}
                        <p class="mt-1 text-[11.5px] text-ink-tertiary">Sin pista musical asignada para este episodio.</p>
                      {/if}
                    </div>
                    <div class="rounded-lg border border-line bg-surface-inset p-3">
                      <p class="font-medium text-[12px] text-ink">SFX</p>
                      {#if (selectedEpisodeDetail.sfx_cue_tags ?? []).length > 0}
                        <div class="mt-2 flex flex-wrap gap-1.5">
                          {#each selectedEpisodeDetail.sfx_cue_tags as tag}
                            <Badge tone={(selectedEpisodeDetail.sfx_resolved_paths ?? {})[tag] ? 'success' : 'neutral'}>
                              {tag}
                            </Badge>
                          {/each}
                        </div>
                        {#if (selectedEpisodeDetail.sfx_missing_tags ?? []).length > 0}
                          <p class="mt-2 text-[11px] text-warning">Faltan en biblioteca: {selectedEpisodeDetail.sfx_missing_tags.join(', ')}</p>
                        {/if}
                      {:else}
                        <p class="mt-1 text-[11.5px] text-ink-tertiary">El guion no activÃ³ SFX por palabra clave.</p>
                      {/if}
                    </div>
                  </div>
                {:else if episodeDetailTab === 'produccion'}
                  <dl class="grid grid-cols-2 gap-2 text-[11px]">
                    <div><dt class="text-ink-tertiary">Escenas</dt><dd class="text-ink">{selectedEpisodeDetail.video_scene_count ?? '—'}</dd></div>
                    <div><dt class="text-ink-tertiary">Tomas</dt><dd class="text-ink">{selectedEpisodeDetail.video_shot_count ?? '—'}</dd></div>
                    <div><dt class="text-ink-tertiary">Loudness</dt><dd class="text-ink">{selectedEpisodeDetail.video_integrated_lufs != null ? `${selectedEpisodeDetail.video_integrated_lufs.toFixed(1)} LUFS` : '—'}</dd></div>
                    <div><dt class="text-ink-tertiary">QC</dt><dd><Badge tone={selectedEpisodeDetail.video_qc_passed ? 'success' : 'error'}>{selectedEpisodeDetail.video_qc_passed ? 'Aprobado' : 'Con problemas'}</Badge></dd></div>
                  </dl>
                  {#if (selectedEpisodeDetail.video_qc_issues ?? []).length > 0}
                    <ul class="mt-2 space-y-0.5">
                      {#each selectedEpisodeDetail.video_qc_issues as issue}
                        <li class="text-[11px] text-error">{issue}</li>
                      {/each}
                    </ul>
                  {/if}
                  {#if videoNeedsRetry(selectedEpisodeDetail)}
                    <div class="mt-3 rounded-lg border border-ember-500/30 bg-ember-500/10 p-3">
                      <p class="text-[12px] font-medium text-ink">El video no queda aprobado para publicar.</p>
                      <p class="mt-1 text-[11.5px] leading-relaxed text-ink-secondary">Puedes reintentarlo; Kronara volvera a pasar por agentes, validaciones y produccion para crear una version nueva en lugar de aprobar este fallo.</p>
                      <button
                        class="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-ember-500 px-3 py-2 text-[11.5px] font-semibold text-ink transition hover:bg-ember-400 disabled:cursor-not-allowed disabled:opacity-50"
                        onclick={retrySelectedProgram}
                        disabled={creating || connection !== 'connected'}
                      >
                        <Icon name="refresh" size={13} />
                        Reintentar produccion
                      </button>
                    </div>
                  {/if}
                {:else if episodeDetailTab === 'distribucion'}
                  <ul class="space-y-1.5">
                    {#each selected.platforms as platform}
                      <li class="flex items-center justify-between text-[11.5px]">
                        <span class="capitalize text-ink">{platform}</span>
                        <Badge tone="neutral">Sin publicar</Badge>
                      </li>
                    {/each}
                  </ul>
                  <p class="mt-2 text-[11px] text-ink-tertiary">La publicación real por plataforma llega con N1-N4 (Facebook/YouTube/Spotify/TikTok).</p>
                {:else if episodeDetailTab === 'analiticas'}
                  <p class="text-[12px] text-ink-tertiary">Vistas, retención y comentarios aparecerán aquí cuando Kronara Pulse pueda leer métricas reales de la plataforma donde se publique este episodio.</p>
                {/if}
              {/if}
            </div>
            <div class="mt-4 border-t border-line pt-3">
              <button
                class="inline-flex items-center gap-1.5 rounded-lg border border-error/25 px-3 py-2 text-[11.5px] font-medium text-error transition hover:bg-error/10 disabled:cursor-not-allowed disabled:opacity-50"
                onclick={deleteEpisode}
                disabled={deletingEpisodeId === selectedEpisode.story_id || connection !== 'connected'}
              >
                <Icon name="trash" size={14} />
                {deletingEpisodeId === selectedEpisode.story_id ? 'Eliminando…' : 'Eliminar episodio'}
              </button>
            </div>
          </Card>
        {:else}
          <Card title="Formatos y distribución">
            <ul class="space-y-2">
              {#each selected.platforms as platform}
                <li class="flex items-center justify-between text-[12.5px]">
                  <span class="capitalize text-ink">{platform}</span>
                  <Badge tone="success">Activo</Badge>
                </li>
              {/each}
            </ul>
          </Card>
          <Card title="Estilo visual">
            <p class="text-[12.5px] text-ink-secondary">Vinculado a <code class="text-purple-300">{selected.visual_style_id}</code> en config/programs/visual_style.v1.json.</p>
          </Card>
        {/if}
      </div>
    </div>
  </div>
{:else}
  {#if loading}
    <div class="grid min-h-[420px] place-items-center rounded-2xl border border-line bg-surface/70 p-6">
      {#if listGeneration}
        {@const stage = GENERATION_STAGES[listGeneration.stageIndex]}
        {@const percent = generationPercent(listGeneration)}
        <div class="w-full max-w-2xl rounded-2xl border border-ember-500/35 bg-ember-500/10 p-5 shadow-[0_18px_48px_rgba(0,0,0,0.18)]">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <span class="live-dot h-2 w-2 rounded-full" class:bg-ember-500={listGeneration.status === 'running'} class:bg-success={listGeneration.status === 'completed'} class:bg-error={listGeneration.status === 'failed'}></span>
                <p class="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-tertiary">{listGeneration.status === 'running' ? 'Generando episodio' : listGeneration.status === 'completed' ? 'Episodio generado' : 'Generación detenida'}</p>
              </div>
              <h2 class="mt-2 font-display text-xl font-semibold text-ink">{listGeneration.title}</h2>
              <p class="mt-1 text-[12.5px] text-ink-secondary">{listGeneration.programName ?? 'Programa local'}</p>
              <p class="mt-3 text-[13px] text-ink">{stage.label}</p>
              <p class="mt-1 text-[12px] text-ink-tertiary">{listGeneration.message || phaseDetail(listGeneration, stage)}</p>
            </div>
            <div class="text-right">
              <p class="font-mono text-xl font-semibold text-ink">{percent}%</p>
              <p class="text-[10.5px] text-ink-tertiary">{formatElapsed(listGeneration.elapsedSeconds)}</p>
              {#if listGeneration.status === 'failed' || listGeneration.status === 'running'}
                <button
                  class="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-[11.5px] font-medium text-ink-tertiary transition hover:border-ink-tertiary hover:text-ink"
                  onclick={clearEpisodeGeneration}
                >
                  Abandonar
                </button>
              {/if}
            </div>
          </div>
          <div class="mt-4 h-1.5 overflow-hidden rounded-full bg-line">
            <div class="h-full rounded-full bg-ember-500 transition-all duration-500" style={`width:${percent}%`}></div>
          </div>
          <div class="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {#each GENERATION_STAGES as pipelineStage, index}
              {@const status = phaseStatus(listGeneration, pipelineStage, index)}
              <div
                class={`rounded-lg border p-2.5 transition ${phaseCardClass(status)}`}
              >
                <div class="flex items-center justify-between gap-2">
                  <div class="flex min-w-0 items-center gap-2">
                    <Icon name={pipelineStage.icon} size={13} class="text-ink-tertiary" />
                    <p class="truncate text-[11.5px] font-medium text-ink">{pipelineStage.label}</p>
                  </div>
                  <span class={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10.5px] font-semibold ${phaseBadgeClass(status)}`}>{phaseStatusLabel(status)}</span>
                </div>
                <p class="mt-1 line-clamp-3 text-[10.5px] leading-relaxed text-ink-secondary">{phaseDetail(listGeneration, pipelineStage, index)}</p>
              </div>
            {/each}
          </div>
          {#if listGeneration.diagnostics?.quality_failure}
            {@const quality = listGeneration.diagnostics.quality_failure}
            <div class="mt-3 rounded-lg border border-error bg-error px-3 py-2">
              <p class="text-[11.5px] font-semibold text-ink">Crítica bloqueó el episodio</p>
              <p class="mt-1 text-[11px] leading-relaxed text-ink-secondary">Calidad {quality.quality_total}/110 tras {quality.revision_count} revisiones. Fallan {formatDimensions(quality.blocking_dimensions)}.</p>
            </div>
          {/if}
        </div>
      {:else}
        <div class="rounded-2xl border border-line bg-surface-inset px-5 py-4 text-center">
          <p class="text-[13px] font-medium text-ink">Cargando programas...</p>
          <p class="mt-1 text-[12px] text-ink-tertiary">Conectando con la web local.</p>
        </div>
      {/if}
    </div>
  {:else if programs.length === 0}
    <p class="rounded-lg border border-line bg-surface-inset px-3 py-2 text-[13px] text-ink-secondary">No hay programas cargados todavía.</p>
  {:else}
    <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {#each programs as program (program.program_id)}
        {@const cover = coverFor(program.program_id)}
        <button
          class="group overflow-hidden rounded-2xl border border-line bg-gradient-to-br from-surface to-surface-inset text-left shadow-[0_12px_32px_rgba(0,0,0,0.14)] transition duration-200 hover:-translate-y-0.5 hover:border-purple-500 hover:shadow-[0_18px_40px_rgba(123,92,255,0.14)]"
          onclick={() => openProgram(program)}
        >
          <div class="relative h-44 overflow-hidden" style={`background:${programGradient(program.program_id)}`}>
            {#if cover}
              <img src={cover} alt="" class="absolute inset-0 h-full w-full object-cover transition duration-500 group-hover:scale-105" loading="lazy" />
            {/if}
            <div class="absolute inset-0 bg-gradient-to-t from-black/80 via-black/15 to-black/10"></div>
            <div class="absolute inset-x-3 top-3 flex items-center justify-between">
              <Badge tone="purple">{program.weekday}</Badge>
              <span class="rounded-full border border-white/15 bg-black/35 px-2 py-1 text-[10px] font-medium text-ink backdrop-blur-sm">Activo</span>
            </div>
            <div class="absolute inset-x-4 bottom-3">
              <p class="font-display text-lg font-semibold leading-tight text-ink">{program.name}</p>
              <p class="mt-1 line-clamp-1 text-[11px] text-white/70">{program.genre}</p>
            </div>
          </div>
          <div class="p-4">
            <p class="text-[12px] leading-relaxed text-ink-secondary">{program.description}</p>
            <div class="mt-4 grid grid-cols-2 gap-2 border-t border-line-subtle pt-3">
              <div>
                <p class="text-[10px] uppercase tracking-wide text-ink-tertiary">Episodios</p>
                <p class="mt-1 text-[12px] font-semibold text-ink">{episodeCountFor(program.program_id)}</p>
              </div>
              <div class="text-right">
                <p class="text-[10px] uppercase tracking-wide text-ink-tertiary">Objetivo</p>
                <p class="mt-1 text-[12px] font-semibold text-ink">{program.target_duration_seconds}s</p>
              </div>
            </div>
          </div>
        </button>
      {/each}
    </div>
  {/if}
{/if}
