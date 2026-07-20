<script>
  import { onMount } from 'svelte';
  import Card from '../components/Card.svelte';
  import Badge from '../components/Badge.svelte';
  import Icon from '../components/Icon.svelte';
  import { callOperations } from '../tauri-operations.js';

  let programs = $state([]);
  let loadError = $state(false);
  let selected = $state(null);
  let activeTab = $state('resumen');

  const TABS = ['resumen', 'episodios', 'calendario', 'personajes', 'configuracion', 'analiticas', 'recursos'];
  const TAB_LABELS = {
    resumen: 'Resumen', episodios: 'Episodios', calendario: 'Calendario', personajes: 'Personajes',
    configuracion: 'Configuración', analiticas: 'Analíticas', recursos: 'Recursos',
  };

  onMount(async () => {
    try {
      const response = await callOperations('programs.list', {});
      programs = response.programs ?? [];
    } catch (error) {
      loadError = true;
    }
  });

  function openProgram(program) {
    selected = program;
    activeTab = 'resumen';
  }
</script>

{#if loadError}
  <p class="text-[13px] text-ink-secondary">No se pudo cargar la parrilla de programas. Abre Kronara desde la aplicación de escritorio.</p>
{:else if selected}
  <div class="space-y-4">
    <button class="flex items-center gap-1.5 text-[12.5px] text-ink-tertiary hover:text-ink" onclick={() => (selected = null)}>
      <Icon name="chevron-left" size={14} /> Programas
    </button>

    <Card>
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Badge tone="purple">{selected.genre}</Badge>
          <h2 class="mt-2 font-display text-xl font-bold text-ink">{selected.name}</h2>
          <p class="mt-1 max-w-xl text-[13px] text-ink-secondary">{selected.description}</p>
        </div>
        <dl class="grid grid-cols-2 gap-3 text-right sm:grid-cols-4">
          <div><dt class="text-[10.5px] text-ink-tertiary">Día</dt><dd class="mt-0.5 text-[12.5px] capitalize text-ink">{selected.weekday}</dd></div>
          <div><dt class="text-[10.5px] text-ink-tertiary">Duración objetivo</dt><dd class="mt-0.5 text-[12.5px] text-ink">{selected.target_duration_seconds}s</dd></div>
          <div><dt class="text-[10.5px] text-ink-tertiary">Episodios</dt><dd class="mt-0.5 text-[12.5px] text-ink">0</dd></div>
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
      <Card>
        {#if activeTab === 'resumen'}
          <p class="text-[13px] text-ink-secondary">Sin episodios publicados aún para {selected.name}. Créalos desde Estudio o espera a que el Agente B (parrilla automática) los produzca en su horario.</p>
        {:else}
          <p class="text-[13px] text-ink-secondary">Esta pestaña ({TAB_LABELS[activeTab]}) se conecta cuando exista contenido real que mostrar.</p>
        {/if}
      </Card>
      <div class="space-y-4">
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
      </div>
    </div>
  </div>
{:else}
  <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
    {#each programs as program (program.program_id)}
      <button
        class="rounded-2xl border border-line bg-surface p-4 text-left transition-colors hover:border-purple-500"
        onclick={() => openProgram(program)}
      >
        <div class="flex items-center justify-between">
          <Badge tone="purple">{program.weekday}</Badge>
          <Badge tone="success">Activo</Badge>
        </div>
        <p class="mt-3 font-display text-sm font-semibold text-ink">{program.name}</p>
        <p class="mt-1 text-[12px] text-ink-tertiary">{program.genre}</p>
        <p class="mt-3 text-[11.5px] leading-relaxed text-ink-secondary">{program.description}</p>
        <div class="mt-4 flex items-center justify-between text-[11px] text-ink-tertiary">
          <span>0 episodios</span>
          <span>{program.target_duration_seconds}s objetivo</span>
        </div>
      </button>
    {/each}
  </div>
{/if}
