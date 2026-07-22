<script>
  import { onDestroy } from 'svelte';
  import Card from '../components/Card.svelte';
  import Badge from '../components/Badge.svelte';
  import Icon from '../components/Icon.svelte';
  import StubView from './StubView.svelte';
  import { applyProgressEvent } from '../operations-state.js';
  import { episodeGeneration } from '../generation-state.js';
  import { assetSrc, callOperations } from '../local-operations.js';

  let { operations = $bindable({}), connection = 'disconnected' } = $props();

  let subreddit = $state('Historias');
  let contentRunning = $state(false);
  let contentResult = $state(null);
  let notice = $state('');
  let activeTab = $state('en_vivo');

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
    if (!community) {
      notice = 'Escribe una comunidad de Reddit para investigar.';
      return;
    }
    contentRunning = true;
    contentResult = null;
    notice = '';
    try {
      const result = await callOperations('content.run', {
        story_id: `owned_reddit_${Date.now()}`,
        subreddits: [community],
        sort: 'hot',
        limit: 25,
        target_duration_seconds: 90,
      });
      contentResult = result;
      await refreshTimeline(result.run_id);
    } catch (error) {
      notice = 'El vertical productivo se detuvo: ninguna historia se publica si falla Reddit, los modelos, los derechos o la calidad.';
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
    <Card title="Vertical productivo" subtitle="Reddit oficial → oportunidad abstracta → historia propia">
      <div class="flex flex-wrap items-center gap-3">
        <label class="flex-1 min-w-[220px]">
          <span class="mb-1 block text-[11px] text-ink-tertiary">Comunidad para observar</span>
          <input
            class="w-full rounded-full border border-line bg-surface-inset px-4 py-2 text-[13px] text-ink placeholder:text-ink-tertiary focus:border-purple-500 focus:outline-none"
            bind:value={subreddit}
            placeholder="Historias"
            autocomplete="off"
          />
        </label>
        <button
          class="rounded-full bg-purple-500 px-5 py-2.5 text-[13px] font-medium text-ink hover:bg-purple-600 disabled:cursor-not-allowed disabled:opacity-40"
          onclick={runProductionContent}
          disabled={contentRunning || connection !== 'connected'}
        >
          {contentRunning ? 'Investigando y creando…' : 'Crear historia gobernada'}
        </button>
      </div>
      <p class="mt-3 text-[11.5px] text-ink-tertiary">
        <code class="text-purple-300">reddit.list_signals</code> usa solo señales abstractas; nunca entrega el cuerpo externo al escritor.
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
  {:else}
    <StubView
      icon="wand"
      title={TAB_LABELS[activeTab]}
      description="Esta pestaña se conecta cuando el guion tenga escenas navegables por separado (voz por escena, storyboard, biblioteca de recursos, mezcla de música y SFX)."
    />
  {/if}
</div>
