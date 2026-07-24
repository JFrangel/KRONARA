<script>
  import { onMount } from 'svelte';
  import { fly } from 'svelte/transition';
  import Card from '../components/Card.svelte';
  import Badge from '../components/Badge.svelte';
  import Icon from '../components/Icon.svelte';
  import Skeleton from '../components/Skeleton.svelte';
  import { callOperations } from '../local-operations.js';
  import { CHANNELS } from '../nav.js';

  let { operations = {}, onNavigate = () => {} } = $props();

  let episodes = $state([]);
  let programs = $state([]);
  let loadError = $state(false);
  let loading = $state(true);
  let activeTab = $state('rendimiento');

  const TABS = ['rendimiento', 'audiencia'];
  const TAB_LABELS = { rendimiento: 'Rendimiento', audiencia: 'Audiencia' };

  onMount(async () => {
    try {
      const [episodesResponse, programsResponse] = await Promise.all([
        callOperations('episodes.list', { limit: 200 }),
        callOperations('programs.list', {}),
      ]);
      episodes = episodesResponse.episodes ?? [];
      programs = programsResponse.programs ?? [];
    } catch (error) {
      loadError = true;
    } finally {
      loading = false;
    }
  });

  // #97: Kronara Pulse -- el agente de métricas da recomendaciones editoriales.
  // Con métricas reales (vía la conexión de red) el análisis es más rico; por
  // ahora razona sobre el catálogo (títulos, duración, QC).
  let pulse = $state(null);
  let pulseLoading = $state(false);
  let pulseError = $state('');

  async function runPulse() {
    if (pulseLoading || episodes.length === 0) return;
    pulseLoading = true;
    pulse = null;
    pulseError = '';
    try {
      const eps = episodes.slice(0, 40).map((e) => ({
        title: e.title,
        program: e.program_id,
        duration_seconds: e.duration_seconds,
        narrative_passed: e.narrative_passed,
        originality_passed: e.originality_passed,
        content_kind: e.content_kind,
        style_id: e.style_id,
        video_source_kind_counts: e.video_source_kind_counts,
      }));
      const result = await callOperations('pulse.analyze', { episodes: eps });
      if (result.status === 'ok') pulse = result;
      else pulseError = result.detail || 'Sin datos suficientes para el análisis.';
    } catch (error) {
      pulseError = 'Kronara Pulse no respondió (revisa la ruta de modelos).';
    } finally {
      pulseLoading = false;
    }
  }

  const qcPassRate = $derived.by(() => {
    if (episodes.length === 0) return null;
    const passed = episodes.filter((e) => e.narrative_passed && e.originality_passed).length;
    return Math.round((passed / episodes.length) * 100);
  });

  const avgDurationSeconds = $derived.by(() => {
    const withDuration = episodes.filter((e) => e.duration_seconds);
    if (withDuration.length === 0) return null;
    const total = withDuration.reduce((sum, e) => sum + e.duration_seconds, 0);
    return Math.round(total / withDuration.length);
  });

  const byProgram = $derived.by(() => {
    const counts = {};
    for (const episode of episodes) {
      const id = episode.program_id || 'sin_programa';
      counts[id] = (counts[id] ?? 0) + 1;
    }
    const rows = programs.map((program) => ({
      id: program.program_id,
      name: program.name,
      weekday: program.weekday,
      count: counts[program.program_id] ?? 0,
    }));
    return rows.sort((a, b) => b.count - a.count);
  });

  const maxProgramCount = $derived(Math.max(1, ...byProgram.map((row) => row.count)));

  const byModelPair = $derived.by(() => {
    const counts = {};
    for (const episode of episodes) {
      const key = `${episode.generator_family ?? '—'} / ${episode.critic_family ?? '—'}`;
      counts[key] = (counts[key] ?? 0) + 1;
    }
    return Object.entries(counts)
      .map(([pair, count]) => ({ pair, count }))
      .sort((a, b) => b.count - a.count);
  });

  const recentEpisodes = $derived([...episodes].slice(0, 6));
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

  {#if loadError}
    <p class="text-[13px] text-ink-secondary">No se pudo cargar el rendimiento. Inicia la web local y verifica que Python esté conectado.</p>
  {:else if activeTab === 'rendimiento'}
    <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Card interactive>
        <span class="block h-0.5 w-6 rounded-full bg-purple-500/50"></span>
        <p class="mt-2 text-[10px] uppercase tracking-[0.08em] text-ink-tertiary">Episodios totales</p>
        {#if loading}<span class="mt-1 block h-7 w-16 rounded-md kron-shimmer"></span>{:else}<p class="mt-1 font-display text-2xl font-semibold tabular-nums text-ink">{episodes.length}</p>{/if}
      </Card>
      <Card interactive>
        <span class="block h-0.5 w-6 rounded-full bg-purple-500/50"></span>
        <p class="mt-2 text-[10px] uppercase tracking-[0.08em] text-ink-tertiary">Aprobación QC</p>
        {#if loading}<span class="mt-1 block h-7 w-16 rounded-md kron-shimmer"></span>{:else}<p class="mt-1 font-display text-2xl font-semibold tabular-nums {qcPassRate !== null && qcPassRate >= 80 ? 'text-success' : qcPassRate !== null && qcPassRate < 60 ? 'text-warning' : 'text-ink'}">{qcPassRate === null ? '—' : qcPassRate}<span class="ml-0.5 text-[13px] font-normal text-ink-tertiary">%</span></p>{/if}
      </Card>
      <Card interactive>
        <span class="block h-0.5 w-6 rounded-full bg-purple-500/50"></span>
        <p class="mt-2 text-[10px] uppercase tracking-[0.08em] text-ink-tertiary">Duración promedio</p>
        {#if loading}<span class="mt-1 block h-7 w-16 rounded-md kron-shimmer"></span>{:else}<p class="mt-1 font-display text-2xl font-semibold tabular-nums text-ink">{avgDurationSeconds === null ? '—' : avgDurationSeconds}<span class="ml-0.5 text-[13px] font-normal text-ink-tertiary">s</span></p>{/if}
      </Card>
      <Card interactive>
        <span class="block h-0.5 w-6 rounded-full bg-purple-500/50"></span>
        <p class="mt-2 text-[10px] uppercase tracking-[0.08em] text-ink-tertiary">Herramientas trazadas</p>
        <p class="mt-1 font-display text-2xl font-semibold tabular-nums text-ink">{(operations.toolEvents ?? []).length}</p>
      </Card>
    </div>

    <Card title="Kronara Pulse" subtitle="El agente analiza el catálogo y recomienda qué funciona, qué cambiar y fórmulas de título">
      <div class="flex flex-wrap items-center gap-3">
        <button
          class="rounded-full bg-purple-500 px-5 py-2.5 text-[13px] font-medium text-ink hover:bg-purple-600 disabled:cursor-not-allowed disabled:opacity-40"
          onclick={runPulse}
          disabled={pulseLoading || episodes.length === 0}
        >
          {pulseLoading ? 'Analizando…' : 'Analizar con Pulse'}
        </button>
        <p class="text-[11.5px] text-ink-tertiary">Con métricas reales (vía Postiz/red conectada) el análisis se afina; ahora razona sobre el catálogo.</p>
      </div>
      {#if pulseError}<p class="mt-3 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-[12px] text-warning">{pulseError}</p>{/if}
      {#if pulse}
        <div class="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {#each [['Qué funciona', pulse.what_works, 'border-l-success'], ['Qué cambiar', pulse.what_to_change, 'border-l-warning'], ['Fórmulas de título', pulse.title_formulas, 'border-l-purple-500'], ['Próximos temas', pulse.next_topics, 'border-l-info']] as [label, items, accent], i}
            <div class="rounded-xl border border-l-2 border-line bg-surface-inset p-3 {accent}" in:fly={{ y: 8, duration: 280, delay: i * 60 }}>
              <p class="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-tertiary">{label}</p>
              <ul class="mt-1.5 space-y-1">
                {#each items ?? [] as item}<li class="flex gap-2 text-[12px] leading-relaxed text-ink-secondary"><span class="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-purple-400/60"></span><span>{item}</span></li>{/each}
              </ul>
            </div>
          {/each}
        </div>
      {/if}
    </Card>

    <div class="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_1fr]">
      <Card title="Episodios por programa" subtitle="episodes.list">
        {#if loading}
          <Skeleton lines={4} class="text-ink" />
        {:else if byProgram.length === 0}
          <p class="text-[13px] text-ink-secondary">Sin programas cargados.</p>
        {:else}
          <ul class="space-y-2.5">
            {#each byProgram as row, i (row.id)}
              <li in:fly={{ y: 6, duration: 300, delay: Math.min(i, 8) * 45 }}>
                <div class="flex items-center justify-between text-[12.5px]">
                  <span class="text-ink">{row.name}</span>
                  <span class="font-mono text-[11px] tabular-nums text-ink-secondary">{row.count}</span>
                </div>
                <div class="mt-1.5 h-1.5 rounded-full bg-line-subtle">
                  <div class="h-full rounded-full bg-gradient-to-r from-purple-600 to-purple-400 transition-[width] duration-700 ease-out" style={`width:${(row.count / maxProgramCount) * 100}%`}></div>
                </div>
              </li>
            {/each}
          </ul>
        {/if}
      </Card>

      <Card title="Generador / crítico" subtitle="Diversidad de enrutado de modelos">
        {#if loading}
          <Skeleton lines={4} class="text-ink" />
        {:else if byModelPair.length === 0}
          <p class="text-[13px] text-ink-secondary">Sin episodios todavía -- esta vista se llena con cada ejecución de <code>content.run</code>.</p>
        {:else}
          <ul class="divide-y divide-line-subtle">
            {#each byModelPair as row (row.pair)}
              <li class="flex items-center justify-between py-2 text-[12.5px]">
                <span class="font-mono text-ink-secondary">{row.pair}</span>
                <Badge tone="purple">{row.count}</Badge>
              </li>
            {/each}
          </ul>
        {/if}
      </Card>
    </div>

    <Card title="Episodios recientes" subtitle={loading ? undefined : `${episodes.length} en total`}>
      {#if loading}
        <Skeleton lines={4} class="text-ink" />
      {:else if recentEpisodes.length === 0}
        <p class="text-[13px] text-ink-secondary">
          Sin episodios todavía. Créalos desde Estudio o espera a que el Agente B produzca la parrilla automáticamente.
        </p>
      {:else}
        <ul class="space-y-0.5">
          {#each recentEpisodes as episode, i (episode.story_id)}
            <li
              class="group -mx-2 flex items-center justify-between gap-3 rounded-lg px-2 py-2.5 text-[12.5px] transition-colors hover:bg-surface-inset"
              in:fly={{ y: 6, duration: 260, delay: Math.min(i, 8) * 40 }}
            >
              <div class="min-w-0">
                <p class="truncate font-display text-[13.5px] text-ink transition-colors group-hover:text-purple-200">{episode.title}</p>
                <p class="mt-0.5 truncate font-mono text-[10.5px] text-ink-tertiary">{episode.program_id ?? 'sin programa'}</p>
              </div>
              <Badge tone={episode.narrative_passed && episode.originality_passed ? 'success' : 'neutral'}>
                {episode.narrative_passed && episode.originality_passed ? 'Aprobado' : 'Revisar'}
              </Badge>
            </li>
          {/each}
        </ul>
      {/if}
    </Card>
  {:else}
    <Card title="Cuentas conectadas" subtitle="Estado real de credenciales -- no simulado">
      <ul class="divide-y divide-line-subtle">
        {#each CHANNELS as channel (channel.id)}
          <li class="flex items-center justify-between py-2.5">
            <span class="text-[12.5px] text-ink">{channel.label}</span>
            <div class="flex items-center gap-2">
              <Badge tone="neutral">Sin verificar</Badge>
              <button
                class="flex items-center gap-1 rounded-full border border-line px-2.5 py-1 text-[11.5px] text-ink-secondary hover:border-purple-500 hover:text-ink"
                onclick={() => onNavigate('configuracion')}
              >
                Conectar <Icon name="external-link" size={12} />
              </button>
            </div>
          </li>
        {/each}
      </ul>
    </Card>

    <Card title="Audiencia">
      <div class="flex flex-col items-center justify-center gap-3 px-4 py-10 text-center">
        <span class="grid h-12 w-12 place-items-center rounded-full bg-surface-hover text-purple-400">
          <Icon name="users" size={22} />
        </span>
        <p class="max-w-md text-[13px] leading-relaxed text-ink-secondary">
          Seguidores, retención por segundo y demografía aparecerán aquí una vez que Kronara Pulse (Agente B) esté
          leyendo métricas reales de las plataformas conectadas. Sin cuentas conectadas, no hay datos que mostrar --
          nunca se simulan aquí.
        </p>
      </div>
    </Card>
  {/if}
</div>
