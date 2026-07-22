<script>
  import { onMount } from 'svelte';
  import Card from '../components/Card.svelte';
  import Badge from '../components/Badge.svelte';
  import Icon from '../components/Icon.svelte';
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
      <Card>
        <p class="text-[11px] text-ink-tertiary">Episodios totales</p>
        <p class="mt-1 font-display text-2xl font-semibold text-ink">{loading ? '—' : episodes.length}</p>
      </Card>
      <Card>
        <p class="text-[11px] text-ink-tertiary">Aprobación QC</p>
        <p class="mt-1 font-display text-2xl font-semibold text-ink">{qcPassRate === null ? '—' : `${qcPassRate}%`}</p>
      </Card>
      <Card>
        <p class="text-[11px] text-ink-tertiary">Duración promedio</p>
        <p class="mt-1 font-display text-2xl font-semibold text-ink">{avgDurationSeconds === null ? '—' : `${avgDurationSeconds}s`}</p>
      </Card>
      <Card>
        <p class="text-[11px] text-ink-tertiary">Herramientas trazadas</p>
        <p class="mt-1 font-display text-2xl font-semibold text-ink">{(operations.toolEvents ?? []).length}</p>
      </Card>
    </div>

    <div class="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_1fr]">
      <Card title="Episodios por programa" subtitle="episodes.list">
        {#if loading}
          <p class="text-[13px] text-ink-secondary">Cargando…</p>
        {:else if byProgram.length === 0}
          <p class="text-[13px] text-ink-secondary">Sin programas cargados.</p>
        {:else}
          <ul class="space-y-2.5">
            {#each byProgram as row (row.id)}
              <li>
                <div class="flex items-center justify-between text-[12.5px]">
                  <span class="text-ink">{row.name}</span>
                  <span class="text-ink-tertiary">{row.count}</span>
                </div>
                <div class="mt-1.5 h-1.5 rounded-full bg-line-subtle">
                  <div class="h-full rounded-full bg-purple-500" style={`width:${(row.count / maxProgramCount) * 100}%`}></div>
                </div>
              </li>
            {/each}
          </ul>
        {/if}
      </Card>

      <Card title="Generador / crítico" subtitle="Diversidad de enrutado de modelos">
        {#if loading}
          <p class="text-[13px] text-ink-secondary">Cargando…</p>
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
        <p class="text-[13px] text-ink-secondary">Cargando…</p>
      {:else if recentEpisodes.length === 0}
        <p class="text-[13px] text-ink-secondary">
          Sin episodios todavía. Créalos desde Estudio o espera a que el Agente B produzca la parrilla automáticamente.
        </p>
      {:else}
        <ul class="divide-y divide-line-subtle">
          {#each recentEpisodes as episode (episode.story_id)}
            <li class="flex items-center justify-between gap-3 py-2.5 text-[12.5px]">
              <div class="min-w-0">
                <p class="truncate text-ink">{episode.title}</p>
                <p class="mt-0.5 truncate text-[11px] text-ink-tertiary">{episode.program_id ?? 'sin programa'}</p>
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
