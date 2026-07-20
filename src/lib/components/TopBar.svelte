<script>
  import Icon from './Icon.svelte';

  let { title = 'Panel', onOpenAssistant = () => {}, notificationCount = 0 } = $props();
</script>

<header class="flex h-16 shrink-0 items-center justify-between gap-4 border-b border-line bg-bg px-6">
  <div class="flex min-w-0 items-center gap-4">
    <h1 class="truncate font-display text-lg font-semibold text-ink">{title}</h1>
  </div>

  <div class="flex flex-1 justify-center">
    <label class="flex w-full max-w-md items-center gap-2 rounded-full border border-line bg-surface-inset px-4 py-2 text-ink-tertiary focus-within:border-purple-500">
      <Icon name="search" size={15} />
      <input
        class="w-full bg-transparent text-[13px] text-ink placeholder:text-ink-tertiary focus:outline-none"
        placeholder="Buscar en Kronara..."
      />
      <kbd class="rounded border border-line px-1.5 py-0.5 text-[10px] text-ink-tertiary">Ctrl+K</kbd>
    </label>
  </div>

  <div class="flex shrink-0 items-center gap-2">
    <button
      class="flex items-center gap-1.5 rounded-full bg-purple-500 px-3.5 py-1.5 text-[13px] font-medium text-ink hover:bg-purple-600"
      onclick={onOpenAssistant}
    >
      <Icon name="wand" size={14} />
      Asistente
    </button>
    <button class="relative grid h-9 w-9 place-items-center rounded-full text-ink-secondary hover:bg-surface-hover" aria-label="Notificaciones">
      <Icon name="bell" size={17} />
      {#if notificationCount > 0}
        <span class="absolute right-1 top-1 grid h-3.5 w-3.5 place-items-center rounded-full bg-error text-[9px] font-bold text-ink">{notificationCount}</span>
      {/if}
    </button>
    <span class="grid h-9 w-9 place-items-center rounded-full bg-surface-hover text-ink-secondary">
      <Icon name="gear" size={16} />
    </span>
    <span class="grid h-9 w-9 place-items-center rounded-full bg-gradient-to-br from-purple-400 to-purple-600 text-xs font-bold text-ink">KR</span>
  </div>
</header>
