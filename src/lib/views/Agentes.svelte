<script>
  import { onMount } from 'svelte';
  import { fly } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import Card from '../components/Card.svelte';
  import Badge from '../components/Badge.svelte';
  import Icon from '../components/Icon.svelte';
  import Skeleton from '../components/Skeleton.svelte';
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
  <div class="flex items-start gap-3 rounded-2xl border border-purple-500/25 bg-gradient-to-br from-purple-500/12 to-purple-500/[0.04] p-4">
    <div class="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-purple-500/15 text-purple-300 ring-1 ring-inset ring-purple-500/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
      <Icon name="cpu" size={20} />
    </div>
    <div>
      <p class="flex flex-wrap items-center gap-2 font-display text-[15px] font-medium text-ink">
        Tres super-agentes
        <Badge tone="purple">clase Agente B</Badge>
      </p>
      <p class="mt-1 text-[12px] leading-relaxed text-ink-secondary">
        Kronara consolidó 24 agentes especializados en 3 super-nodos más capaces. Cada corrida real emite solo estos tres; cada uno absorbe las funciones que ves abajo.
      </p>
    </div>
  </div>

  {#if loadError}
    <Card>
      <div class="flex items-start gap-3">
        <div class="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-error/12 text-error"><Icon name="alert-triangle" size={18} /></div>
        <p class="text-[13px] text-ink-secondary">No se pudo cargar. Inicia la web local y verifica que Python esté conectado.</p>
      </div>
    </Card>
  {:else if !loaded}
    <div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
      {#each Array(3) as _, i}
        <Card>
          <div class="mb-4 kronara-skeleton h-9 w-9 rounded-xl"></div>
          <Skeleton lines={5} />
        </Card>
      {/each}
    </div>
  {:else}
    <div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
      {#each agents as agent, i (agent.id)}
        <div in:fly={{ y: 12, duration: 380, delay: i * 90, easing: cubicOut }}>
          <Card class="group h-full transition duration-300 hover:-translate-y-1 hover:border-purple-500/40 hover:shadow-[0_24px_60px_rgba(123,92,255,0.14)]">
            <div class="flex items-center gap-2">
              <div class="grid h-9 w-9 place-items-center rounded-xl bg-purple-500/15 text-purple-300 ring-1 ring-inset ring-purple-500/20 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] transition-all group-hover:bg-purple-500/25 group-hover:ring-purple-400/40"><Icon name={ICONS[agent.id] ?? 'cpu'} size={20} /></div>
              <span class="font-mono text-[11px] text-ink-tertiary">{agent.id}</span>
              {#if agent.absorbs?.length}<Badge tone="purple">absorbe {agent.absorbs.length}</Badge>{/if}
            </div>
            <div class="mt-3">
              <p class="font-mono text-[10px] uppercase tracking-[0.14em] text-purple-300/70">{agent.role}</p>
              <p class="mt-1 font-display text-[19px] leading-tight text-ink">{agent.name}</p>
            </div>
            <p class="mt-3 text-[12px] leading-relaxed text-ink-secondary">{agent.description}</p>
            {#if agent.capabilities?.length}
              <ul class="mt-3 space-y-1.5">
                {#each agent.capabilities as cap}
                  <li class="group/cap -mx-1.5 flex items-center gap-2 rounded-md px-1.5 py-0.5 text-[11.5px] text-ink transition-colors hover:bg-purple-500/[0.06]">
                    <span class="h-1.5 w-1.5 shrink-0 rounded-full bg-purple-500 ring-2 ring-purple-500/15"></span>{cap}
                  </li>
                {/each}
              </ul>
            {/if}
            {#if agent.absorbs?.length}
              <details class="group/abs mt-3 rounded-lg border border-line bg-surface-inset p-2.5">
                <summary class="flex cursor-pointer list-none items-center justify-between text-[11px] text-ink-tertiary [&::-webkit-details-marker]:hidden">
                  <span>Funciones absorbidas ({agent.absorbs.length})</span>
                  <Icon name="chevron-down" size={14} class="transition-transform duration-200 group-open/abs:rotate-180" />
                </summary>
                <div class="mt-2 flex flex-wrap gap-1.5">
                  {#each agent.absorbs as legacy}
                    <span class="rounded-md border border-line px-2 py-0.5 font-mono text-[10px] text-ink-tertiary transition-colors hover:border-purple-500/30">{legacy}</span>
                  {/each}
                </div>
              </details>
            {/if}
          </Card>
        </div>
      {/each}
    </div>
  {/if}
</div>
