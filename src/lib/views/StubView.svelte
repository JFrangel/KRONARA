<script>
  import Icon from '../components/Icon.svelte';

  let { icon = 'grid', title = '', description = '' } = $props();
</script>

<div class="flex h-full min-h-[420px] flex-col items-center justify-center rounded-2xl border border-dashed border-line px-6 text-center">
  <span class="grid h-12 w-12 place-items-center rounded-full bg-surface text-purple-400">
    <Icon name={icon} size={22} />
  </span>
  <h2 class="mt-4 font-display text-base font-semibold text-ink">{title}</h2>
  <p class="mt-2 max-w-sm text-[13px] leading-relaxed text-ink-secondary">{description}</p>
  <span class="mt-4 rounded-full bg-surface px-3 py-1 text-[11px] text-ink-tertiary">En construcción</span>
</div>
