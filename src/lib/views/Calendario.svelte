<script>
  import { onMount } from 'svelte';
  import { fly } from 'svelte/transition';
  import Card from '../components/Card.svelte';
  import Badge from '../components/Badge.svelte';
  import Skeleton from '../components/Skeleton.svelte';
  import Icon from '../components/Icon.svelte';
  import { callOperations } from '../local-operations.js';

  const WEEKDAYS = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo'];
  const WEEKDAY_LABELS = {
    lunes: 'Lunes', martes: 'Martes', miercoles: 'Miércoles', jueves: 'Jueves',
    viernes: 'Viernes', sabado: 'Sábado', domingo: 'Domingo',
  };
  // getDay(): 0=domingo … 6=sabado. Map to the accent-free keys used in programs.v1.json.
  const TODAY_KEY = ['domingo', 'lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado'][new Date().getDay()];

  let programs = $state([]);
  let loadError = $state(false);
  let loading = $state(true);

  let programsCount = $derived(programs.length);
  let daysCovered = $derived(WEEKDAYS.filter((w) => programs.some((p) => p.weekday === w)).length);

  onMount(async () => {
    try {
      const response = await callOperations('programs.list', {});
      programs = response.programs ?? [];
    } catch (error) {
      loadError = true;
    } finally {
      loading = false;
    }
  });

  function programFor(weekday) {
    // Spanish weekday names in programs.v1.json don't carry accents (miercoles, not miércoles).
    return programs.find((p) => p.weekday === weekday);
  }
</script>

<div class="space-y-4">
  <header class="flex flex-wrap items-end justify-between gap-3">
    <div>
      <h1 class="font-display text-xl font-semibold text-ink">Calendario editorial</h1>
      <p class="mt-1 text-[12.5px] text-ink-tertiary">Parrilla semanal por programa</p>
    </div>
    <div class="flex items-center gap-2">
      <div class="rounded-lg border border-line bg-surface px-3 py-2 text-center">
        <p class="font-display text-lg font-semibold leading-none text-ink">{programsCount}</p>
        <p class="mt-1 font-mono text-[9px] uppercase tracking-[0.09em] text-ink-tertiary">Programas activos</p>
      </div>
      <div class="rounded-lg border border-line bg-surface px-3 py-2 text-center">
        <p class="font-display text-lg font-semibold leading-none text-ink">{daysCovered}</p>
        <p class="mt-1 font-mono text-[9px] uppercase tracking-[0.09em] text-ink-tertiary">Días cubiertos</p>
      </div>
    </div>
  </header>

  <Card>
    {#if loadError}
      <p class="text-[13px] text-ink-secondary">No se pudo cargar la parrilla. Inicia la web local y verifica que Python esté conectado.</p>
    {:else}
      {#if loading}
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-7">
          {#each Array(7) as _, i}
            <div class="rounded-xl border border-line bg-surface-inset p-3">
              <div class="kronara-skeleton h-2.5 w-14 rounded-full"></div>
              <div class="mt-3">
                <Skeleton lines={2} />
              </div>
            </div>
          {/each}
        </div>
      {:else}
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-7">
          {#each WEEKDAYS as weekday, i}
            {@const program = programFor(weekday)}
            {@const isToday = weekday === TODAY_KEY}
            <div
              in:fly={{ y: 10, duration: 260, delay: i * 45 }}
              class="flex min-h-[136px] flex-col rounded-xl border bg-gradient-to-br from-surface to-surface-inset p-3.5 shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:border-purple-500/60 hover:shadow-card-hover {isToday ? 'border-purple-500/50 ring-1 ring-purple-500/40' : 'border-line'}"
            >
              <div class="flex items-center justify-between gap-2 border-b border-line-subtle pb-2">
                <p class="text-[10.5px] font-medium uppercase tracking-wide text-ink-tertiary">{WEEKDAY_LABELS[weekday]}</p>
                {#if isToday}
                  <Badge tone="purple">Hoy</Badge>
                {:else}
                  <span class="font-mono text-[9px] uppercase tracking-[0.08em] text-ink-tertiary">{String(i + 1).padStart(2, '0')}</span>
                {/if}
              </div>
              {#if program}
                <p class="mt-3 font-display text-[13px] font-semibold leading-snug text-ink">{program.name}</p>
                <p class="mt-1.5 font-mono text-[10px] uppercase tracking-wide text-ink-tertiary">{program.genre}</p>
                <div class="mt-auto pt-3">
                  <Badge tone="neutral">Sin episodio programado</Badge>
                </div>
              {:else}
                <div class="mt-3 flex flex-1 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-line py-4 text-center">
                  <Icon name="calendar" size={18} class="text-ink-tertiary/60" />
                  <p class="text-[11px] text-ink-tertiary">Sin programa</p>
                </div>
              {/if}
            </div>
          {/each}
        </div>
      {/if}
      <p class="mt-4 flex items-start gap-2 border-t border-line-subtle pt-3 text-[11.5px] text-ink-tertiary">
        <Icon name="info" size={15} class="mt-px shrink-0 text-info" />
        <span>La parrilla automática (Agente B) programará episodios reales aquí una vez que el scheduler esté conectado a la ejecución.</span>
      </p>
    {/if}
  </Card>
</div>
