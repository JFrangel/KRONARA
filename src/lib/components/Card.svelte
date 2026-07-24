<script>
  // interactive: adds a hover lift + purple edge (use only on clickable cards).
  // editorial: renders the title in the literary serif instead of the default
  // uppercase-tracked utility eyebrow (use for narrative/story headers).
  let {
    title = '',
    subtitle = '',
    interactive = false,
    editorial = false,
    class: className = '',
    children,
  } = $props();
</script>

<section
  class="rounded-2xl border border-line bg-gradient-to-br from-surface to-surface-inset p-5 shadow-card transition-[transform,border-color,box-shadow] duration-200 ease-standard {interactive
    ? 'hover:-translate-y-0.5 hover:border-purple-500/30 hover:shadow-card-hover'
    : ''} {className}"
>
  {#if title}
    <div
      class="relative mb-4 flex items-start justify-between gap-3 pb-3 after:absolute after:inset-x-0 after:bottom-0 after:h-px after:bg-gradient-to-r after:from-line after:via-line-subtle after:to-transparent"
    >
      {#if editorial}
        <h2 class="font-display text-lg font-medium leading-tight text-ink">{title}</h2>
      {:else}
        <h2 class="text-[11.5px] font-semibold uppercase tracking-[0.11em] text-ink-secondary">{title}</h2>
      {/if}
      {#if subtitle}<span class="shrink-0 text-[11px] text-ink-tertiary">{subtitle}</span>{/if}
    </div>
  {/if}
  {@render children?.()}
</section>
