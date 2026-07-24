<script>
  import { onDestroy, onMount } from 'svelte';
  import Card from '../components/Card.svelte';
  import Badge from '../components/Badge.svelte';
  import Icon from '../components/Icon.svelte';
  import { applyProgressEvent } from '../operations-state.js';
  import { episodeGeneration } from '../generation-state.js';
  import { assetSrc, callOperations } from '../local-operations.js';

  let { operations = $bindable({}), connection = 'disconnected' } = $props();

  let subreddit = $state('Historias');
  let contentRunning = $state(false);
  let contentResult = $state(null);
  let notice = $state('');
  let activeTab = $state('en_vivo');

  // Fase 1e: pick a visual style for this episode. Empty = automatic (the
  // program's configured style). The list comes from styles.list (base 10 +
  // any custom styles the user added in Configuración → Estilos).
  let styles = $state([]);
  let selectedStyleId = $state('');

  // Fase 5: tipo de contenido. "narrative_story" investiga Reddit; los demás son
  // de forma corta (30-60s) desde un tema, sin Reddit. Cambiar el modo cambia el
  // formulario ("cambiar a la otra vista") y lo que se envía a content.run.
  const CONTENT_KINDS = [
    { id: 'narrative_story', label: 'Historia', hint: 'Reconstruye un caso real de Reddit.' },
    { id: 'reflection', label: 'Reflexión', hint: 'Idea breve que reencuadra una preocupación.' },
    { id: 'scripture', label: 'Bíblico', hint: 'Lectura devocional (dominio público).' },
    { id: 'quote', label: 'Frase', hint: 'Aforismo original memorable.' },
  ];
  let contentKind = $state('narrative_story');
  let theme = $state('');
  const isStoryMode = $derived(contentKind === 'narrative_story');

  onMount(async () => {
    try {
      const result = await callOperations('styles.list', {});
      styles = result.styles ?? [];
    } catch (error) {
      styles = [];
    }
  });

  // Live view state (FASE B): polls run.diagnostics every 2s while a
  // generation is active so the user watches the research, script and
  // shots build up in real time instead of waiting blind for the run
  // to complete. Uses episodeGeneration (from Programas.svelte or the
  // chat approve path) as the source-of-truth for which run to poll.
  let liveDiagnostics = $state(null);
  let livePollInterval = null;

  const terminalStates = ['completed', 'blocked', 'failed', 'cancelled'];
  const TABS = ['en_vivo', 'resumen', 'guion', 'voces', 'storyboard', 'recursos', 'musica', 'produccion', 'exportaciones'];
  const TAB_LABELS = {
    en_vivo: 'En vivo', resumen: 'Resumen', guion: 'Guion', voces: 'Voces', storyboard: 'Storyboard',
    recursos: 'Recursos', musica: 'Música y SFX', produccion: 'Producción', exportaciones: 'Exportaciones',
  };

  $effect(() => {
    // Track the active generation from generation-state.js. When it goes
    // from null -> running, start polling; when it goes to terminal,
    // stop but keep the last diagnostics visible so the user can review
    // what actually happened.
    const run = $episodeGeneration;
    if (run?.status === 'running' && run.storyId) {
      startLivePoll(`content:${run.storyId}`);
    } else {
      stopLivePoll();
    }
  });

  onDestroy(stopLivePoll);

  async function pollLiveDiagnostics(runId) {
    try {
      const diagnostics = await callOperations('run.diagnostics', { run_id: runId });
      liveDiagnostics = diagnostics;
    } catch (error) {
      // Transient failures don't tear down the poll -- next tick will retry.
    }
  }

  function startLivePoll(runId) {
    stopLivePoll();
    pollLiveDiagnostics(runId);
    livePollInterval = setInterval(() => pollLiveDiagnostics(runId), 2000);
  }

  function stopLivePoll() {
    if (livePollInterval) {
      clearInterval(livePollInterval);
      livePollInterval = null;
    }
  }

  function phaseIcon(status) {
    if (status === 'completed') return 'check';
    if (status === 'running') return 'clock';
    if (status === 'failed') return 'plus';
    return 'clock';
  }

  function phaseTone(status) {
    if (status === 'completed') return 'success';
    if (status === 'running') return 'purple';
    if (status === 'failed') return 'error';
    return 'neutral';
  }

  async function runProductionContent() {
    if (contentRunning || connection !== 'connected') return;
    const community = subreddit.trim().replace(/^r\//, '');
    if (isStoryMode && !community) {
      notice = 'Escribe una comunidad de Reddit para investigar.';
      return;
    }
    if (!isStoryMode && !theme.trim()) {
      notice = 'Escribe un tema para este contenido.';
      return;
    }
    contentRunning = true;
    contentResult = null;
    notice = '';
    try {
      const result = await callOperations('content.run', {
        story_id: `owned_${contentKind}_${Date.now()}`,
        content_kind: contentKind,
        // Historia = investiga Reddit (90s); modos cortos = tema, sin Reddit (45s).
        ...(isStoryMode
          ? { subreddits: [community], sort: 'hot', limit: 25, target_duration_seconds: 90 }
          : { theme: theme.trim(), target_duration_seconds: 45 }),
        // Only send style_id when the user picked one; empty means "let the
        // program's configured style decide" (the resolver falls back to it).
        ...(selectedStyleId ? { style_id: selectedStyleId } : {}),
      });
      contentResult = result;
      await refreshTimeline(result.run_id);
    } catch (error) {
      notice = 'La generación se detuvo de forma segura: nada se publica si fallan los modelos, los derechos o la calidad.';
    } finally {
      contentRunning = false;
    }
  }

  async function runStoryTest() {
    if (operations.activeRun && !terminalStates.includes(operations.activeRun.status)) return;
    notice = '';
    try {
      const run = await callOperations('story.test', { story_id: `owned_ui_${Date.now()}`, wait: false });
      operations = { ...operations, activeRun: run };
      await pollRun(run.run_id);
    } catch (error) {
      notice = 'La prueba narrativa no pudo iniciarse.';
    }
  }

  async function pollRun(runId) {
    const progress = await callOperations('run.progress', { run_id: runId });
    operations = { ...operations, activeRun: progress };
    await refreshTimeline(runId);
    if (!terminalStates.includes(progress.status)) {
      setTimeout(() => pollRun(runId).catch(() => (notice = 'Se perdió la actualización de progreso.')), 700);
    }
  }

  async function cancelRun() {
    if (!operations.activeRun) return;
    const progress = await callOperations('run.cancel', { run_id: operations.activeRun.run_id });
    operations = { ...operations, activeRun: progress };
  }

  async function refreshTimeline(runId) {
    const timeline = await callOperations('tools.timeline', { run_id: runId });
    for (const event of timeline.events) operations = applyProgressEvent(operations, event);
  }

  // --- Cabina de edición: derivados sobre el episodio producido -------------
  // Los tabs Voces/Storyboard/Recursos/Música leen el mismo `video.scene_manifest`
  // (una fila por escena, con su asset real, corte, tier y duración medida) más
  // el conteo de fuentes, la música y los SFX que el pipeline visual reporta.
  const SOURCE_KIND_LABELS = { ai_image: 'Imagen IA', video_loop: 'Video loop', graphic_overlay: 'Tarjeta gráfica', placeholder: 'Placeholder' };
  const SOURCE_KIND_TONE = { ai_image: 'purple', video_loop: 'success', graphic_overlay: 'neutral', placeholder: 'neutral' };
  const SOURCE_KIND_HEX = { ai_image: '#a855f7', video_loop: '#34d399', graphic_overlay: '#64748b', placeholder: '#3f3f46' };
  const TIER_LABELS = { premium: 'Premium', fast: 'Rápida' };

  const secs = (ms) => `${(Math.max(0, ms ?? 0) / 1000).toFixed(1)}s`;

  const video = $derived(contentResult?.video ?? null);
  const sceneManifest = $derived(video?.scene_manifest ?? []);
  const hasEpisode = $derived(sceneManifest.length > 0);
  const maxSceneMs = $derived(sceneManifest.reduce((m, s) => Math.max(m, s.duration_ms ?? 0), 0) || 1);
  const totalNarrationMs = $derived(sceneManifest.reduce((sum, s) => sum + (s.duration_ms ?? 0), 0));

  // Composición de fuentes visuales como segmentos proporcionales (Recursos).
  const sourceBreakdown = $derived.by(() => {
    const counts = video?.source_kind_counts ?? {};
    const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
    return Object.entries(counts)
      .filter(([, n]) => n > 0)
      .map(([kind, n]) => ({ kind, count: n, pct: (n / total) * 100 }));
  });

  // Medidor de loudness: dónde cae el LUFS integrado dentro de la ventana
  // objetivo de plataforma (-19…-13 LUFS). Dominio visible -30…-6.
  const lufsPct = (lufs) => Math.min(100, Math.max(0, ((lufs - -30) / (-6 - -30)) * 100));
  const lufsInRange = $derived(video?.integrated_lufs != null && video.integrated_lufs >= -19 && video.integrated_lufs <= -13);
  const sfxTags = $derived(video?.sfx_cue_tags ?? []);
  const sfxResolved = $derived(video?.sfx_resolved_paths ?? {});
  const sfxMissing = $derived(video?.sfx_missing_tags ?? []);
</script>

<div class="space-y-4">
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

  {#if notice}<p class="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-[12.5px] text-warning">{notice}</p>{/if}

  {#if activeTab === 'en_vivo'}
    {@const run = $episodeGeneration}
    <div class="grid grid-cols-1 gap-3 lg:grid-cols-[1.1fr_0.9fr]">
      <Card title={run?.status === 'running' ? 'Generación activa' : 'Última corrida'} subtitle={run?.programName ?? 'Sin generación activa'}>
        {#if !run}
          <p class="text-[13px] text-ink-secondary">Aún no has iniciado un episodio en esta sesión. Ve a <strong>Programas → Crear episodio</strong> y esta vista mostrará el guion, señales investigadas y tomas mientras se generan (auto-refresh cada 2s).</p>
        {:else}
          <div class="flex flex-wrap items-center gap-2">
            <span class="live-dot h-2 w-2 rounded-full" class:bg-ember-500={run.status === 'running'} class:bg-success={run.status === 'completed'} class:bg-error={run.status === 'failed'}></span>
            <p class="font-display text-[13px] font-semibold text-ink">{run.title ?? 'Generando episodio'}</p>
            <Badge tone={run.status === 'completed' ? 'success' : run.status === 'failed' ? 'error' : 'purple'}>{run.status}</Badge>
          </div>
          <p class="mt-1 text-[12px] text-ink-secondary">{run.message}</p>

          {#if liveDiagnostics?.phases}
            <div class="mt-4 space-y-1.5">
              {#each liveDiagnostics.phases as phase}
                <div class="flex items-start gap-2 rounded-lg border border-line bg-surface-inset px-3 py-2">
                  <Badge tone={phaseTone(phase.status)}>{phase.label}</Badge>
                  <div class="min-w-0 flex-1">
                    <p class="text-[12px] text-ink">{phase.status}</p>
                    {#if phase.detail}
                      <p class="mt-0.5 text-[11px] text-ink-tertiary">{phase.detail}</p>
                    {/if}
                  </div>
                </div>
              {/each}
            </div>
          {/if}
        {/if}
      </Card>

      <div class="space-y-3">
        <Card title="Agentes en acción" subtitle="Últimas decisiones agente por agente">
          {#if liveDiagnostics?.agent_logs?.length}
            <div class="max-h-96 space-y-2 overflow-y-auto pr-1">
              {#each [...liveDiagnostics.agent_logs].reverse().slice(0, 20) as entry}
                <div class="rounded-lg border border-line bg-surface-inset px-3 py-2">
                  <div class="flex items-center justify-between gap-2">
                    <p class="font-mono text-[10.5px] text-purple-300">{entry.agent_id}</p>
                    <p class="text-[10.5px] text-ink-tertiary">{entry.action}</p>
                  </div>
                  {#if entry.detail}
                    <p class="mt-1 text-[11.5px] leading-relaxed text-ink">{entry.detail}</p>
                  {/if}
                </div>
              {/each}
            </div>
          {:else}
            <p class="text-[12px] text-ink-tertiary">Sin logs de agentes todavía. Aparecen conforme cada nodo del pipeline reporta.</p>
          {/if}
        </Card>

        <Card title="Herramientas invocadas" subtitle="tool_events crudos (backend)">
          {#if liveDiagnostics?.tool_events?.length}
            <div class="max-h-64 space-y-1 overflow-y-auto pr-1 font-mono text-[10.5px]">
              {#each [...liveDiagnostics.tool_events].reverse().slice(0, 15) as event}
                <div class="flex items-center gap-2 rounded border border-line bg-surface-inset px-2 py-1">
                  <Badge tone={event.status === 'completed' ? 'success' : event.status === 'failed' ? 'error' : 'neutral'}>{event.status}</Badge>
                  <span class="text-purple-300">{event.tool_id}</span>
                  <span class="truncate text-ink-tertiary">{event.summary ?? ''}</span>
                </div>
              {/each}
            </div>
          {:else}
            <p class="text-[12px] text-ink-tertiary">Sin herramientas registradas todavía.</p>
          {/if}
        </Card>
      </div>
    </div>

    {#if liveDiagnostics?.script}
      {@const s = liveDiagnostics.script}
      <Card title="Guion en vivo" subtitle={`${s.word_count ?? 0} palabras · ~${Math.round(s.estimated_seconds ?? 0)}s${s.revision_count ? ` · ${s.revision_count} revisión(es)` : ''}`}>
        <div class="flex items-center gap-2">
          <span class="live-dot h-2 w-2 rounded-full bg-success"></span>
          <p class="text-[11.5px] text-ink-tertiary">Guion aprobado por el crítico. Se muestra mientras la producción de video (lo lento) sigue corriendo.</p>
        </div>
        {#if s.hook}
          <p class="mt-3 rounded-lg border border-purple-500/30 bg-purple-500/10 px-3 py-2 text-[12.5px] font-medium leading-relaxed text-ink">{s.hook}</p>
        {/if}
        <p class="mt-3 max-h-96 overflow-y-auto whitespace-pre-wrap pr-1 text-[12.5px] leading-relaxed text-ink-secondary">{s.script}</p>
      </Card>
    {/if}

    {#if liveDiagnostics?.program_quality_failure}
      <Card title="Falla en la plantilla del programa">
        <p class="text-[12px] text-ink">Programa: <code class="text-purple-300">{liveDiagnostics.program_quality_failure.program_id}</code></p>
        <p class="mt-1 text-[11.5px] text-ink-tertiary">Hallazgos: {liveDiagnostics.program_quality_failure.findings?.join(', ') ?? 'sin detalle'}</p>
        <p class="mt-2 text-[11px] text-ink-secondary">Este bloqueo ocurre en Crítica. El guion puede tener voz medida pero no respeta la plantilla narrativa del programa.</p>
      </Card>
    {:else if liveDiagnostics?.quality_failure}
      <Card title="Falla en Crítica de calidad">
        <p class="text-[12px] text-ink">Calidad total: {liveDiagnostics.quality_failure.quality_total}/110 tras {liveDiagnostics.quality_failure.revision_count} revisiones.</p>
        <p class="mt-1 text-[11.5px] text-ink-tertiary">Dimensiones bloqueantes: {liveDiagnostics.quality_failure.blocking_dimensions?.join(', ') ?? 'ninguna'}</p>
      </Card>
    {/if}
  {:else if activeTab === 'resumen'}
    <Card title="Crear contenido" subtitle="Elige el tipo: historia real de Reddit, o forma corta (reflexión / bíblico / frase)">
      <div class="mb-4 flex flex-wrap gap-1.5">
        {#each CONTENT_KINDS as kind (kind.id)}
          <button
            class="rounded-full border px-3.5 py-1.5 text-[12px] font-medium transition-colors"
            class:border-purple-500={contentKind === kind.id}
            class:bg-purple-500={contentKind === kind.id}
            class:text-ink={contentKind === kind.id}
            class:border-line={contentKind !== kind.id}
            class:text-ink-secondary={contentKind !== kind.id}
            onclick={() => (contentKind = kind.id)}
          >
            {kind.label}
          </button>
        {/each}
      </div>
      <div class="flex flex-wrap items-center gap-3">
        {#if isStoryMode}
          <label class="flex-1 min-w-[220px]">
            <span class="mb-1 block text-[11px] text-ink-tertiary">Comunidad para observar</span>
            <input
              class="w-full rounded-full border border-line bg-surface-inset px-4 py-2 text-[13px] text-ink placeholder:text-ink-tertiary focus:border-purple-500 focus:outline-none"
              bind:value={subreddit}
              placeholder="Historias"
              autocomplete="off"
            />
          </label>
        {:else}
          <label class="flex-1 min-w-[220px]">
            <span class="mb-1 block text-[11px] text-ink-tertiary">Tema</span>
            <input
              class="w-full rounded-full border border-line bg-surface-inset px-4 py-2 text-[13px] text-ink placeholder:text-ink-tertiary focus:border-purple-500 focus:outline-none"
              bind:value={theme}
              placeholder={contentKind === 'scripture' ? 'Salmo 23, el buen pastor' : contentKind === 'quote' ? 'la constancia' : 'la calma en la incertidumbre'}
              autocomplete="off"
            />
          </label>
        {/if}
        <label class="min-w-[200px]">
          <span class="mb-1 block text-[11px] text-ink-tertiary">Estilo visual</span>
          <select
            class="w-full rounded-full border border-line bg-surface-inset px-4 py-2 text-[13px] text-ink focus:border-purple-500 focus:outline-none"
            bind:value={selectedStyleId}
          >
            <option value="">Automático (según programa)</option>
            {#each styles as style (style.style_id)}
              <option value={style.style_id}>{style.name}</option>
            {/each}
          </select>
        </label>
        <button
          class="rounded-full bg-purple-500 px-5 py-2.5 text-[13px] font-medium text-ink hover:bg-purple-600 disabled:cursor-not-allowed disabled:opacity-40"
          onclick={runProductionContent}
          disabled={contentRunning || connection !== 'connected'}
        >
          {contentRunning ? 'Creando…' : isStoryMode ? 'Crear historia gobernada' : 'Crear pieza'}
        </button>
      </div>
      <p class="mt-3 text-[11.5px] text-ink-tertiary">
        {#if isStoryMode}
          <code class="text-purple-300">reddit.list_signals</code> usa solo señales abstractas; el investigador reconstruye el caso real anonimizado.
        {:else}
          {CONTENT_KINDS.find((k) => k.id === contentKind)?.hint} Forma corta (~45s), sin Reddit; reusa voz, estilo y música.
        {/if}
      </p>

      {#if contentResult}
        <div class="mt-4 border-t border-line pt-4">
          <div class="flex items-center gap-2">
            <Badge tone={contentResult.status === 'completed' ? 'success' : 'error'}>{contentResult.status}</Badge>
            <h3 class="font-display text-sm font-semibold text-ink">{contentResult.story?.title ?? contentResult.error_code ?? 'Ejecución bloqueada de forma segura'}</h3>
          </div>
          {#if contentResult.story}
            <p class="mt-1.5 text-[13px] text-ink-secondary">{contentResult.story.hook}</p>
            <dl class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
              <div class="rounded-lg border border-line bg-surface-inset p-2.5"><dt class="text-[10.5px] text-ink-tertiary">Generador</dt><dd class="mt-0.5 text-[12px] text-ink">{contentResult.story.generator_family}</dd></div>
              <div class="rounded-lg border border-line bg-surface-inset p-2.5"><dt class="text-[10.5px] text-ink-tertiary">Crítico</dt><dd class="mt-0.5 text-[12px] text-ink">{contentResult.story.critic_family}</dd></div>
              <div class="rounded-lg border border-line bg-surface-inset p-2.5"><dt class="text-[10.5px] text-ink-tertiary">Duración</dt><dd class="mt-0.5 text-[12px] text-ink">{Math.round(contentResult.story.estimated_seconds)}s</dd></div>
              <div class="rounded-lg border border-line bg-surface-inset p-2.5"><dt class="text-[10.5px] text-ink-tertiary">RAG citado</dt><dd class="mt-0.5 text-[12px] text-ink">{contentResult.rag_citations?.length ?? 0}</dd></div>
              <div class="rounded-lg border border-line bg-surface-inset p-2.5"><dt class="text-[10.5px] text-ink-tertiary">Video</dt><dd class="mt-0.5 text-[12px] text-ink">{contentResult.video?.status ?? 'no_configured'}</dd></div>
            </dl>
          {/if}
        </div>

        {#if contentResult.selected_signal}
          <div class="mt-4 border-t border-line pt-4">
            <p class="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-tertiary">Investigación · señal elegida</p>
            <p class="mt-2 text-[13px] text-ink-secondary">{contentResult.selected_signal.theme_hint}</p>
            <dl class="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
              <div class="rounded-lg border border-line bg-surface-inset p-2.5"><dt class="text-[10.5px] text-ink-tertiary">Velocidad</dt><dd class="mt-0.5 text-[12px] text-ink">{contentResult.selected_signal.velocity.toFixed(2)}</dd></div>
              <div class="rounded-lg border border-line bg-surface-inset p-2.5"><dt class="text-[10.5px] text-ink-tertiary">Saturación</dt><dd class="mt-0.5 text-[12px] text-ink">{Math.round(contentResult.selected_signal.saturation * 100)}%</dd></div>
              <div class="rounded-lg border border-line bg-surface-inset p-2.5"><dt class="text-[10.5px] text-ink-tertiary">Aceleración</dt><dd class="mt-0.5 text-[12px] text-ink">{contentResult.selected_signal.acceleration.toFixed(2)}</dd></div>
              <div class="rounded-lg border border-line bg-surface-inset p-2.5"><dt class="text-[10.5px] text-ink-tertiary">Derechos</dt><dd class="mt-0.5 text-[12px] text-ink">{contentResult.selected_signal.rights_mode}</dd></div>
            </dl>
            <small class="mt-2 block break-all text-[11px] text-ink-tertiary">{contentResult.selected_signal.source_uri}</small>
          </div>
        {/if}

        {#if contentResult.rejected_signals && Object.keys(contentResult.rejected_signals).length > 0}
          <div class="mt-4 border-t border-line pt-4">
            <p class="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-tertiary">Señales descartadas por los filtros</p>
            <div class="mt-2 flex flex-wrap gap-1.5">
              {#each Object.entries(contentResult.rejected_signals) as [reason, count]}
                <span class="rounded-full border border-line bg-surface-inset px-2.5 py-1 text-[11px] text-ink-tertiary">{reason}: {count}</span>
              {/each}
            </div>
          </div>
        {/if}
      {/if}
    </Card>
  {:else if activeTab === 'guion'}
    <Card title="Guion" subtitle={contentResult?.story ? `${contentResult.story.word_count} palabras` : undefined}>
      {#if contentResult?.story}
        <dl class="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div class="rounded-lg border border-line bg-surface-inset p-2.5">
            <dt class="text-[10.5px] text-ink-tertiary">Duración real / objetivo</dt>
            <dd class="mt-0.5 text-[12px] text-ink">{Math.round(contentResult.story.duration_qc.estimated_seconds)}s / {contentResult.story.duration_qc.target_seconds}s</dd>
          </div>
          <div class="rounded-lg border border-line bg-surface-inset p-2.5">
            <dt class="text-[10.5px] text-ink-tertiary">Palabras reales / objetivo</dt>
            <dd class="mt-0.5 text-[12px] text-ink">{contentResult.story.duration_qc.actual_word_count} / {contentResult.story.duration_qc.target_word_count}</dd>
          </div>
          <div class="rounded-lg border border-line bg-surface-inset p-2.5">
            <dt class="text-[10.5px] text-ink-tertiary">Calidad narrativa</dt>
            <dd class="mt-0.5 text-[12px] text-ink">{contentResult.story.quality.total.toFixed(1)}/10</dd>
          </div>
          <div class="rounded-lg border border-line bg-surface-inset p-2.5">
            <dt class="text-[10.5px] text-ink-tertiary">Originalidad</dt>
            <dd class="mt-0.5"><Badge tone={contentResult.story.originality.passed ? 'success' : 'error'}>{contentResult.story.originality.passed ? 'Aprobada' : 'Revisar'}</Badge></dd>
          </div>
        </dl>
        <div class="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div class="rounded-lg border border-line bg-surface-inset p-2"><p class="text-[10px] text-ink-tertiary">Similitud léxica</p><p class="mt-0.5 text-[11.5px] text-ink">{Math.round(contentResult.story.originality.lexical_similarity * 100)}%</p></div>
          <div class="rounded-lg border border-line bg-surface-inset p-2"><p class="text-[10px] text-ink-tertiary">Similitud semántica</p><p class="mt-0.5 text-[11.5px] text-ink">{Math.round(contentResult.story.originality.semantic_similarity * 100)}%</p></div>
          <div class="rounded-lg border border-line bg-surface-inset p-2"><p class="text-[10px] text-ink-tertiary">Similitud estructural</p><p class="mt-0.5 text-[11.5px] text-ink">{Math.round(contentResult.story.originality.structural_similarity * 100)}%</p></div>
          <div class="rounded-lg border border-line bg-surface-inset p-2"><p class="text-[10px] text-ink-tertiary">Secuencia de eventos</p><p class="mt-0.5 text-[11.5px] text-ink">{Math.round(contentResult.story.originality.event_sequence_similarity * 100)}%</p></div>
        </div>
        {#if contentResult.story.revision_count > 0}
          <p class="mt-2 text-[11px] text-ink-tertiary">{contentResult.story.revision_count} revisión(es) aplicadas por el crítico independiente antes de aprobar.</p>
        {/if}
        {#if (contentResult.story.quality.blocking_dimensions ?? []).length > 0}
          <p class="mt-2 text-[11px] text-error">Dimensiones bloqueantes: {contentResult.story.quality.blocking_dimensions.join(', ')}</p>
        {/if}
        <p class="mt-4 whitespace-pre-wrap text-[12.5px] leading-relaxed text-ink-secondary">{contentResult.story.script}</p>
        {#if (contentResult.rag_citations ?? []).length > 0}
          <div class="mt-3 border-t border-line pt-3">
            <p class="text-[10.5px] text-ink-tertiary">Fragmentos propios citados (RAG)</p>
            {#each contentResult.rag_citations as citation}
              <small class="mt-1 block break-all text-[11px] text-ink-tertiary">{citation}</small>
            {/each}
          </div>
        {/if}
      {:else}
        <p class="text-[13px] text-ink-secondary">Crea una historia desde la pestaña Resumen para ver el guion aquí.</p>
      {/if}
    </Card>
  {:else if activeTab === 'voces'}
    {#if hasEpisode}
      <Card title="Voz en off, escena por escena" subtitle={`${sceneManifest.length} escenas · ${secs(totalNarrationMs)} narrados`}>
        <p class="text-[11.5px] text-ink-tertiary">Duración medida sobre el audio real. La voz y la clonación por programa se configuran en <strong class="text-ink-secondary">Configuración → Voces</strong>.</p>
        <div class="mt-4 space-y-2.5">
          {#each sceneManifest as scene (scene.scene_id)}
            <div class="rounded-lg border border-line bg-surface-inset p-3">
              <div class="flex items-baseline justify-between gap-3">
                <span class="font-mono text-[10.5px] text-purple-300">E{String(scene.scene_index).padStart(2, '0')}</span>
                <span class="shrink-0 font-mono text-[11px] tabular-nums text-ink-secondary">{secs(scene.duration_ms)}</span>
              </div>
              <p class="mt-1.5 text-[12.5px] leading-relaxed text-ink">{scene.narration}</p>
              <div class="mt-2 h-1 overflow-hidden rounded-full bg-line">
                <div class="h-full rounded-full bg-purple-500/70" style={`width:${(scene.duration_ms / maxSceneMs) * 100}%`}></div>
              </div>
            </div>
          {/each}
        </div>
      </Card>
    {:else}
      <Card title="Voces">
        <p class="text-[13px] text-ink-secondary">Aún no hay narración. Crea una historia en <strong>Resumen</strong> y aquí verás la voz en off segmentada por escena, con la duración hablada real de cada una.</p>
      </Card>
    {/if}
  {:else if activeTab === 'storyboard'}
    {#if hasEpisode}
      <Card title="Storyboard" subtitle={`${video.scene_count} escenas · ${video.shot_count} tomas`}>
        <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {#each sceneManifest as scene (scene.scene_id)}
            <figure class="overflow-hidden rounded-xl border border-line bg-surface-inset">
              <div class="relative aspect-[9/16] bg-black">
                {#if assetSrc(scene.asset_path)}
                  <img src={assetSrc(scene.asset_path)} alt={`Escena ${scene.scene_index}`} class="h-full w-full object-cover" loading="lazy" />
                {:else}
                  <div class="flex h-full items-center justify-center text-ink-tertiary"><Icon name="film" /></div>
                {/if}
                <span class="absolute left-1.5 top-1.5 rounded-md bg-black/70 px-1.5 py-0.5 font-mono text-[10px] text-white">E{String(scene.scene_index).padStart(2, '0')}</span>
                <span class="absolute bottom-1.5 right-1.5 rounded-md bg-black/70 px-1.5 py-0.5 font-mono text-[10px] tabular-nums text-white">{secs(scene.duration_ms)}</span>
              </div>
              <figcaption class="flex items-center justify-between gap-2 px-2.5 py-2">
                <Badge tone={SOURCE_KIND_TONE[scene.source_kind] ?? 'neutral'}>{SOURCE_KIND_LABELS[scene.source_kind] ?? scene.source_kind}</Badge>
                <span class="text-[10.5px] text-ink-tertiary">{scene.shot_count} tomas · {TIER_LABELS[scene.tier] ?? scene.tier}</span>
              </figcaption>
            </figure>
          {/each}
        </div>
      </Card>
    {:else}
      <Card title="Storyboard">
        <p class="text-[13px] text-ink-secondary">Sin escenas todavía. Cuando el pipeline visual produzca un episodio, cada escena aparecerá aquí con su imagen real, tipo de fuente, número de tomas y duración.</p>
      </Card>
    {/if}
  {:else if activeTab === 'recursos'}
    {#if hasEpisode}
      <div class="space-y-3">
        <Card title="Composición de fuentes visuales" subtitle="De dónde sale cada escena del episodio">
          <div class="flex h-3 overflow-hidden rounded-full border border-line">
            {#each sourceBreakdown as seg (seg.kind)}
              <div class="h-full" style={`width:${seg.pct}%;background:${SOURCE_KIND_HEX[seg.kind] ?? '#3f3f46'}`} title={SOURCE_KIND_LABELS[seg.kind] ?? seg.kind}></div>
            {/each}
          </div>
          <div class="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
            {#each sourceBreakdown as seg (seg.kind)}
              <div class="flex items-center gap-1.5 text-[11.5px] text-ink-secondary">
                <span class="h-2.5 w-2.5 rounded-sm" style={`background:${SOURCE_KIND_HEX[seg.kind] ?? '#3f3f46'}`}></span>
                {SOURCE_KIND_LABELS[seg.kind] ?? seg.kind}<span class="text-ink-tertiary">· {seg.count}</span>
              </div>
            {/each}
          </div>
        </Card>
        <div class="grid grid-cols-1 gap-3 lg:grid-cols-[0.8fr_1.2fr]">
          <Card title="Portada">
            {#if assetSrc(video.cover_image_path)}
              <img src={assetSrc(video.cover_image_path)} alt="Portada del episodio" class="w-full rounded-lg border border-line object-cover" />
            {:else}
              <p class="text-[12px] text-ink-tertiary">Sin portada generada.</p>
            {/if}
          </Card>
          <Card title="Efectos de sonido" subtitle={`${sfxTags.length} señales detectadas`}>
            {#if sfxTags.length}
              <div class="flex flex-wrap gap-1.5">
                {#each sfxTags as tag}
                  <span class={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] ${sfxResolved[tag] ? 'border-success text-success' : 'border-line text-ink-tertiary'}`}>
                    <span class={`h-1.5 w-1.5 rounded-full ${sfxResolved[tag] ? 'bg-success' : 'bg-line'}`}></span>
                    {tag}
                  </span>
                {/each}
              </div>
              {#if sfxMissing.length}
                <p class="mt-3 text-[11px] text-ink-tertiary">{sfxMissing.length} señal(es) sin archivo en la biblioteca: se omiten sin romper la mezcla.</p>
              {/if}
            {:else}
              <p class="text-[12px] text-ink-tertiary">Este episodio no disparó SFX; el guion no contenía palabras clave mapeadas.</p>
            {/if}
          </Card>
        </div>
      </div>
    {:else}
      <Card title="Recursos">
        <p class="text-[13px] text-ink-secondary">Sin recursos todavía. Aquí verás el desglose de fuentes visuales (imagen IA, video loop, tarjeta gráfica), la portada y los efectos de sonido usados cuando se produzca un episodio.</p>
      </Card>
    {/if}
  {:else if activeTab === 'musica'}
    {#if hasEpisode}
      <div class="space-y-3">
        <Card title="Loudness del episodio" subtitle="Nivel integrado contra la ventana objetivo de plataforma">
          {#if video.integrated_lufs != null}
            <div class="flex items-baseline justify-between">
              <span class="font-display text-2xl font-semibold tabular-nums text-ink">{video.integrated_lufs.toFixed(1)} <span class="text-[12px] font-normal text-ink-tertiary">LUFS</span></span>
              <Badge tone={lufsInRange ? 'success' : 'error'}>{lufsInRange ? 'En rango' : 'Fuera de rango'}</Badge>
            </div>
            <div class="relative mt-3 h-2.5 rounded-full bg-line">
              <div class="absolute inset-y-0 rounded-full bg-success/25" style="left:45.8%;width:25%"></div>
              <div class="absolute top-1/2 h-4 w-1 -translate-y-1/2 rounded-full bg-ink" style={`left:${lufsPct(video.integrated_lufs)}%`}></div>
            </div>
            <div class="mt-1 flex justify-between text-[10px] text-ink-tertiary"><span>-30</span><span>ventana -19…-13</span><span>-6</span></div>
          {:else}
            <p class="text-[12px] text-ink-tertiary">Sin medición de loudness para este episodio.</p>
          {/if}
        </Card>
        <Card title="Música" subtitle="Pista de fondo con ducking bajo la narración">
          {#if video.music_path}
            <div class="flex items-center gap-3 rounded-lg border border-line bg-surface-inset p-3">
              <span class="flex h-9 w-9 items-center justify-center rounded-lg bg-purple-500/15 text-purple-300"><Icon name="play" /></span>
              <p class="min-w-0 flex-1 truncate font-mono text-[11.5px] text-ink-secondary">{video.music_path.split(/[\\/]/).pop()}</p>
            </div>
          {:else}
            <p class="text-[12px] text-ink-tertiary">Este episodio se renderizó sin música (el estilo visual no define moods musicales o la biblioteca no tenía una pista compatible).</p>
          {/if}
        </Card>
      </div>
    {:else}
      <Card title="Música y SFX">
        <p class="text-[13px] text-ink-secondary">Sin mezcla todavía. Aquí verás el loudness integrado del episodio, la pista musical con ducking y los efectos de sonido una vez producido.</p>
      </Card>
    {/if}
  {:else if activeTab === 'produccion'}
    <Card title="Producción">
      <button
        class="rounded-full border border-line px-4 py-2 text-[13px] text-ink-secondary hover:border-purple-500 hover:text-ink"
        onclick={runStoryTest}
      >
        Probar historia propia
      </button>
      {#if operations.activeRun}
        <div class="mt-3 rounded-lg border border-line bg-surface-inset p-3">
          <div class="flex items-center justify-between text-[12px] text-ink-secondary">
            <span>{operations.activeRun.status}</span>
            <span>{operations.activeRun.progress_percent}%</span>
          </div>
          <div class="mt-2 h-1.5 rounded-full bg-line">
            <div class="h-full rounded-full bg-purple-500" style={`width:${operations.activeRun.progress_percent}%`}></div>
          </div>
          {#if !terminalStates.includes(operations.activeRun.status)}
            <button class="mt-2 rounded-full border border-line px-3 py-1 text-[12px] text-ink-secondary hover:text-ink" onclick={cancelRun}>Cancelar</button>
          {/if}
        </div>
      {/if}
    </Card>

    <Card title="Herramientas utilizadas" subtitle="Trazas resumidas, sin secretos">
      {#if (operations.toolEvents ?? []).length === 0}
        <p class="text-[13px] text-ink-secondary">Las llamadas aparecerán aquí con su agente, resultado, tiempo y evidencia.</p>
      {:else}
        <div class="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
          {#each operations.toolEvents.slice(-9).reverse() as event}
            <article class="rounded-lg border border-line bg-surface-inset p-3" class:border-l-2={true} class:border-l-success={event.status === 'completed'} class:border-l-error={event.status === 'failed' || event.status === 'blocked'}>
              <div class="flex items-center justify-between">
                <strong class="text-[11.5px] text-ink-secondary">{event.agent_id}</strong>
                <span class="text-[10.5px] text-ink-tertiary">{event.status} · {event.duration_ms ?? 0}ms</span>
              </div>
              <h3 class="mt-2 text-[12.5px] font-medium text-ink">{event.tool_id}</h3>
              <p class="mt-1 text-[11.5px] text-ink-tertiary">{event.result_summary}</p>
            </article>
          {/each}
        </div>
      {/if}
    </Card>
  {:else if activeTab === 'exportaciones'}
    <Card title="Exportaciones">
      {#if contentResult?.video?.output_path}
        <div class="flex items-start gap-3 rounded-lg border border-line bg-surface-inset p-3">
          {#if assetSrc(contentResult.video.cover_image_path)}
            <img src={assetSrc(contentResult.video.cover_image_path)} alt="" class="h-16 w-16 shrink-0 rounded-lg object-cover" />
          {/if}
          <div class="min-w-0 flex-1">
            <div class="flex items-center justify-between gap-2">
              <p class="truncate text-[12.5px] text-ink">{contentResult.video.output_path}</p>
              <Badge tone={contentResult.video.qc_passed ? 'success' : 'error'}>{contentResult.video.qc_passed ? 'QC aprobado' : 'QC con problemas'}</Badge>
            </div>
            <p class="mt-1 text-[11px] text-ink-tertiary">
              {contentResult.video.scene_count} escenas · {contentResult.video.shot_count} tomas
              {#if contentResult.video.integrated_lufs != null} · {contentResult.video.integrated_lufs.toFixed(1)} LUFS{/if}
            </p>
            {#if contentResult.video.source_kind_counts}
              <div class="mt-2 flex flex-wrap gap-1.5">
                {#each Object.entries(contentResult.video.source_kind_counts) as [kind, count]}
                  <span class="rounded-full border border-line bg-surface px-2 py-0.5 text-[10.5px] text-ink-tertiary">{kind}: {count}</span>
                {/each}
              </div>
            {/if}
            {#if (contentResult.video.qc_issues ?? []).length > 0}
              <ul class="mt-2 space-y-0.5">
                {#each contentResult.video.qc_issues as issue}
                  <li class="text-[11px] text-error">{issue}</li>
                {/each}
              </ul>
            {/if}
          </div>
        </div>
      {:else if contentResult?.video?.status === 'failed'}
        <p class="text-[13px] text-ink-secondary">La producción de video falló para esta ejecución ({contentResult.video.error}); el guion de texto se guardó igualmente.</p>
      {:else}
        <p class="text-[13px] text-ink-secondary">Sin exportaciones todavía. El master 16:9 y sus variantes por plataforma aparecerán aquí una vez que el pipeline visual (V0-V8) produzca un episodio.</p>
      {/if}
    </Card>
  {/if}
</div>
