<script>
  import Icon from './Icon.svelte';

  const TERMINAL_STATES = ['completed', 'blocked', 'failed', 'cancelled'];

  let { title = 'Panel', activeRun = null, onOpenAssistant = () => {}, notificationCount = 0 } = $props();

  const isLive = $derived(!!activeRun && !TERMINAL_STATES.includes(activeRun.status));
</script>

<header class="flex h-16 shrink-0 items-center justify-between gap-4 border-b border-line bg-bg/90 px-4 backdrop-blur-xl sm:px-6">
  <div class="flex min-w-0 items-center gap-3">
    <h1 class="truncate font-display text-lg font-semibold text-ink">{title}</h1>
    {#if isLive}
      <span class="flex shrink-0 items-center gap-1.5 rounded-full border border-ember-500/40 bg-ember-500/10 px-2.5 py-1 text-[11px] font-medium text-ember-400">
        <span class="live-dot h-1.5 w-1.5 rounded-full bg-ember-500"></span>
        Produciendo
      </span>
    {/if}
  </div>

  <div class="hidden flex-1 justify-center md:flex">
    <label class="group flex w-full max-w-md items-center gap-2 rounded-full border border-line bg-surface-inset px-4 py-2 text-ink-tertiary transition-[border-color,box-shadow] duration-150 focus-within:border-purple-500 focus-within:shadow-[0_0_0_3px_color-mix(in_srgb,var(--color-purple-500)_15%,transparent)]">
      <Icon name="search" size={15} class="shrink-0 group-focus-within:text-purple-400" />
      <input
        class="w-full min-w-0 bg-transparent text-[13px] text-ink placeholder:text-ink-tertiary focus:outline-none"
        placeholder="Buscar en Kronara..."
      />
      <kbd class="hidden shrink-0 rounded border border-line px-1.5 py-0.5 text-[10px] text-ink-tertiary lg:inline">Ctrl+K</kbd>
    </label>
  </div>

  <div class="flex shrink-0 items-center gap-1.5 sm:gap-2">
    <button
      class="group flex items-center gap-1.5 rounded-full bg-gradient-to-br from-purple-500 to-purple-600 px-3 py-1.5 text-[13px] font-medium text-ink shadow-[0_2px_12px_-2px_rgba(123,92,255,0.55)] transition-all duration-150 hover:from-purple-400 hover:to-purple-600 hover:shadow-[0_4px_18px_-2px_rgba(123,92,255,0.7)] active:scale-[0.97] sm:px-3.5"
      onclick={onOpenAssistant}
    >
      <Icon name="wand" size={14} class="shrink-0 transition-transform duration-150 group-hover:-rotate-12" />
      <span class="hidden sm:inline">Asistente</span>
    </button>
    <button class="relative grid h-9 w-9 shrink-0 place-items-center rounded-full text-ink-secondary transition-colors hover:bg-surface-hover hover:text-ink" aria-label="Notificaciones">
      <Icon name="bell" size={17} />
      {#if notificationCount > 0}
        <span class="absolute right-1 top-1 grid h-3.5 w-3.5 place-items-center rounded-full bg-error text-[9px] font-bold text-ink">{notificationCount}</span>
      {/if}
    </button>
    <button class="hidden h-9 w-9 shrink-0 place-items-center rounded-full text-ink-secondary transition-colors hover:bg-surface-hover hover:text-ink sm:grid" aria-label="Ajustes">
      <Icon name="gear" size={16} />
    </button>
    <span class="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-gradient-to-br from-purple-400 to-purple-600 text-xs font-bold text-ink shadow-[0_2px_8px_-2px_rgba(123,92,255,0.4)] ring-1 ring-purple-400/25 transition hover:ring-purple-300/40">KR</span>
  </div>
</header>
