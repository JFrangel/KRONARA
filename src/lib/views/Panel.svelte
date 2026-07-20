<script>
  import Card from '../components/Card.svelte';
  import Badge from '../components/Badge.svelte';

  let { operations = {}, control = {}, onNavigate = () => {} } = $props();

  // The 7 real programs (config/programs/visual_style.v1.json) -- no episodes
  // have been produced through them yet, so counts are honestly zero rather
  // than fabricated. B1 (programs.v1.json registry) will make this live.
  const PROGRAMS = [
    { id: 'decisiones-dificiles', name: 'Decisiones Difíciles', day: 'Lunes' },
    { id: 'confesiones-anonimas', name: 'Confesiones Anónimas', day: 'Martes' },
    { id: 'cronicas-de-justicia', name: 'Crónicas de Justicia', day: 'Miércoles' },
    { id: 'mentes-ocultas', name: 'Mentes Ocultas', day: 'Jueves' },
    { id: 'viernes-paranormal', name: 'Viernes Paranormal', day: 'Viernes' },
    { id: 'historias-medianoche', name: 'Historias de Medianoche', day: 'Sábado' },
    { id: 'caso-de-la-semana', name: 'El Caso de la Semana', day: 'Domingo' },
  ];

  const PIPELINE_STAGES = [
    'Investigación', 'Concepto', 'Guion', 'Narración', 'Storyboard', 'Producción', 'Revisión', 'Publicación',
  ];

  const recentEvents = $derived((operations.toolEvents ?? []).slice(-6).reverse());
</script>

<div class="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_340px]">
  <div class="space-y-4">
    <Card title="Programas" subtitle="7 programas · parrilla semanal">
      <div class="flex gap-3 overflow-x-auto pb-1">
        {#each PROGRAMS as program (program.id)}
          <button
            class="w-56 shrink-0 rounded-xl border border-line bg-surface-inset p-4 text-left transition-colors hover:border-purple-500"
            onclick={() => onNavigate('programas')}
          >
            <Badge tone="purple">{program.day}</Badge>
            <p class="mt-3 font-display text-sm font-semibold text-ink">{program.name}</p>
            <p class="mt-1 text-[11.5px] text-ink-tertiary">Sin episodios publicados aún</p>
          </button>
        {/each}
      </div>
    </Card>

    <Card title="Pipeline de producción" subtitle="Persistente y recuperable">
      <div class="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {#each PIPELINE_STAGES as stage, index}
          <div class="rounded-xl border border-line bg-surface-inset p-3">
            <span class="text-[10px] text-ink-tertiary">0{index + 1}</span>
            <p class="mt-1 text-[12.5px] font-medium text-ink">{stage}</p>
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
        <div><dt class="text-[11px] text-ink-tertiary">Episodios publicados</dt><dd class="mt-1 font-display text-lg font-semibold text-ink">0</dd></div>
        <div><dt class="text-[11px] text-ink-tertiary">Reproducciones</dt><dd class="mt-1 font-display text-lg font-semibold text-ink">0</dd></div>
        <div><dt class="text-[11px] text-ink-tertiary">Herramientas trazadas</dt><dd class="mt-1 font-display text-lg font-semibold text-ink">{(operations.toolEvents ?? []).length}</dd></div>
        <div><dt class="text-[11px] text-ink-tertiary">Programas activos</dt><dd class="mt-1 font-display text-lg font-semibold text-ink">{PROGRAMS.length}</dd></div>
      </dl>
    </Card>

    <Card title="Tareas próximas">
      <p class="text-[13px] text-ink-secondary">
        Sin tareas programadas todavía. El Agente B (parrilla semanal + scheduler) llenará esto automáticamente por programa.
      </p>
    </Card>
  </div>
</div>
