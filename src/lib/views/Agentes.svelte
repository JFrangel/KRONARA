<script>
  import { onMount } from 'svelte';
  import Card from '../components/Card.svelte';
  import Badge from '../components/Badge.svelte';
  import Icon from '../components/Icon.svelte';
  import { callOperations } from '../local-operations.js';

  let agents = $state([]);
  let loaded = $state(false);
  let loadError = $state(false);

  onMount(async () => {
    try {
      const result = await callOperations('agents.overview', {});
      agents = result.agents ?? [];
    } catch (error) {
      loadError = true;
    } finally {
      loaded = true;
    }
  });

  const ICONS = { estratega: 'search', guionista: 'wand', productor: 'film' };
</script>

<div class="space-y-4">
  <div class="rounded-xl border border-purple-500/25 bg-purple-500/10 p-4">
    <p class="text-[13px] font-medium text-ink">Tres super-agentes (clase Agente B)</p>
    <p class="mt-1 text-[12px] leading-relaxed text-ink-secondary">
      Kronara consolidó 24 agentes especializados en 3 super-nodos más capaces. Cada corrida real emite solo estos tres; cada uno absorbe las funciones que ves abajo.
    </p>
  </div>

  {#if loadError}
    <Card title="Agentes">
      <p class="text-[13px] text-ink-secondary">No se pudo cargar. Inicia la web local y verifica que Python esté conectado.</p>
    </Card>
  {:else if !loaded}
    <Card title="Agentes"><p class="text-[13px] text-ink-secondary">Cargando…</p></Card>
  {:else}
    <div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
      {#each agents as agent (agent.id)}
        <Card title={agent.name} subtitle={agent.role}>
          <div class="flex items-center gap-2">
            <div class="grid h-9 w-9 place-items-center rounded-xl bg-purple-500/15 text-purple-300"><Icon name={ICONS[agent.id] ?? 'cpu'} size={18} /></div>
            <span class="font-mono text-[11px] text-ink-tertiary">{agent.id}</span>
            {#if agent.absorbs?.length}<Badge tone="neutral">absorbe {agent.absorbs.length}</Badge>{/if}
          </div>
          <p class="mt-3 text-[12px] leading-relaxed text-ink-secondary">{agent.description}</p>
          {#if agent.capabilities?.length}
            <ul class="mt-3 space-y-1.5">
              {#each agent.capabilities as cap}
                <li class="flex items-center gap-2 text-[11.5px] text-ink">
                  <span class="h-1.5 w-1.5 shrink-0 rounded-full bg-purple-500"></span>{cap}
                </li>
              {/each}
            </ul>
          {/if}
          {#if agent.absorbs?.length}
            <details class="mt-3 rounded-lg border border-line bg-surface-inset p-2.5">
              <summary class="cursor-pointer text-[11px] text-ink-tertiary">Funciones absorbidas ({agent.absorbs.length})</summary>
              <div class="mt-2 flex flex-wrap gap-1.5">
                {#each agent.absorbs as legacy}
                  <span class="rounded-md border border-line px-2 py-0.5 font-mono text-[10px] text-ink-tertiary">{legacy}</span>
                {/each}
              </div>
            </details>
          {/if}
        </Card>
      {/each}
    </div>
  {/if}
</div>
