<script>
  import { onMount } from 'svelte';
  import Card from '../components/Card.svelte';
  import Badge from '../components/Badge.svelte';
  import { callOperations } from '../local-operations.js';

  const WEEKDAYS = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo'];
  const WEEKDAY_LABELS = {
    lunes: 'Lunes', martes: 'Martes', miercoles: 'Miércoles', jueves: 'Jueves',
    viernes: 'Viernes', sabado: 'Sábado', domingo: 'Domingo',
  };

  let programs = $state([]);
  let loadError = $state(false);

  onMount(async () => {
    try {
      const response = await callOperations('programs.list', {});
      programs = response.programs ?? [];
    } catch (error) {
      loadError = true;
    }
  });

  function programFor(weekday) {
    // Spanish weekday names in programs.v1.json don't carry accents (miercoles, not miércoles).
    return programs.find((p) => p.weekday === weekday);
  }
</script>

<Card title="Calendario editorial" subtitle="Parrilla semanal por programa">
  {#if loadError}
    <p class="text-[13px] text-ink-secondary">No se pudo cargar la parrilla. Inicia la web local y verifica que Python esté conectado.</p>
  {:else}
    <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-7">
      {#each WEEKDAYS as weekday}
        {@const program = programFor(weekday)}
        <div class="rounded-xl border border-line bg-surface-inset p-3">
          <p class="text-[10.5px] font-medium uppercase tracking-wide text-ink-tertiary">{WEEKDAY_LABELS[weekday]}</p>
          {#if program}
            <p class="mt-2 text-[12.5px] font-medium leading-snug text-ink">{program.name}</p>
            <p class="mt-1 text-[11px] text-ink-tertiary">{program.genre}</p>
            <div class="mt-3">
              <Badge tone="neutral">Sin episodio programado</Badge>
            </div>
          {:else}
            <p class="mt-2 text-[12px] text-ink-tertiary">Sin programa</p>
          {/if}
        </div>
      {/each}
    </div>
    <p class="mt-4 text-[11.5px] text-ink-tertiary">
      La parrilla automática (Agente B) programará episodios reales aquí una vez que el scheduler esté conectado a la ejecución.
    </p>
  {/if}
</Card>
