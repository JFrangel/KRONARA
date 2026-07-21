<script>
  import { onMount } from 'svelte';
  import Card from '../components/Card.svelte';
  import Badge from '../components/Badge.svelte';
  import Icon from '../components/Icon.svelte';
  import { callOperations } from '../tauri-operations.js';
  import { programGradient } from '../programArt.js';

  let programs = $state([]);
  let episodes = $state([]);
  let loadError = $state(false);
  let loading = $state(true);
  let selected = $state(null);
  let activeTab = $state('resumen');

  // Episodios lives here rather than as its own top-level section -- every
  // episode belongs to exactly one program, so browsing them detached from
  // that program threw away the one grouping that actually matters.
  const TABS = ['resumen', 'episodios', 'calendario', 'personajes', 'configuracion', 'analiticas', 'recursos'];
  const TAB_LABELS = {
    resumen: 'Resumen', episodios: 'Episodios', calendario: 'Calendario', personajes: 'Personajes',
    configuracion: 'Configuración', analiticas: 'Analíticas', recursos: 'Recursos',
  };

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

  function openProgram(program) {
    selected = program;
    activeTab = 'resumen';
  }

  function episodesFor(programId) {
    return episodes.filter((episode) => episode.program_id === programId);
  }

  function episodeCountFor(programId) {
    return episodesFor(programId).length;
  }

  function formatDate(unixSeconds) {
    if (!unixSeconds) return '—';
    return new Date(unixSeconds * 1000).toLocaleDateString('es', { year: 'numeric', month: 'short', day: 'numeric' });
  }

  function statusTone(episode) {
    if (episode.narrative_passed && episode.originality_passed) return 'success';
    if (episode.narrative_passed === false || episode.originality_passed === false) return 'error';
    return 'neutral';
  }

  const selectedEpisodes = $derived(selected ? episodesFor(selected.program_id) : []);
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
        <div class="flex items-start gap-3.5">
          <span
            class="grid h-14 w-14 shrink-0 place-items-center rounded-xl font-display text-lg font-bold text-ink"
            style={`background:${programGradient(selected.program_id)}`}
          >{selected.name.charAt(0)}</span>
          <div>
            <Badge tone="purple">{selected.genre}</Badge>
            <h2 class="mt-2 font-display text-xl font-bold text-ink">{selected.name}</h2>
            <p class="mt-1 max-w-xl text-[13px] text-ink-secondary">{selected.description}</p>
          </div>
        </div>
        <dl class="grid grid-cols-2 gap-3 text-right sm:grid-cols-4">
          <div><dt class="text-[10.5px] text-ink-tertiary">Día</dt><dd class="mt-0.5 text-[12.5px] capitalize text-ink">{selected.weekday}</dd></div>
          <div><dt class="text-[10.5px] text-ink-tertiary">Duración objetivo</dt><dd class="mt-0.5 text-[12.5px] text-ink">{selected.target_duration_seconds}s</dd></div>
          <div><dt class="text-[10.5px] text-ink-tertiary">Episodios</dt><dd class="mt-0.5 text-[12.5px] text-ink">{episodeCountFor(selected.program_id)}</dd></div>
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
      <Card subtitle={activeTab === 'episodios' && selectedEpisodes.length ? `${selectedEpisodes.length} episodio(s)` : undefined}>
        {#if activeTab === 'resumen'}
          {#if selectedEpisodes.length > 0}
            <p class="text-[13px] text-ink-secondary">
              {selectedEpisodes.length} episodio{selectedEpisodes.length === 1 ? '' : 's'} producido{selectedEpisodes.length === 1 ? '' : 's'} para {selected.name}.
              Revísalos en la pestaña Episodios.
            </p>
          {:else}
            <p class="text-[13px] text-ink-secondary">Sin episodios publicados aún para {selected.name}. Créalos desde Estudio o espera a que el Agente B (parrilla automática) los produzca en su horario.</p>
          {/if}
        {:else if activeTab === 'episodios'}
          {#if loading}
            <p class="text-[13px] text-ink-secondary">Cargando…</p>
          {:else if selectedEpisodes.length === 0}
            <p class="text-[13px] text-ink-secondary">
              Sin episodios todavía para {selected.name}. Créalos desde Estudio ("Crear historia gobernada") o espera a que el Agente B produzca la parrilla automáticamente.
            </p>
          {:else}
            <div class="overflow-x-auto">
              <table class="w-full text-left text-[12.5px]">
                <thead>
                  <tr class="border-b border-line text-[10.5px] uppercase tracking-wide text-ink-tertiary">
                    <th class="pb-2 pr-4 font-medium">Título</th>
                    <th class="pb-2 pr-4 font-medium">Fecha</th>
                    <th class="pb-2 pr-4 font-medium">Duración</th>
                    <th class="pb-2 pr-4 font-medium">Generador / Crítico</th>
                    <th class="pb-2 font-medium">Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {#each selectedEpisodes as episode (episode.story_id)}
                    <tr class="border-b border-line-subtle">
                      <td class="py-2.5 pr-4 text-ink">{episode.title}</td>
                      <td class="py-2.5 pr-4 text-ink-tertiary">{formatDate(episode.created_at)}</td>
                      <td class="py-2.5 pr-4 text-ink-tertiary">{episode.duration_seconds ? `${Math.round(episode.duration_seconds)}s` : '—'}</td>
                      <td class="py-2.5 pr-4 font-mono text-ink-tertiary">{episode.generator_family ?? '—'} / {episode.critic_family ?? '—'}</td>
                      <td class="py-2.5">
                        <Badge tone={statusTone(episode)}>
                          {episode.narrative_passed && episode.originality_passed ? 'Aprobado' : 'Revisar'}
                        </Badge>
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {/if}
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
        class="overflow-hidden rounded-2xl border border-line bg-surface text-left transition-colors hover:border-purple-500"
        onclick={() => openProgram(program)}
      >
        <div class="flex items-center justify-between p-3" style={`background:${programGradient(program.program_id)}`}>
          <Badge tone="purple">{program.weekday}</Badge>
          <Badge tone="success">Activo</Badge>
        </div>
        <div class="p-4">
          <p class="font-display text-sm font-semibold text-ink">{program.name}</p>
          <p class="mt-1 text-[12px] text-ink-tertiary">{program.genre}</p>
          <p class="mt-3 text-[11.5px] leading-relaxed text-ink-secondary">{program.description}</p>
          <div class="mt-4 flex items-center justify-between text-[11px] text-ink-tertiary">
            <span>{episodeCountFor(program.program_id)} episodio{episodeCountFor(program.program_id) === 1 ? '' : 's'}</span>
            <span>{program.target_duration_seconds}s objetivo</span>
          </div>
        </div>
      </button>
    {/each}
  </div>
{/if}
