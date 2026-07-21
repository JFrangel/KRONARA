<script>
  import { onMount } from 'svelte';
  import Card from '../components/Card.svelte';
  import Badge from '../components/Badge.svelte';
  import Icon from '../components/Icon.svelte';
  import { callOperations } from '../tauri-operations.js';
  import { programGradient } from '../programArt.js';

  let { operations = {}, control = {}, onNavigate = () => {} } = $props();

  let programs = $state([]);
  let episodes = $state([]);
  let loadError = $state(false);
  let loading = $state(true);

  const PIPELINE_STAGES = [
    { key: 'investigacion', label: 'Investigación', icon: 'search' },
    { key: 'guion', label: 'Guion', icon: 'list' },
    { key: 'narracion', label: 'Narración', icon: 'wand' },
    { key: 'produccion', label: 'Producción', icon: 'film' },
    { key: 'publicacion', label: 'Publicación', icon: 'send' },
  ];

  const WEEKDAYS = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo'];
  const WEEKDAY_LABELS = { lunes: 'Lun', martes: 'Mar', miercoles: 'Mié', jueves: 'Jue', viernes: 'Vie', sabado: 'Sáb', domingo: 'Dom' };
  const TODAY_WEEKDAY = WEEKDAYS[(new Date().getDay() + 6) % 7];

  onMount(async () => {
    try {
      const [programsResponse, episodesResponse] = await Promise.all([
        callOperations('programs.list', {}),
        callOperations('episodes.list', { limit: 200 }),
      ]);
      programs = programsResponse.programs ?? [];
      episodes = episodesResponse.episodes ?? [];
    } catch (error) {
      loadError = true;
    } finally {
      loading = false;
    }
  });

  function episodeCountFor(programId) {
    return episodes.filter((episode) => episode.program_id === programId).length;
  }

  function latestEpisodeFor(programId) {
    return episodes.find((episode) => episode.program_id === programId) ?? null;
  }

  function programFor(weekday) {
    return programs.find((program) => program.weekday === weekday);
  }

  const recentEvents = $derived((operations.toolEvents ?? []).slice(-6).reverse());
  const totalEpisodes = $derived(episodes.length);
  const approvedEpisodes = $derived(
    episodes.filter((episode) => episode.narrative_passed && episode.originality_passed).length
  );
</script>

<div class="space-y-4">
  <div>
    <h1 class="font-display text-xl font-semibold text-ink">¡Bienvenido de vuelta! <span aria-hidden="true">👋</span></h1>
    <p class="mt-1 text-[13px] text-ink-secondary">Aquí tienes el estado general de tu red de contenidos.</p>
  </div>

  <div class="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_340px]">
    <div class="space-y-4">
      <Card title="Programas activos" subtitle="7 programas · parrilla semanal">
        {#if loadError}
          <p class="text-[13px] text-ink-secondary">No se pudo cargar la parrilla. Abre Kronara desde la aplicación de escritorio.</p>
        {:else}
          <div class="flex gap-3 overflow-x-auto pb-1">
            {#each (loading ? Array.from({ length: 7 }, (_, index) => ({ program_id: `_placeholder_${index}` })) : programs) as program (program.program_id)}
              <button
                class="group relative h-40 w-56 shrink-0 overflow-hidden rounded-xl border text-left transition-colors"
                class:border-line={!loading}
                class:border-purple-500={!loading && TODAY_WEEKDAY === program.weekday}
                class:border-line-subtle={loading}
                class:opacity-60={loading}
                style={loading ? undefined : `background:${programGradient(program.program_id)}`}
                onclick={() => onNavigate('programas')}
                disabled={loading}
              >
                {#if !loading}
                  <div class="absolute inset-0 bg-gradient-to-t from-black/75 via-black/10 to-transparent"></div>
                  <div class="relative flex h-full flex-col justify-end p-3.5">
                    <span class="w-fit rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-medium capitalize text-ink backdrop-blur-sm">{program.weekday}</span>
                    <p class="mt-2 font-display text-[15px] font-semibold leading-tight text-ink">{program.name}</p>
                    <p class="mt-1 truncate text-[11px] text-ink-secondary">{program.genre}</p>
                    <p class="mt-2 text-[10.5px] text-ink-tertiary">{episodeCountFor(program.program_id)} episodio{episodeCountFor(program.program_id) === 1 ? '' : 's'}</p>
                  </div>
                {/if}
              </button>
            {/each}
          </div>
        {/if}
      </Card>

      <Card title="Calendario editorial" subtitle="Esta semana">
        {#if !loadError}
          <div class="grid grid-cols-3 gap-2 sm:grid-cols-7">
            {#each WEEKDAYS as weekday}
              {@const program = programFor(weekday)}
              {@const episode = program ? latestEpisodeFor(program.program_id) : null}
              {@const isToday = weekday === TODAY_WEEKDAY}
              <div
                class="rounded-lg border p-2.5 {isToday ? 'border-purple-500 bg-purple-500/10' : 'border-line bg-surface-inset'}"
              >
                <p class="text-[10px] font-medium uppercase tracking-wide" class:text-purple-300={isToday} class:text-ink-tertiary={!isToday}>{WEEKDAY_LABELS[weekday]}</p>
                {#if program}
                  <p class="mt-1.5 truncate text-[11px] font-medium text-ink">{program.name}</p>
                  {#if episode}
                    <Badge tone={episode.narrative_passed && episode.originality_passed ? 'success' : 'neutral'}>{episode.narrative_passed && episode.originality_passed ? 'Listo' : 'Revisar'}</Badge>
                  {:else}
                    <p class="mt-1 text-[10px] text-ink-tertiary">Sin episodio</p>
                  {/if}
                {:else}
                  <p class="mt-1.5 text-[11px] text-ink-tertiary">—</p>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
        <button class="mt-3 text-[11.5px] text-purple-300 hover:text-purple-200" onclick={() => onNavigate('calendario')}>Ver calendario completo →</button>
      </Card>

      <Card title="Pipeline de producción" subtitle="Persistente y recuperable">
        <div class="grid grid-cols-2 gap-2.5 sm:grid-cols-5">
          {#each PIPELINE_STAGES as stage, index}
            <div class="rounded-xl border border-line bg-surface-inset p-3">
              <div class="flex items-center justify-between">
                <Icon name={stage.icon} size={14} class="text-ink-tertiary" />
                <span class="text-[10px] text-ink-tertiary">0{index + 1}</span>
              </div>
              <p class="mt-2 text-[12.5px] font-medium text-ink">{stage.label}</p>
              <p class="mt-1 text-[11px] text-ink-tertiary">0 en cola</p>
            </div>
          {/each}
        </div>
      </Card>

      <Card title="Actividad reciente" subtitle="tools.timeline">
        {#if recentEvents.length === 0}
          <p class="text-[13px] text-ink-secondary">Las llamadas de las herramientas aparecerán aquí con su agente, resultado y evidencia.</p>
        {:else}
          <ul class="space-y-2">
            {#each recentEvents as event}
              <li class="flex items-start justify-between gap-3 rounded-lg border border-line bg-surface-inset px-3 py-2.5">
                <div class="min-w-0">
                  <p class="truncate text-[12.5px] font-medium text-ink">{event.tool_id}</p>
                  <p class="truncate text-[11.5px] text-ink-tertiary">{event.agent_id} · {event.result_summary}</p>
                </div>
                <Badge tone={event.status === 'completed' ? 'success' : event.status === 'failed' || event.status === 'blocked' ? 'error' : 'neutral'}>
                  {event.status}
                </Badge>
              </li>
            {/each}
          </ul>
        {/if}
      </Card>
    </div>

    <div class="space-y-4">
      <Card title="Estado del sistema">
        <div class="flex items-center gap-2">
          <span class="h-2 w-2 rounded-full" class:bg-success={operations.connection === 'connected'} class:bg-error={operations.connection !== 'connected'}></span>
          <span class="text-[13px] text-ink">{operations.connection === 'connected' ? 'Plano cognitivo conectado' : 'Sin conexión al plano cognitivo'}</span>
        </div>
        <div class="mt-3 flex items-center gap-2">
          <span class="h-2 w-2 rounded-full" class:bg-purple-400={!control.paused} class:bg-warning={control.paused}></span>
          <span class="text-[13px] text-ink">{control.paused ? 'Operación en pausa global' : 'Modo FULL AUTO'}</span>
        </div>
        <p class="mt-3 text-[11.5px] leading-relaxed text-ink-tertiary">
          Solo avanza cuando derechos, originalidad, calidad y políticas pasan. La autoridad de Rust controla secretos y efectos.
        </p>
      </Card>

      <Card title="Resumen general" subtitle="Todo el tiempo">
        <dl class="grid grid-cols-2 gap-3">
          <div class="rounded-lg border border-line bg-surface-inset p-2.5">
            <dt class="text-[11px] text-ink-tertiary">Episodios publicados</dt>
            <dd class="mt-1 font-display text-lg font-semibold text-ink">{loading ? '—' : totalEpisodes}</dd>
          </div>
          <div class="rounded-lg border border-line bg-surface-inset p-2.5">
            <dt class="text-[11px] text-ink-tertiary">Aprobación QC</dt>
            <dd class="mt-1 font-display text-lg font-semibold text-ink">{loading || totalEpisodes === 0 ? '—' : `${Math.round((approvedEpisodes / totalEpisodes) * 100)}%`}</dd>
          </div>
          <div class="rounded-lg border border-line bg-surface-inset p-2.5">
            <dt class="text-[11px] text-ink-tertiary">Herramientas trazadas</dt>
            <dd class="mt-1 font-display text-lg font-semibold text-ink">{(operations.toolEvents ?? []).length}</dd>
          </div>
          <div class="rounded-lg border border-line bg-surface-inset p-2.5">
            <dt class="text-[11px] text-ink-tertiary">Programas activos</dt>
            <dd class="mt-1 font-display text-lg font-semibold text-ink">{loading ? '—' : programs.length}</dd>
          </div>
        </dl>
        <p class="mt-3 text-[11px] leading-relaxed text-ink-tertiary">
          Reproducciones, tiempo de visualización y suscriptores aparecerán aquí una vez que Kronara Pulse lea métricas reales de las plataformas conectadas.
        </p>
      </Card>

      <Card title="Tareas próximas">
        <p class="text-[13px] text-ink-secondary">
          Sin tareas programadas todavía. El Agente B (parrilla semanal + scheduler) llenará esto automáticamente por programa.
        </p>
      </Card>
    </div>
  </div>
</div>
