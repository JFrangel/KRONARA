<script>
  import { onMount } from 'svelte';
  import Card from '../components/Card.svelte';
  import Badge from '../components/Badge.svelte';
  import Icon from '../components/Icon.svelte';
  import { assetSrc, callOperations } from '../local-operations.js';
  import { programGradient } from '../programArt.js';
  import { currentGenerationDetail, currentGenerationStage, episodeGeneration, formatElapsed, generationPercent, GENERATION_STAGES } from '../generation-state.js';

  let { operations = {}, control = {}, onNavigate = () => {} } = $props();

  let programs = $state([]);
  let episodes = $state([]);
  let timelineEvents = $state([]);
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
      const [programsResponse, episodesResponse, timelineResponse] = await Promise.all([
        callOperations('programs.list', {}),
        callOperations('episodes.list', { limit: 200 }),
        callOperations('tools.timeline', {}),
      ]);
      programs = programsResponse.programs ?? [];
      episodes = episodesResponse.episodes ?? [];
      timelineEvents = timelineResponse.events ?? [];
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

  function coverImageFor(programId) {
    const withCover = episodes.find(
      (episode) => episode.program_id === programId && episode.cover_image_path
    );
    const program = programs.find((item) => item.program_id === programId);
    return assetSrc(withCover?.cover_image_path ?? program?.cover_image_path);
  }

  function programFor(weekday) {
    return programs.find((program) => program.weekday === weekday);
  }

  const recentEvents = $derived((timelineEvents.length ? timelineEvents : operations.toolEvents ?? []).slice(-6).reverse());
  const totalEpisodes = $derived(episodes.length);
  const approvedEpisodes = $derived(
    episodes.filter((episode) => episode.narrative_passed && episode.originality_passed).length
  );

  function pipelineCount(key) {
    if (key === 'investigacion') return episodes.filter((episode) => episode.research_status === 'completed').length;
    if (key === 'guion') return episodes.filter((episode) => episode.narrative_passed != null).length;
    if (key === 'narracion') return episodes.filter((episode) => episode.audio_status === 'completed' || episode.audio_path).length;
    if (key === 'produccion') return episodes.filter((episode) => episode.video_status === 'completed').length;
    if (key === 'publicacion') return episodes.filter((episode) => episode.publication_status === 'published' || episode.published_at).length;
    return 0;
  }

  function generationPipelineKey() {
    const key = GENERATION_STAGES[$episodeGeneration?.stageIndex ?? 0]?.key;
    if (key === 'investigacion') return 'investigacion';
    if (key === 'narracion') return 'narracion';
    if (key === 'produccion' || key === 'guardando') return 'produccion';
    return 'guion';
  }

  function isPipelineActive(key) {
    return $episodeGeneration?.status === 'running' && generationPipelineKey() === key;
  }

  function isPipelineCompleted(index) {
    if (!$episodeGeneration || $episodeGeneration.status === 'failed') return false;
    const activeIndex = PIPELINE_STAGES.findIndex((stage) => stage.key === generationPipelineKey());
    return $episodeGeneration.status === 'completed' || index < activeIndex;
  }

  const upcomingTasks = $derived(episodes.length > 0
    ? [
        { title: `Revisar: ${episodes[0].title}`, detail: 'Control visual y reproducción', when: 'Ahora', tone: 'Producción', icon: 'film' },
        { title: 'Validar portada del episodio', detail: 'Imagen generada y poster del video', when: 'Hoy', tone: 'Diseño', icon: 'wand' },
        { title: 'Comprobar calidad de audio', detail: 'QC de mezcla antes de publicar', when: 'Pendiente', tone: 'Revisión', icon: 'chart' },
      ]
    : [{ title: 'Crear el primer episodio', detail: 'Selecciona un programa para empezar', when: 'Pendiente', tone: 'Producción', icon: 'plus' }]);
</script>

<div class="space-y-4">
  <div>
    <h1 class="font-display text-xl font-semibold text-ink">¡Bienvenido de vuelta! <span aria-hidden="true">👋</span></h1>
    <p class="mt-1 text-[13px] text-ink-secondary">Aquí tienes el estado general de tu red de contenidos.</p>
  </div>

  <div class="grid grid-cols-1 gap-4 2xl:grid-cols-[1fr_340px]">
    <div class="space-y-4">
      <Card>
        <div class="mb-4 flex items-center justify-between gap-3">
          <div>
            <h2 class="font-display text-base font-semibold text-ink">Programas activos</h2>
            <p class="mt-1 text-[11px] text-ink-tertiary">{programs.length || 7} programas · parrilla semanal</p>
          </div>
          <button class="shrink-0 text-[11.5px] font-medium text-purple-300 transition hover:text-purple-200" onclick={() => onNavigate('programas')}>Ver todos <span aria-hidden="true">→</span></button>
        </div>
        {#if loadError}
          <p class="text-[13px] text-ink-secondary">No se pudo cargar la parrilla. Inicia la web local y verifica que Python esté conectado.</p>
        {:else}
          <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
            {#each (loading ? Array.from({ length: 5 }, (_, index) => ({ program_id: `_placeholder_${index}` })) : programs.slice(0, 5)) as program (program.program_id)}
              {@const cover = loading ? null : coverImageFor(program.program_id)}
              <button
                class="group relative h-56 min-w-0 overflow-hidden rounded-xl border text-left transition duration-200 hover:-translate-y-0.5 hover:border-purple-500"
                class:border-line={!loading}
                class:border-purple-500={!loading && TODAY_WEEKDAY === program.weekday}
                class:border-line-subtle={loading}
                class:opacity-60={loading}
                style={loading ? undefined : `background:${programGradient(program.program_id)}`}
                onclick={() => onNavigate('programas', { programId: program.program_id })}
                disabled={loading}
              >
                {#if !loading}
                  {#if cover}
                    <img src={cover} alt="" class="absolute inset-0 h-full w-full object-cover" loading="lazy" />
                  {/if}
                  <div class="absolute inset-0 bg-gradient-to-t from-black/75 via-black/10 to-transparent"></div>
                  <div class="relative flex h-full flex-col justify-end p-3.5">
                    <span class="w-fit rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-medium capitalize text-ink backdrop-blur-sm">{program.weekday}</span>
                    <p class="mt-2 font-display text-[15px] font-semibold leading-tight text-ink">{program.name}</p>
                    <p class="mt-1 line-clamp-2 text-[11px] leading-relaxed text-ink-secondary">{program.genre}</p>
                    <div class="mt-3 flex items-center justify-between text-[10.5px] text-ink-tertiary"><span>{episodeCountFor(program.program_id)} episodio{episodeCountFor(program.program_id) === 1 ? '' : 's'}</span><span class="capitalize">{program.weekday}</span></div>
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
                class="min-h-40 rounded-xl border p-3 transition {isToday ? 'border-purple-500 bg-purple-500/10 shadow-[0_0_24px_rgba(123,92,255,0.12)]' : 'border-line bg-surface-inset'}"
              >
                <div class="flex items-center justify-between gap-1">
                  <p class="text-[10px] font-medium uppercase tracking-wide" class:text-purple-300={isToday} class:text-ink-tertiary={!isToday}>{WEEKDAY_LABELS[weekday]}</p>
                  {#if isToday}<span class="rounded-full bg-purple-500 px-1.5 py-0.5 text-[9px] font-semibold text-ink">HOY</span>{/if}
                </div>
                {#if program}
                  <div class="mt-2 h-0.5 rounded-full" style={`background:${programGradient(program.program_id)}`}></div>
                  <p class="mt-2 line-clamp-2 text-[11px] font-semibold leading-tight text-ink">{program.name}</p>
                  {#if episode}
                    <Badge tone={episode.narrative_passed && episode.originality_passed ? 'success' : 'neutral'}>{episode.narrative_passed && episode.originality_passed ? 'Listo' : 'Revisar'}</Badge>
                    <p class="mt-2 line-clamp-2 text-[10.5px] leading-relaxed text-ink-secondary">{episode.title}</p>
                    <p class="mt-1 text-[9.5px] text-ink-tertiary">Video {episode.video_status === 'completed' ? 'validado' : 'pendiente'}</p>
                  {:else}
                    <Badge tone="neutral">Sin episodio</Badge>
                    <p class="mt-2 text-[10px] leading-relaxed text-ink-tertiary">Aún no hay contenido programado.</p>
                  {/if}
                  <button class="mt-3 text-[10px] font-medium text-purple-300 hover:text-purple-200" onclick={() => onNavigate('programas', { programId: program.program_id })}>Ver programa →</button>
                {:else}
                  <p class="mt-1.5 text-[11px] text-ink-tertiary">—</p>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
        <button class="mt-3 text-[11.5px] text-purple-300 hover:text-purple-200" onclick={() => onNavigate('calendario')}>Ver calendario completo →</button>
      </Card>

      <Card title="Pipeline de producción" subtitle={$episodeGeneration?.status === 'running' ? `Generando · ${currentGenerationStage($episodeGeneration).label} · ${formatElapsed($episodeGeneration.elapsedSeconds)}` : 'Persistente y recuperable'}>
        {#if $episodeGeneration}
          <div class="mb-3 rounded-lg border border-ember-500/30 bg-ember-500/10 p-3">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div class="min-w-0">
                <p class="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-tertiary">{$episodeGeneration.status === 'running' ? 'Episodio en generación' : $episodeGeneration.status === 'completed' ? 'Episodio generado' : 'Generación detenida'}</p>
                <p class="mt-1 truncate text-[13px] font-medium text-ink">{$episodeGeneration.programName ?? 'Programa'} · {currentGenerationStage($episodeGeneration).label}</p>
                <p class="mt-0.5 text-[11.5px] text-ink-tertiary">{currentGenerationDetail($episodeGeneration)}</p>
              </div>
              <div class="text-right">
                <p class="font-mono text-lg font-semibold text-ink">{generationPercent($episodeGeneration)}%</p>
                <p class="text-[10.5px] text-ink-tertiary">{formatElapsed($episodeGeneration.elapsedSeconds)}</p>
              </div>
            </div>
            <div class="mt-3 h-1.5 overflow-hidden rounded-full bg-line">
              <div class="h-full rounded-full bg-ember-500 transition-all duration-500" style={`width:${generationPercent($episodeGeneration)}%`}></div>
            </div>
          </div>
        {/if}
        <div class="grid grid-cols-2 gap-2.5 sm:grid-cols-5">
          {#each PIPELINE_STAGES as stage, index}
            {@const count = pipelineCount(stage.key)}
            {@const active = isPipelineActive(stage.key)}
            {@const completed = isPipelineCompleted(index)}
            <div
              class="rounded-xl border p-3 transition"
              class:border-ember-500={active}
              class:border-success={completed && !active}
              class:border-line={count === 0 && !active && !completed}
              class:border-purple-500={count > 0 && !active && !completed}
              class:bg-ember-500={active}
              class:bg-success={completed && !active}
              class:bg-purple-500={count > 0 && !active && !completed}
              class:bg-surface-inset={count === 0 && !active && !completed}
            >
              <div class="flex items-center justify-between">
                <Icon name={stage.icon} size={14} class={active || completed || count > 0 ? 'text-white/85' : 'text-ink-tertiary'} />
                <span class={active || completed || count > 0 ? 'text-[10px] font-semibold text-white/80' : 'text-[10px] text-ink-tertiary'}>0{index + 1}</span>
              </div>
              <p class={active || completed || count > 0 ? 'mt-2 text-[12.5px] font-semibold text-white' : 'mt-2 text-[12.5px] font-medium text-ink'}>{stage.label}</p>
              <p class={active || completed || count > 0 ? 'mt-1 text-[11.5px] font-medium text-white/85' : 'mt-1 text-[11px] text-ink-tertiary'}>{active ? 'En curso ahora' : completed ? 'Completado en este run' : `${count} ${count === 1 ? 'episodio' : 'episodios'}`}</p>
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
      <Card>
        <div class="mb-4 flex items-center justify-between gap-3">
          <h2 class="font-display text-base font-semibold text-ink">Resumen general</h2>
          <span class="rounded-lg border border-line bg-surface-inset px-2.5 py-1 text-[10.5px] text-ink-secondary">Esta semana</span>
        </div>
        <dl class="grid grid-cols-2 gap-2.5">
          <div class="rounded-xl border border-line bg-surface-inset p-3"><dt class="text-[10.5px] text-ink-tertiary">Episodios en biblioteca</dt><dd class="mt-1 font-display text-xl font-semibold text-ink">{loading ? '—' : totalEpisodes}</dd><p class="mt-1 text-[10px] text-success">Datos locales</p></div>
          <div class="rounded-xl border border-line bg-surface-inset p-3"><dt class="text-[10.5px] text-ink-tertiary">Programas activos</dt><dd class="mt-1 font-display text-xl font-semibold text-ink">{loading ? '—' : programs.length}</dd><p class="mt-1 text-[10px] text-ink-tertiary">Parrilla semanal</p></div>
          <div class="rounded-xl border border-line bg-surface-inset p-3"><dt class="text-[10.5px] text-ink-tertiary">QC aprobado</dt><dd class="mt-1 font-display text-xl font-semibold text-ink">{loading || totalEpisodes === 0 ? '—' : `${Math.round((approvedEpisodes / totalEpisodes) * 100)}%`}</dd><p class="mt-1 text-[10px] text-success">Narrativa y originalidad</p></div>
          <div class="rounded-xl border border-line bg-surface-inset p-3"><dt class="text-[10.5px] text-ink-tertiary">Trazas recientes</dt><dd class="mt-1 font-display text-xl font-semibold text-ink">{recentEvents.length}</dd><p class="mt-1 text-[10px] text-ink-tertiary">tools.timeline</p></div>
        </dl>
      </Card>

      <Card title="Estado del sistema">
        <div class="flex items-center gap-2">
          <span class="h-2 w-2 rounded-full" class:bg-success={operations.connection === 'connected'} class:bg-error={operations.connection !== 'connected'}></span>
          <span class="text-[13px] text-ink">{operations.connection === 'connected' ? 'Web local conectada' : 'Sin conexión al plano cognitivo'}</span>
        </div>
        <div class="mt-3 flex items-center gap-2">
          <span class="h-2 w-2 rounded-full" class:bg-purple-400={!control.paused} class:bg-warning={control.paused}></span>
          <span class="text-[13px] text-ink">{control.paused ? 'Operación en pausa global' : 'Modo FULL AUTO'}</span>
        </div>
        <p class="mt-3 text-[11.5px] leading-relaxed text-ink-tertiary">
          {operations.connection === 'connected' ? 'La web local ejecuta el sidecar Python y guarda episodios en el runtime local. Nada se publica si derechos, originalidad, calidad o políticas fallan.' : 'Inicia la web local para conectar el plano cognitivo y crear episodios reales.'}
        </p>
      </Card>

      <Card>
        <div class="mb-4 flex items-center justify-between gap-3"><h2 class="font-display text-base font-semibold text-ink">Tareas próximas</h2><span class="text-[11px] text-ink-tertiary">{upcomingTasks.length}</span></div>
        <ul class="divide-y divide-line-subtle">
          {#each upcomingTasks as task}
            <li class="flex items-center gap-3 py-3 first:pt-0 last:pb-0">
              <span class="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-purple-500/15 text-purple-300"><Icon name={task.icon} size={15} /></span>
              <div class="min-w-0 flex-1"><p class="truncate text-[12px] font-medium text-ink">{task.title}</p><p class="mt-0.5 truncate text-[10.5px] text-ink-tertiary">{task.detail}</p></div>
              <span class="shrink-0 rounded-full border border-line px-2 py-1 text-[10px] text-ink-tertiary">{task.when}</span>
            </li>
          {/each}
        </ul>
      </Card>
    </div>
  </div>
</div>
