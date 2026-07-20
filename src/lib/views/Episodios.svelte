<script>
  import { onMount } from 'svelte';
  import Card from '../components/Card.svelte';
  import Badge from '../components/Badge.svelte';
  import { callOperations } from '../tauri-operations.js';

  let episodes = $state([]);
  let loadError = $state(false);
  let loading = $state(true);

  onMount(async () => {
    try {
      const response = await callOperations('episodes.list', { limit: 50 });
      episodes = response.episodes ?? [];
    } catch (error) {
      loadError = true;
    } finally {
      loading = false;
    }
  });

  function formatDate(unixSeconds) {
    if (!unixSeconds) return '—';
    return new Date(unixSeconds * 1000).toLocaleDateString('es', { year: 'numeric', month: 'short', day: 'numeric' });
  }

  function statusTone(episode) {
    if (episode.narrative_passed && episode.originality_passed) return 'success';
    if (episode.narrative_passed === false || episode.originality_passed === false) return 'error';
    return 'neutral';
  }
</script>

<Card title="Episodios" subtitle={`${episodes.length} episodio(s)`}>
  {#if loading}
    <p class="text-[13px] text-ink-secondary">Cargando…</p>
  {:else if loadError}
    <p class="text-[13px] text-ink-secondary">No se pudo cargar la lista de episodios. Abre Kronara desde la aplicación de escritorio.</p>
  {:else if episodes.length === 0}
    <p class="text-[13px] text-ink-secondary">
      Sin episodios todavía. Créalos desde Estudio ("Crear historia gobernada") o espera a que el Agente B produzca la parrilla automáticamente.
    </p>
  {:else}
    <div class="overflow-x-auto">
      <table class="w-full text-left text-[12.5px]">
        <thead>
          <tr class="border-b border-line text-[10.5px] uppercase tracking-wide text-ink-tertiary">
            <th class="pb-2 pr-4 font-medium">Título</th>
            <th class="pb-2 pr-4 font-medium">Programa</th>
            <th class="pb-2 pr-4 font-medium">Fecha</th>
            <th class="pb-2 pr-4 font-medium">Duración</th>
            <th class="pb-2 pr-4 font-medium">Generador / Crítico</th>
            <th class="pb-2 font-medium">Estado</th>
          </tr>
        </thead>
        <tbody>
          {#each episodes as episode (episode.story_id)}
            <tr class="border-b border-line-subtle">
              <td class="py-2.5 pr-4 text-ink">{episode.title}</td>
              <td class="py-2.5 pr-4 text-ink-secondary">{episode.program_id ?? '—'}</td>
              <td class="py-2.5 pr-4 text-ink-tertiary">{formatDate(episode.created_at)}</td>
              <td class="py-2.5 pr-4 text-ink-tertiary">{episode.duration_seconds ? `${Math.round(episode.duration_seconds)}s` : '—'}</td>
              <td class="py-2.5 pr-4 text-ink-tertiary">{episode.generator_family ?? '—'} / {episode.critic_family ?? '—'}</td>
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
</Card>
