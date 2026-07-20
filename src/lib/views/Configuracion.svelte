<script>
  import { onMount } from 'svelte';
  import Card from '../components/Card.svelte';
  import Badge from '../components/Badge.svelte';
  import { callOperations } from '../tauri-operations.js';

  const TABS = ['general', 'ia', 'voces', 'publicacion', 'almacenamiento', 'seguridad'];
  const TAB_LABELS = {
    general: 'General', ia: 'IA y modelos', voces: 'Voces', publicacion: 'Publicación',
    almacenamiento: 'Almacenamiento', seguridad: 'Seguridad',
  };

  let activeTab = $state('ia');
  let context = $state(null);
  let loadError = $state(false);

  onMount(async () => {
    try {
      context = await callOperations('operations.context', {});
    } catch (error) {
      loadError = true;
    }
  });

  const PROVIDERS = [
    { id: 'openrouter', label: 'OpenRouter (Qwen / Kimi / Nemotron / Hy3)', envVar: 'KRONARA_OPENROUTER_API_KEY' },
    { id: 'groq', label: 'Groq', envVar: 'KRONARA_GROQ_API_KEY' },
    { id: 'reddit', label: 'Reddit OAuth (opcional -- RSS funciona sin credenciales)', envVar: 'KRONARA_REDDIT_CLIENT_ID' },
    { id: 'meta', label: 'Meta (Facebook Reels)', envVar: 'KRONARA_META_PAGE_TOKEN' },
    { id: 'pexels', label: 'Pexels (video loops)', envVar: 'KRONARA_PEXELS_API_KEY' },
    { id: 'freesound', label: 'Freesound (música y SFX)', envVar: 'KRONARA_FREESOUND_ACCESS_TOKEN' },
  ];
</script>

<div class="space-y-4">
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

  {#if activeTab === 'ia'}
    <Card title="Presupuesto" subtitle="operations.context -- dato real">
      {#if loadError}
        <p class="text-[13px] text-ink-secondary">No se pudo cargar. Abre Kronara desde la aplicación de escritorio.</p>
      {:else if context}
        <div class="flex items-center justify-between text-[13px]">
          <span class="text-ink-secondary">Disponible hoy</span>
          <span class="font-display font-semibold text-ink">${context.budget_status.remaining_usd.toFixed(2)} / ${context.budget_status.maximum_usd.toFixed(2)}</span>
        </div>
        <div class="mt-2 h-1.5 rounded-full bg-line">
          <div
            class="h-full rounded-full bg-purple-500"
            style={`width:${(context.budget_status.remaining_usd / context.budget_status.maximum_usd) * 100}%`}
          ></div>
        </div>
      {:else}
        <p class="text-[13px] text-ink-secondary">Cargando…</p>
      {/if}
    </Card>

    <Card title="Proveedores" subtitle="Configurados vía .env -- todos gratuitos">
      <ul class="divide-y divide-line-subtle">
        {#each PROVIDERS as provider}
          <li class="flex items-center justify-between py-2.5">
            <div>
              <p class="text-[12.5px] text-ink">{provider.label}</p>
              <p class="mt-0.5 text-[11px] text-ink-tertiary">{provider.envVar}</p>
            </div>
            <Badge tone="neutral">Ver .env</Badge>
          </li>
        {/each}
      </ul>
      <p class="mt-3 text-[11.5px] text-ink-tertiary">
        La edición de credenciales desde esta pantalla (sin tocar .env a mano) todavía no está conectada -- necesita una ruta de autoridad Rust dedicada para nunca exponer secretos a Python o a la UI.
      </p>
    </Card>
  {:else if activeTab === 'seguridad'}
    <Card title="Seguridad">
      <ul class="space-y-2 text-[12.5px] text-ink-secondary">
        <li>• Los secretos viven solo en Rust; Python nunca los recibe en texto plano.</li>
        <li>• Cada acción con efectos externos pasa por una lista cerrada de herramientas permitidas.</li>
        <li>• Las trazas de herramientas nunca incluyen el cuerpo de las señales externas (ej. texto de Reddit).</li>
      </ul>
    </Card>
  {:else}
    <Card title={TAB_LABELS[activeTab]}>
      <p class="text-[13px] text-ink-secondary">
        Esta pestaña necesita una ruta de RPC dedicada para leer/escribir configuración real -- todavía no conectada.
      </p>
    </Card>
  {/if}
</div>
