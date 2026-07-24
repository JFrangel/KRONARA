<script>
  import { onMount } from 'svelte';
  import { fly, fade, slide } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import Card from '../components/Card.svelte';
  import Badge from '../components/Badge.svelte';
  import Icon from '../components/Icon.svelte';
  import { assetSrc, callOperations } from '../local-operations.js';

  let { operations = {} } = $props();

  let episodes = $state([]);
  let programs = $state([]);
  let loading = $state(true);
  let loadError = $state(false);
  let selectedTab = $state('episodios');
  let selectedProgramFilter = $state('all');
  let selectedEpisodeDetail = $state(null);

  const TABS = ['episodios', 'imagenes', 'voces', 'guiones', 'musica-sfx'];
  const TAB_LABELS = {
    episodios: 'Episodios',
    imagenes: 'Imágenes',
    voces: 'Voces',
    guiones: 'Guiones',
    'musica-sfx': 'Música y SFX',
  };
  const TAB_ICONS = {
    episodios: 'film',
    imagenes: 'wand',
    voces: 'clock',
    guiones: 'list',
    'musica-sfx': 'wand',
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

  const filteredEpisodes = $derived(
    selectedProgramFilter === 'all'
      ? episodes
      : episodes.filter((ep) => ep.program_id === selectedProgramFilter)
  );

  // Group all generated images by program, sourced from every episode's
  // cover + any images metadata surfaced by the pipeline. Since episode
  // metadata carries cover_image_path and video_source_kind_counts, we
  // treat cover as the primary preview per episode -- listing every shot
  // individually would require a new RPC (episode.list_shots) which is
  // Fase D scope, not this Biblioteca skeleton.
  const allImages = $derived(
    filteredEpisodes
      .filter((ep) => ep.cover_image_path)
      .map((ep) => ({
        path: ep.cover_image_path,
        program_id: ep.program_id,
        episode_title: ep.title,
        episode_id: ep.story_id,
      }))
  );

  const allVoices = $derived(
    filteredEpisodes.filter((ep) => ep.video_path)
  );

  const totalDurationMinutes = $derived(
    Math.round(episodes.reduce((acc, ep) => acc + (ep.duration_seconds ?? 0), 0) / 60)
  );

  async function loadEpisodeDetail(storyId) {
    if (selectedEpisodeDetail?.story_id === storyId) {
      selectedEpisodeDetail = null;
      return;
    }
    try {
      selectedEpisodeDetail = await callOperations('episodes.get', { story_id: storyId });
    } catch (error) {
      selectedEpisodeDetail = null;
    }
  }

  function formatDate(unixSeconds) {
    if (!unixSeconds) return '—';
    return new Date(unixSeconds * 1000).toLocaleDateString('es', { year: 'numeric', month: 'short', day: 'numeric' });
  }

  function programName(programId) {
    return programs.find((p) => p.program_id === programId)?.name ?? programId ?? '—';
  }

  // Etiquetas legibles para las señales estructuradas del episodio (#103).
  const CONTENT_KIND_LABELS = {
    narrative_story: 'Historia',
    reflection: 'Reflexión',
    scripture: 'Bíblico',
    quote: 'Frase',
  };
  const SOURCE_KIND_LABELS = {
    generated_image: 'Imagen IA',
    ken_burns: 'Ken Burns',
    stock_loop: 'Loop stock',
    i2v: 'Generativo i2v',
    placeholder: 'Placeholder',
  };

  function assetBasename(path) {
    if (!path) return '—';
    const parts = String(path).split(/[\\/]/);
    return parts[parts.length - 1] || path;
  }
</script>

<div class="space-y-4">
  <header class="flex flex-wrap items-end justify-between gap-3">
    <div>
      <h1 class="font-display text-xl font-semibold text-ink">Biblioteca local</h1>
      <p class="mt-1 text-[12.5px] text-ink-secondary">
        Todo lo generado en este equipo: episodios completos, portadas, guiones, narración, música y SFX. Cada archivo real vive en <code class="text-purple-300">.kronara/runtime/artifacts</code> y aparece aquí en cuanto se guarda.
      </p>
    </div>
    <div class="flex gap-3 text-right">
      <div class="rounded-xl border border-line bg-gradient-to-br from-surface to-surface-inset px-3.5 py-2.5 shadow-card">
        <p class="text-[10.5px] uppercase tracking-wide text-ink-tertiary">Episodios</p>
        <p class="font-display text-lg font-semibold tabular-nums text-ink">{episodes.length}</p>
      </div>
      <div class="rounded-xl border border-line bg-gradient-to-br from-surface to-surface-inset px-3.5 py-2.5 shadow-card">
        <p class="text-[10.5px] uppercase tracking-wide text-ink-tertiary">Programas</p>
        <p class="font-display text-lg font-semibold tabular-nums text-ink">{programs.length}</p>
      </div>
      <div class="rounded-xl border border-line bg-gradient-to-br from-surface to-surface-inset px-3.5 py-2.5 shadow-card">
        <p class="text-[10.5px] uppercase tracking-wide text-ink-tertiary">Minutos totales</p>
        <p class="font-display text-lg font-semibold tabular-nums text-ink">{totalDurationMinutes}</p>
      </div>
    </div>
  </header>

  {#if loadError}
    <p class="text-[13px] text-error">No se pudo leer la biblioteca. Revisa la conexión con el backend local.</p>
  {:else}
    <div class="flex flex-wrap gap-3">
      <div class="flex gap-1 rounded-full border border-line bg-surface p-1">
        {#each TABS as tab}
          <button
            class={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] font-medium transition ${selectedTab === tab ? 'bg-purple-500 text-ink shadow-[0_2px_12px_rgba(123,92,255,0.35)]' : 'text-ink-tertiary hover:bg-surface-hover hover:text-ink'}`}
            onclick={() => (selectedTab = tab)}
          >
            <Icon name={TAB_ICONS[tab]} size={13} />
            {TAB_LABELS[tab]}
          </button>
        {/each}
      </div>

      <select
        class="rounded-full border border-line bg-surface px-3 py-1.5 text-[12px] text-ink focus:border-purple-500 focus:outline-none"
        bind:value={selectedProgramFilter}
      >
        <option value="all">Todos los programas</option>
        {#each programs as program}
          <option value={program.program_id}>{program.name}</option>
        {/each}
      </select>
    </div>

    {#if loading}
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {#each Array(8) as _}
          <div class="overflow-hidden rounded-xl border border-line bg-surface">
            <span class="kronara-skeleton block aspect-[9/16] w-full"></span>
            <div class="space-y-2 p-3">
              <span class="kronara-skeleton block h-3 w-3/4 rounded-full"></span>
              <span class="kronara-skeleton block h-3 w-1/2 rounded-full"></span>
            </div>
          </div>
        {/each}
      </div>
    {:else if selectedTab === 'episodios'}
      {#if filteredEpisodes.length === 0}
        <Card>
          <p class="text-[13px] text-ink-secondary">
            No hay episodios guardados todavía{selectedProgramFilter !== 'all' ? ' para este programa' : ''}. Crea el primero desde Programas → Crear episodio.
          </p>
        </Card>
      {:else}
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {#each filteredEpisodes as episode, i}
            <button
              class="group flex flex-col overflow-hidden rounded-xl border border-line bg-gradient-to-br from-surface to-surface-inset text-left shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:border-purple-500/70 hover:shadow-card-hover"
              onclick={() => loadEpisodeDetail(episode.story_id)}
              in:fly={{ y: 10, duration: 260, delay: Math.min(i, 12) * 28, easing: cubicOut }}
            >
              <div class="relative overflow-hidden">
                {#if episode.cover_image_path && assetSrc(episode.cover_image_path)}
                  <img
                    src={assetSrc(episode.cover_image_path)}
                    alt={episode.title}
                    class="aspect-[9/16] w-full object-cover transition-transform duration-500 ease-out group-hover:scale-[1.04]"
                    loading="lazy"
                  />
                {:else}
                  <div class="grid aspect-[9/16] w-full place-items-center bg-surface-inset text-ink-tertiary">
                    <Icon name="film" size={32} />
                  </div>
                {/if}
                <div class="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-black/55 to-transparent"></div>
                {#if episode.video_qc_passed === true}
                  <span class="absolute right-2 top-2 rounded-full bg-black/45 px-2 py-0.5 font-mono text-[10px] text-success backdrop-blur-sm">QC ✓</span>
                {:else if episode.video_qc_passed === false}
                  <span class="absolute right-2 top-2 rounded-full bg-black/45 px-2 py-0.5 font-mono text-[10px] text-error backdrop-blur-sm">QC ✗</span>
                {/if}
                {#if episode.duration_seconds}
                  <span class="absolute bottom-2 left-2 rounded-full bg-black/45 px-2 py-0.5 font-mono text-[10px] tabular-nums text-ink backdrop-blur-sm">{Math.round(episode.duration_seconds)}s</span>
                {/if}
              </div>
              <div class="p-3">
                <p class="line-clamp-2 font-display text-[13px] font-semibold text-ink">{episode.title}</p>
                <p class="mt-1 text-[11px] text-ink-tertiary">{programName(episode.program_id)}</p>
                <p class="mt-1 font-mono text-[10.5px] tabular-nums text-ink-tertiary">{formatDate(episode.created_at)}</p>
              </div>
            </button>
          {/each}
        </div>

        {#if selectedEpisodeDetail}
          <Card title={selectedEpisodeDetail.title ?? 'Episodio'} subtitle={programName(selectedEpisodeDetail.program_id)}>
            {#if selectedEpisodeDetail.video_path && assetSrc(selectedEpisodeDetail.video_path)}
              <!-- svelte-ignore a11y_media_has_caption -->
              <video
                controls
                preload="metadata"
                playsinline
                poster={assetSrc(selectedEpisodeDetail.cover_image_path) ?? undefined}
                src={assetSrc(selectedEpisodeDetail.video_path)}
                class="mb-3 w-full rounded-lg bg-black"
              ></video>
            {/if}
            {#if selectedEpisodeDetail.hook}
              <p class="text-[13px] italic text-ink-secondary">"{selectedEpisodeDetail.hook}"</p>
            {/if}
            {#if selectedEpisodeDetail.script}
              <div class="mt-3 max-h-64 overflow-y-auto rounded-lg border border-line bg-surface-inset p-3">
                <p class="whitespace-pre-wrap text-[12.5px] leading-relaxed text-ink">{selectedEpisodeDetail.script}</p>
              </div>
            {/if}
            <div class="mt-3 flex flex-wrap gap-1.5">
              {#if selectedEpisodeDetail.content_kind}
                <Badge tone="purple">{CONTENT_KIND_LABELS[selectedEpisodeDetail.content_kind] ?? selectedEpisodeDetail.content_kind}</Badge>
              {/if}
              {#if selectedEpisodeDetail.style_id}
                <Badge tone="info">Estilo · {selectedEpisodeDetail.style_id}</Badge>
              {/if}
              {#each Object.entries(selectedEpisodeDetail.video_source_kind_counts ?? {}) as [kind, count]}
                <Badge tone="neutral">{SOURCE_KIND_LABELS[kind] ?? kind}: {count}</Badge>
              {/each}
            </div>
            <dl class="mt-3 grid grid-cols-2 gap-2 text-[11.5px] sm:grid-cols-4">
              <div>
                <dt class="text-ink-tertiary">Generador</dt>
                <dd class="mt-0.5 font-mono text-ink">{selectedEpisodeDetail.generator_family ?? '—'}</dd>
              </div>
              <div>
                <dt class="text-ink-tertiary">Crítico</dt>
                <dd class="mt-0.5 font-mono text-ink">{selectedEpisodeDetail.critic_family ?? '—'}</dd>
              </div>
              <div>
                <dt class="text-ink-tertiary">Escenas</dt>
                <dd class="mt-0.5 text-ink">{selectedEpisodeDetail.video_scene_count ?? '—'}</dd>
              </div>
              <div>
                <dt class="text-ink-tertiary">Tomas</dt>
                <dd class="mt-0.5 text-ink">{selectedEpisodeDetail.video_shot_count ?? '—'}</dd>
              </div>
            </dl>
            {#if selectedEpisodeDetail.scene_manifest?.length}
              <div class="mt-3">
                <p class="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-tertiary">Recursos por escena</p>
                <ul class="mt-1.5 divide-y divide-line-subtle rounded-lg border border-line bg-surface-inset">
                  {#each selectedEpisodeDetail.scene_manifest as asset}
                    <li class="flex items-center justify-between gap-2 px-3 py-2 text-[11.5px]">
                      <span class="flex items-center gap-2 min-w-0">
                        <span class="shrink-0 rounded bg-surface px-1.5 py-0.5 font-mono text-[10.5px] text-ink-tertiary">#{asset.scene_index}</span>
                        <span class="truncate font-mono text-ink-secondary">{assetBasename(asset.asset_path)}</span>
                      </span>
                      <span class="flex shrink-0 items-center gap-1.5">
                        <Badge tone="neutral">{SOURCE_KIND_LABELS[asset.source_kind] ?? asset.source_kind}</Badge>
                        {#if asset.duration_ms}<span class="text-ink-tertiary">{Math.round(asset.duration_ms / 1000)}s</span>{/if}
                      </span>
                    </li>
                  {/each}
                </ul>
              </div>
            {/if}
          </Card>
        {/if}
      {/if}
    {:else if selectedTab === 'imagenes'}
      {#if allImages.length === 0}
        <Card>
          <p class="text-[13px] text-ink-secondary">No hay imágenes guardadas todavía. Cada episodio genera al menos una portada.</p>
        </Card>
      {:else}
        <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
          {#each allImages as image}
            <a
              href={assetSrc(image.path)}
              target="_blank"
              rel="noopener"
              class="group overflow-hidden rounded-lg border border-line bg-surface transition hover:border-purple-500"
              title={image.episode_title}
            >
              <img
                src={assetSrc(image.path)}
                alt={image.episode_title}
                class="aspect-[9/16] w-full object-cover transition group-hover:scale-105"
                loading="lazy"
              />
              <div class="p-2">
                <p class="line-clamp-1 text-[10.5px] text-ink-tertiary">{programName(image.program_id)}</p>
              </div>
            </a>
          {/each}
        </div>
        <p class="text-[11.5px] text-ink-tertiary">
          {allImages.length} portada(s) generada(s). El listado completo de tomas por escena llega en la Fase D (pestañas de Estudio).
        </p>
      {/if}
    {:else if selectedTab === 'voces'}
      {#if allVoices.length === 0}
        <Card>
          <p class="text-[13px] text-ink-secondary">Ningún episodio tiene audio de narración guardado todavía.</p>
        </Card>
      {:else}
        <div class="space-y-2">
          {#each allVoices as episode}
            <Card>
              <div class="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p class="font-display text-[13px] font-semibold text-ink">{episode.title}</p>
                  <p class="text-[11.5px] text-ink-tertiary">{programName(episode.program_id)} · {Math.round(episode.duration_seconds ?? 0)}s</p>
                </div>
              </div>
              {#if episode.video_path && assetSrc(episode.video_path)}
                <!-- svelte-ignore a11y_media_has_caption -->
                <video controls preload="metadata" class="mt-2 w-full rounded-lg bg-black" src={assetSrc(episode.video_path)}></video>
              {/if}
            </Card>
          {/each}
        </div>
      {/if}
    {:else if selectedTab === 'guiones'}
      {#if filteredEpisodes.length === 0}
        <Card>
          <p class="text-[13px] text-ink-secondary">Aún no hay guiones guardados.</p>
        </Card>
      {:else}
        <div class="space-y-3">
          {#each filteredEpisodes as episode}
            <Card>
              <div class="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p class="font-display text-[13px] font-semibold text-ink">{episode.title}</p>
                  <p class="text-[11px] text-ink-tertiary">{programName(episode.program_id)} · {formatDate(episode.created_at)}</p>
                </div>
                <button
                  class="rounded-lg border border-line px-3 py-1.5 text-[11.5px] text-ink-tertiary transition hover:border-purple-500 hover:text-ink"
                  onclick={() => loadEpisodeDetail(episode.story_id)}
                >
                  {selectedEpisodeDetail?.story_id === episode.story_id ? 'Ocultar guion' : 'Ver guion'}
                </button>
              </div>
              {#if selectedEpisodeDetail?.story_id === episode.story_id && selectedEpisodeDetail?.script}
                <div class="mt-3 max-h-80 overflow-y-auto rounded-lg border border-line bg-surface-inset p-3">
                  <p class="whitespace-pre-wrap text-[12.5px] leading-relaxed text-ink">{selectedEpisodeDetail.script}</p>
                </div>
              {/if}
            </Card>
          {/each}
        </div>
      {/if}
    {:else if selectedTab === 'musica-sfx'}
      <Card>
        <div class="flex items-start gap-3">
          <span class="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-surface-inset text-purple-300">
            <Icon name="wand" size={18} />
          </span>
          <div>
            <p class="font-display text-[13px] font-semibold text-ink">Biblioteca de música y SFX</p>
            <p class="mt-1 text-[12.5px] text-ink-secondary">
              La cosecha real desde Freesound y Pexels (FASE V7) todavía no está conectada. Los scripts existen en <code class="text-purple-300">scripts/harvest_freesound.py</code> y <code class="text-purple-300">scripts/harvest_pexels.py</code>, pero la biblioteca (<code class="text-purple-300">asset_library.db</code>) está vacía hoy. Cuando se pueble, cada pista aparecerá acá con su duración, mood, licencia y en qué episodios se ha usado.
            </p>
          </div>
        </div>
      </Card>
    {/if}
  {/if}
</div>
