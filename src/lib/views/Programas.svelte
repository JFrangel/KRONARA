<script>
  import { onMount } from 'svelte';
  import Card from '../components/Card.svelte';
  import Badge from '../components/Badge.svelte';
  import Icon from '../components/Icon.svelte';
  import { assetSrc, callOperations } from '../tauri-operations.js';
  import { programGradient } from '../programArt.js';

  let { connection = 'disconnected' } = $props();

  let programs = $state([]);
  let episodes = $state([]);
  let loadError = $state(false);
  let loading = $state(true);
  let selected = $state(null);
  let activeTab = $state('resumen');
  let creating = $state(false);
  let createNotice = $state('');
  let selectedEpisodeId = $state(null);

  // Episodios lives here rather than as its own top-level section -- every
  // episode belongs to exactly one program, so browsing them detached from
  // that program threw away the one grouping that actually matters.
  const TABS = ['resumen', 'episodios', 'calendario', 'personajes', 'configuracion', 'analiticas', 'recursos'];
  const TAB_LABELS = {
    resumen: 'Resumen', episodios: 'Episodios', calendario: 'Calendario', personajes: 'Personajes',
    configuracion: 'Configuración', analiticas: 'Analíticas', recursos: 'Recursos',
  };
  const WEEKDAY_LABELS = {
    monday: 'lunes', tuesday: 'martes', wednesday: 'miércoles', thursday: 'jueves',
    friday: 'viernes', saturday: 'sábado', sunday: 'domingo',
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
    createNotice = '';
    selectedEpisodeId = null;
  }

  async function createEpisode() {
    if (creating || connection !== 'connected' || !selected) return;
    creating = true;
    createNotice = '';
    const programId = selected.program_id;
    try {
      const result = await callOperations('content.run', {
        program_id: programId,
        story_id: `owned_ui_${Date.now()}`,
      });
      if (result.status === 'completed') {
        createNotice = `Episodio creado: "${result.story?.title ?? result.run_id}".`;
        activeTab = 'episodios';
        const refreshed = await callOperations('episodes.list', { limit: 200 });
        episodes = refreshed.episodes ?? episodes;
        const created = episodes.find((episode) => episode.program_id === programId);
        selectedEpisodeId = created?.story_id ?? null;
      } else {
        createNotice = `No se pudo completar el episodio (${result.error_code ?? result.status}). El vertical no publica nada a menos que Reddit, los modelos, los derechos y la calidad pasen todas las validaciones.`;
      }
    } catch (error) {
      createNotice = 'Falló la creación del episodio. Revisa la conexión con el sidecar.';
    } finally {
      creating = false;
    }
  }

  function episodesFor(programId) {
    return episodes.filter((episode) => episode.program_id === programId);
  }

  function episodeCountFor(programId) {
    return episodesFor(programId).length;
  }

  function coverFor(programId) {
    const withCover = episodesFor(programId).find((episode) => episode.cover_image_path);
    return withCover ? assetSrc(withCover.cover_image_path) : null;
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

  function selectEpisode(episode) {
    selectedEpisodeId = episode.story_id;
  }

  const selectedEpisodes = $derived(selected ? episodesFor(selected.program_id) : []);
  const selectedEpisode = $derived(
    selectedEpisodes.find((episode) => episode.story_id === selectedEpisodeId)
      ?? selectedEpisodes[0]
      ?? null
  );
</script>

{#if loadError}
  <p class="text-[13px] text-ink-secondary">No se pudo cargar la parrilla de programas. Abre Kronara desde la aplicación de escritorio.</p>
{:else if selected}
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <button class="flex items-center gap-1.5 text-[12.5px] text-ink-tertiary hover:text-ink" onclick={() => (selected = null)}>
        <Icon name="chevron-left" size={14} /> Programas
      </button>
      <button
        class="flex items-center gap-1.5 rounded-full bg-purple-500 px-4 py-2 text-[12.5px] font-medium text-ink hover:bg-purple-600 disabled:cursor-not-allowed disabled:opacity-40"
        onclick={createEpisode}
        disabled={creating || connection !== 'connected'}
      >
        <Icon name="plus" size={14} />
        {creating ? 'Creando episodio… (puede tardar varios minutos)' : 'Crear episodio'}
      </button>
    </div>

    {#if createNotice}
      <p class="rounded-lg border border-line bg-surface-inset px-3 py-2 text-[12.5px] text-ink-secondary">{createNotice}</p>
    {/if}

    <Card>
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div class="flex items-start gap-3.5">
          {#if coverFor(selected.program_id)}
            <img src={coverFor(selected.program_id)} alt="" class="h-14 w-14 shrink-0 rounded-xl object-cover" />
          {:else}
            <span
              class="grid h-14 w-14 shrink-0 place-items-center rounded-xl font-display text-lg font-bold text-ink"
              style={`background:${programGradient(selected.program_id)}`}
            >{selected.name.charAt(0)}</span>
          {/if}
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
                    <th class="pb-2 pr-4 font-medium">Episodio</th>
                    <th class="pb-2 pr-4 font-medium">Fecha</th>
                    <th class="pb-2 pr-4 font-medium">Duración</th>
                    <th class="pb-2 pr-4 font-medium">Generador / Crítico</th>
                    <th class="pb-2 font-medium">Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {#each selectedEpisodes as episode (episode.story_id)}
                    <tr
                      class="cursor-pointer border-b border-line-subtle transition-colors hover:bg-surface-inset"
                      class:bg-surface-inset={selectedEpisode?.story_id === episode.story_id}
                      onclick={() => selectEpisode(episode)}
                    >
                      <td class="py-2.5 pr-4 text-ink">
                        <div class="flex items-center gap-2.5">
                          {#if assetSrc(episode.cover_image_path)}
                            <img src={assetSrc(episode.cover_image_path)} alt="" class="h-9 w-9 shrink-0 rounded-lg object-cover" />
                          {:else}
                            <span class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-surface-inset text-ink-tertiary">
                              <Icon name="film" size={14} />
                            </span>
                          {/if}
                          <span class="truncate">{episode.title}</span>
                        </div>
                      </td>
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
        {:else if activeTab === 'calendario'}
          <div class="space-y-3">
            <div class="rounded-lg border border-line bg-surface-inset p-3">
              <p class="text-[11px] text-ink-tertiary">Horario recurrente</p>
              <p class="mt-1 text-[13px] capitalize text-ink">Cada {WEEKDAY_LABELS[selected.weekday] ?? selected.weekday}, vía la parrilla automática (Agente B).</p>
            </div>
            {#if selectedEpisodes.length === 0}
              <p class="text-[13px] text-ink-secondary">Sin episodios todavía -- aquí aparecerá la fecha de cada uno en cuanto se creen.</p>
            {:else}
              <ul class="space-y-2">
                {#each selectedEpisodes as episode (episode.story_id)}
                  <li class="flex items-center justify-between rounded-lg border border-line bg-surface-inset px-3 py-2.5 text-[12.5px]">
                    <span class="text-ink">{episode.title}</span>
                    <span class="text-ink-tertiary">{formatDate(episode.created_at)}</span>
                  </li>
                {/each}
              </ul>
            {/if}
          </div>
        {:else if activeTab === 'configuracion'}
          <dl class="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div class="rounded-lg border border-line bg-surface-inset p-3">
              <dt class="text-[10.5px] text-ink-tertiary">program_id</dt>
              <dd class="mt-1 font-mono text-[12.5px] text-ink">{selected.program_id}</dd>
            </div>
            <div class="rounded-lg border border-line bg-surface-inset p-3">
              <dt class="text-[10.5px] text-ink-tertiary">Estilo visual</dt>
              <dd class="mt-1 font-mono text-[12.5px] text-ink">{selected.visual_style_id}</dd>
            </div>
            <div class="rounded-lg border border-line bg-surface-inset p-3">
              <dt class="text-[10.5px] text-ink-tertiary">Duración objetivo</dt>
              <dd class="mt-1 text-[12.5px] text-ink">{selected.target_duration_seconds} segundos</dd>
            </div>
            <div class="rounded-lg border border-line bg-surface-inset p-3">
              <dt class="text-[10.5px] text-ink-tertiary">Día de publicación</dt>
              <dd class="mt-1 text-[12.5px] capitalize text-ink">{selected.weekday}</dd>
            </div>
          </dl>
          <p class="mt-3 text-[11.5px] text-ink-tertiary">Editar estos valores hoy requiere cambiar <code class="text-purple-300">config/programs/programs.v1.json</code> directamente; un formulario aquí queda pendiente.</p>
        {:else if activeTab === 'personajes'}
          <p class="text-[13px] text-ink-secondary">La consistencia de personajes (misma cara/semilla entre escenas y partes de una serie) está construida y probada en <code class="text-purple-300">character_visual.py</code>, pero todavía no está conectada al pipeline de producción real -- por ahora cada imagen se genera desde cero por escena.</p>
        {:else if activeTab === 'analiticas'}
          <p class="text-[13px] text-ink-secondary">Reproducciones, retención y suscriptores de {selected.name} aparecerán aquí en cuanto Kronara Pulse pueda leer métricas reales de las plataformas conectadas. Hoy no hay ninguna cuenta de YouTube/Spotify/Meta enlazada, así que no hay nada real que mostrar todavía.</p>
        {:else if activeTab === 'recursos'}
          <p class="text-[13px] text-ink-secondary">La biblioteca de música/SFX/video de apoyo (<code class="text-purple-300">asset_library.py</code>) ya existe y alimenta el render real, pero todavía no hay un método RPC para listarla desde la interfaz.</p>
        {/if}
      </Card>
      <div class="space-y-4">
        {#if activeTab === 'episodios' && selectedEpisode}
          <Card title="Episodio seleccionado">
            {#if assetSrc(selectedEpisode.video_path)}
              <!-- svelte-ignore a11y_media_has_caption -->
              <video
                src={assetSrc(selectedEpisode.video_path)}
                poster={assetSrc(selectedEpisode.cover_image_path) ?? undefined}
                controls
                class="w-full rounded-lg bg-black"
              ></video>
            {:else if assetSrc(selectedEpisode.cover_image_path)}
              <img src={assetSrc(selectedEpisode.cover_image_path)} alt="" class="w-full rounded-lg object-cover" />
            {:else}
              <div class="grid aspect-video place-items-center rounded-lg bg-surface-inset text-ink-tertiary">
                <Icon name="film" size={22} />
              </div>
            {/if}
            <p class="mt-3 font-display text-[13px] font-semibold text-ink">{selectedEpisode.title}</p>
            <dl class="mt-2 grid grid-cols-2 gap-2 text-[11.5px]">
              <div><dt class="text-ink-tertiary">Duración</dt><dd class="text-ink">{selectedEpisode.duration_seconds ? `${Math.round(selectedEpisode.duration_seconds)}s` : '—'}</dd></div>
              <div><dt class="text-ink-tertiary">Video</dt><dd class="text-ink">{selectedEpisode.video_status ?? 'no_configurado'}</dd></div>
            </dl>
            {#if selectedEpisode.video_status && selectedEpisode.video_status !== 'completed' && selectedEpisode.video_status !== 'not_configured'}
              <p class="mt-2 text-[11px] text-ink-tertiary">Estado del video: {selectedEpisode.video_status}{selectedEpisode.video_qc_passed === false ? ' (QC con problemas)' : ''}.</p>
            {/if}
          </Card>
        {:else}
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
        {/if}
      </div>
    </div>
  </div>
{:else}
  <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
    {#each programs as program (program.program_id)}
      {@const cover = coverFor(program.program_id)}
      <button
        class="overflow-hidden rounded-2xl border border-line bg-surface text-left transition-colors hover:border-purple-500"
        onclick={() => openProgram(program)}
      >
        <div class="relative flex items-center justify-between overflow-hidden p-3" style={`background:${programGradient(program.program_id)}`}>
          {#if cover}
            <img src={cover} alt="" class="absolute inset-0 h-full w-full object-cover" loading="lazy" />
            <div class="absolute inset-0 bg-black/35"></div>
          {/if}
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
