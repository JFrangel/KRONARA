<script>
  import Icon from './Icon.svelte';
  import Logo from './Logo.svelte';
  import { PRINCIPAL_NAV, CHANNELS } from '../nav.js';

  let { activeView = 'panel', onNavigate = () => {}, collapsed = $bindable(false), systemHealthy = true, systemStatus = '' } = $props();
</script>

<aside class="flex h-full flex-col border-r border-line bg-bg px-3 py-4 transition-[width] duration-200" class:w-64={!collapsed} class:w-[76px]={collapsed}>
  <div class="flex items-center justify-between px-2">
    <div class="flex items-center gap-2 overflow-hidden">
      <Logo size={32} class="shrink-0 rounded-lg" />
      {#if !collapsed}
        <div class="leading-tight">
          <p class="font-display text-sm font-bold tracking-wide text-ink">KRONARA</p>
          <p class="text-[11px] text-ink-tertiary">Studio</p>
        </div>
      {/if}
    </div>
    <button
      class="grid h-7 w-7 shrink-0 place-items-center rounded-md text-ink-tertiary hover:bg-surface-hover hover:text-ink"
      onclick={() => (collapsed = !collapsed)}
      aria-label={collapsed ? 'Expandir barra lateral' : 'Contraer barra lateral'}
    >
      <Icon name={collapsed ? 'chevron-right' : 'chevron-left'} size={16} />
    </button>
  </div>

  <nav class="mt-6 flex-1 overflow-y-auto">
    {#if !collapsed}<p class="px-3 pb-2 text-[11px] font-medium tracking-[0.18em] text-ink-tertiary">PRINCIPAL</p>{/if}
    <ul class="flex flex-col gap-0.5">
      {#each PRINCIPAL_NAV as item (item.id)}
        <li>
          <button
            class="relative flex w-full items-center gap-3 overflow-hidden rounded-lg px-3 py-2 text-left text-[13.5px] transition-all duration-150 {activeView === item.id
              ? 'bg-gradient-to-r from-purple-500 to-purple-600 font-medium text-ink shadow-[0_6px_16px_-8px_rgba(123,92,255,0.65)]'
              : 'text-ink-secondary hover:translate-x-0.5 hover:bg-surface-hover hover:text-ink'}"
            onclick={() => onNavigate(item.id)}
            title={collapsed ? item.label : undefined}
          >
            {#if activeView === item.id}<span class="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-full bg-purple-300"></span>{/if}
            <Icon name={item.icon} size={17} class="shrink-0 {activeView === item.id ? 'text-purple-100' : ''}" />
            {#if !collapsed}<span class="truncate">{item.label}</span>{/if}
          </button>
        </li>
      {/each}
    </ul>

    {#if !collapsed}<p class="px-3 pb-2 pt-6 text-[11px] font-medium tracking-[0.18em] text-ink-tertiary">CANALES</p>{/if}
    <ul class="flex flex-col gap-0.5">
      {#each CHANNELS as channel (channel.id)}
        <li>
          <button
            class="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-[13.5px] text-ink-secondary transition-colors hover:bg-surface-hover hover:text-ink"
            onclick={() => onNavigate('configuracion')}
            title={collapsed ? channel.label : undefined}
          >
            <span class="grid h-[17px] w-[17px] shrink-0 place-items-center text-ink-tertiary" title="Estado de conexión no verificado">
              <span class="h-1.5 w-1.5 rounded-full bg-ink-tertiary"></span>
            </span>
            {#if !collapsed}<span class="truncate">{channel.label}</span>{/if}
          </button>
        </li>
      {/each}
    </ul>
  </nav>

  {#if !collapsed}
    <div class="mt-4 rounded-2xl border border-line bg-gradient-to-br from-surface to-surface-inset p-3.5 shadow-[0_2px_10px_-4px_rgba(0,0,0,0.6)] transition-colors hover:from-surface-hover">
      <div class="flex items-center gap-1.5">
        <Icon name="sparkles" size={13} class="text-purple-300" />
        <span class="font-mono text-[10px] tracking-[0.16em] text-purple-300/70">PLAN LOCAL</span>
      </div>
      <p class="mt-2 text-sm font-semibold text-ink">Herramientas gratuitas</p>
      <p class="mt-1 text-[11.5px] leading-snug text-ink-secondary">SDXL local, Nemotron/Qwen/Kimi gratis, sin costos por episodio.</p>
    </div>
  {/if}

  <div class="mt-3 flex items-center gap-2 px-2 pt-2 text-[11.5px] text-ink-tertiary">
    <span class="h-1.5 w-1.5 shrink-0 rounded-full" class:bg-success={systemHealthy} class:bg-error={!systemHealthy}></span>
    {#if !collapsed}<span class="truncate">{systemStatus || (systemHealthy ? 'Todos los sistemas operativos' : 'Sistema degradado')}</span>{/if}
  </div>
</aside>
