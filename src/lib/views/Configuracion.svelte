<script>
  import { onMount } from 'svelte';
  import Card from '../components/Card.svelte';
  import Badge from '../components/Badge.svelte';
  import Icon from '../components/Icon.svelte';
  import { callOperations } from '../local-operations.js';

  const TABS = ['general', 'ia', 'voces', 'publicacion', 'almacenamiento', 'seguridad'];
  const TAB_LABELS = {
    general: 'General', ia: 'IA y modelos', voces: 'Voces', publicacion: 'Publicación',
    almacenamiento: 'Almacenamiento', seguridad: 'Seguridad',
  };

  let activeTab = $state('general');
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

  const CHANNELS = [
    { label: 'YouTube', icon: 'youtube', note: 'Video largo y Shorts' },
    { label: 'Spotify', icon: 'spotify', note: 'Podcast de audio' },
    { label: 'Instagram', icon: 'instagram', note: 'Reels y teasers' },
    { label: 'Facebook', icon: 'facebook', note: 'Video y comunidad' },
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

  {#if activeTab === 'general'}
    <div class="grid grid-cols-1 gap-4 xl:grid-cols-[1.1fr_1fr_1fr]">
      <Card title="Perfil del espacio" subtitle="Preferencias locales">
        <div class="flex items-center gap-3 rounded-xl border border-purple-500/25 bg-purple-500/10 p-3">
          <div class="grid h-11 w-11 place-items-center rounded-xl bg-purple-500/20 text-purple-300"><Icon name="wand" size={20} /></div>
          <div class="min-w-0">
            <p class="font-display text-base font-semibold text-ink">Kronara Studio</p>
            <p class="mt-0.5 text-[11px] text-ink-secondary">Estudio editorial local</p>
          </div>
          <Badge tone="success">Activo</Badge>
        </div>
        <dl class="mt-4 space-y-3 text-[12px]">
          <div class="flex items-center justify-between border-b border-line-subtle pb-2"><dt class="text-ink-tertiary">Idioma</dt><dd class="text-ink">Español (ES)</dd></div>
          <div class="flex items-center justify-between border-b border-line-subtle pb-2"><dt class="text-ink-tertiary">Zona horaria</dt><dd class="text-ink">UTC−05:00 Bogotá</dd></div>
          <div class="flex items-center justify-between"><dt class="text-ink-tertiary">Modo operativo</dt><dd class="text-purple-300">FULL AUTO</dd></div>
        </dl>
      </Card>

      <Card title="Preferencias de interfaz" subtitle="Diseño del estudio">
        <div class="space-y-3">
          <div class="flex items-center justify-between rounded-xl border border-line bg-surface-inset p-3">
            <div><p class="text-[12px] font-medium text-ink">Tema</p><p class="mt-0.5 text-[11px] text-ink-tertiary">Oscuro cinematográfico</p></div>
            <span class="rounded-lg border border-line px-2.5 py-1 text-[11px] text-ink-secondary">Oscuro</span>
          </div>
          <div class="flex items-center justify-between rounded-xl border border-line bg-surface-inset p-3">
            <div><p class="text-[12px] font-medium text-ink">Vista compacta</p><p class="mt-0.5 text-[11px] text-ink-tertiary">Más información por pantalla</p></div>
            <span class="relative h-5 w-9 rounded-full bg-purple-500"><span class="absolute right-1 top-1 h-3 w-3 rounded-full bg-white"></span></span>
          </div>
          <div class="flex items-center justify-between rounded-xl border border-line bg-surface-inset p-3">
            <div><p class="text-[12px] font-medium text-ink">Guardado automático</p><p class="mt-0.5 text-[11px] text-ink-tertiary">Protege cambios de producción</p></div>
            <span class="relative h-5 w-9 rounded-full bg-purple-500"><span class="absolute right-1 top-1 h-3 w-3 rounded-full bg-white"></span></span>
          </div>
        </div>
      </Card>

      <Card title="Estado del sistema" subtitle="Comprobación local">
        <div class="flex items-center gap-2 rounded-xl border border-success/25 bg-success/10 p-3">
          <span class="h-2 w-2 rounded-full bg-success"></span><span class="text-[12px] font-medium text-success">Interfaz operativa</span>
        </div>
        <div class="mt-3 grid grid-cols-3 gap-2 text-center">
          <div class="rounded-lg border border-line bg-surface-inset p-2"><p class="text-lg font-semibold text-ink">100%</p><p class="text-[10px] text-ink-tertiary">UI</p></div>
          <div class="rounded-lg border border-line bg-surface-inset p-2"><p class="text-lg font-semibold text-ink">D:</p><p class="text-[10px] text-ink-tertiary">Modelos</p></div>
          <div class="rounded-lg border border-line bg-surface-inset p-2"><p class="text-lg font-semibold text-ink">0</p><p class="text-[10px] text-ink-tertiary">Errores</p></div>
        </div>
        <p class="mt-3 text-[11px] leading-relaxed text-ink-tertiary">La generación visual local usa SDXL y conserva sus pesos en el disco D del proyecto.</p>
      </Card>

      <Card title="Motor visual y voz" subtitle="Producción de episodios">
        <div class="space-y-2.5">
          <div class="flex items-center gap-3 rounded-xl border border-line bg-surface-inset p-3"><div class="grid h-8 w-8 place-items-center rounded-lg bg-purple-500/15 text-purple-300"><Icon name="film" size={15} /></div><div><p class="text-[12px] font-medium text-ink">SDXL local</p><p class="text-[10.5px] text-ink-tertiary">RTX 4060 Ti · CUDA</p></div><Badge tone="success">Listo</Badge></div>
          <div class="flex items-center gap-3 rounded-xl border border-line bg-surface-inset p-3"><div class="grid h-8 w-8 place-items-center rounded-lg bg-ember-500/15 text-ember-400"><Icon name="wand" size={15} /></div><div><p class="text-[12px] font-medium text-ink">Narración local</p><p class="text-[10.5px] text-ink-tertiary">Fallback sin coste por episodio</p></div><Badge tone="neutral">Configurar</Badge></div>
        </div>
      </Card>

      <Card title="Publicación e integraciones" subtitle="Canales disponibles">
        <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {#each CHANNELS as channel}
            <div class="flex items-center gap-2.5 rounded-xl border border-line bg-surface-inset p-2.5"><div class="h-2 w-2 rounded-full bg-ink-tertiary"></div><div class="min-w-0"><p class="text-[11.5px] font-medium text-ink">{channel.label}</p><p class="truncate text-[10px] text-ink-tertiary">{channel.note}</p></div><span class="ml-auto text-[10px] text-ink-tertiary">Pendiente</span></div>
          {/each}
        </div>
        <p class="mt-3 text-[11px] text-ink-tertiary">Las credenciales se mantienen fuera de la interfaz y se leen desde el entorno local.</p>
      </Card>

      <Card title="Almacenamiento local" subtitle="Archivos y caché">
        <div class="rounded-xl border border-line bg-surface-inset p-3"><p class="text-[10px] uppercase tracking-wide text-ink-tertiary">Ruta de trabajo</p><p class="mt-1 truncate font-mono text-[11px] text-ink">D:\Proyecto Redit\.kronara</p></div>
        <div class="mt-3 flex items-center justify-between text-[11.5px]"><span class="text-ink-tertiary">Modelos SDXL</span><span class="text-success">Instalados</span></div>
        <div class="mt-2 h-1.5 rounded-full bg-line"><div class="h-full w-[42%] rounded-full bg-purple-500"></div></div>
      </Card>
    </div>
  {:else if activeTab === 'ia'}
    <Card title="Presupuesto" subtitle="operations.context -- dato real">
      {#if loadError}
        <p class="text-[13px] text-ink-secondary">No se pudo cargar. Inicia la web local y verifica que Python esté conectado.</p>
      {:else if context}
        <div class="flex items-center justify-between text-[13px]">
          <span class="text-ink-secondary">Disponible hoy</span>
          <span class="font-mono font-semibold text-ink">${context.budget_status.remaining_usd.toFixed(2)} / ${context.budget_status.maximum_usd.toFixed(2)}</span>
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
              <p class="mt-0.5 font-mono text-[11px] text-ink-tertiary">{provider.envVar}</p>
            </div>
            <Badge tone="neutral">Ver .env</Badge>
          </li>
        {/each}
      </ul>
      <p class="mt-3 text-[11.5px] text-ink-tertiary">
        La edición de credenciales desde esta pantalla (sin tocar .env a mano) todavía no está conectada. Por ahora, configúralas directamente en el archivo local `.env`.
      </p>
    </Card>
  {:else if activeTab === 'seguridad'}
    <Card title="Seguridad">
      <ul class="space-y-2 text-[12.5px] text-ink-secondary">
        <li>• Los secretos viven en `.env` local y no se muestran en la interfaz.</li>
        <li>• Cada acción con efectos externos pasa por una lista cerrada de métodos permitidos.</li>
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
