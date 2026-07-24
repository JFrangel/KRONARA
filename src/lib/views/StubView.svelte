<script>
  import Icon from '../components/Icon.svelte';

  let { icon = 'grid', title = '', description = '' } = $props();
</script>

<div class="flex h-full min-h-[420px] flex-col items-center justify-center rounded-2xl border border-dashed border-line-subtle px-6 text-center">
  <span class="grid h-12 w-12 place-items-center rounded-full bg-gradient-to-br from-surface to-surface-inset text-purple-300 shadow-[0_0_28px_-6px_rgba(159,131,255,0.5)] ring-1 ring-line">
    <Icon name={icon} size={22} />
  </span>
  <h2 class="mt-4 font-display text-lg font-semibold text-ink">{title}</h2>
  <p class="mt-2 max-w-sm text-[13px] leading-relaxed text-ink-secondary">{description}</p>
  <span class="mt-4 inline-flex items-center gap-1.5 rounded-full border border-line bg-surface-inset px-3 py-1 font-mono text-[10px] tracking-wider text-ink-tertiary">
    <span class="h-1.5 w-1.5 rounded-full bg-warning"></span>
    En construcción
  </span>
</div>
