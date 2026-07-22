<script>
  let { title = '', subtitle = '', class: className = '', children } = $props();
</script>

<section class="rounded-2xl border border-line bg-gradient-to-br from-surface to-surface-inset p-5 shadow-[0_16px_40px_rgba(0,0,0,0.16)] {className}">
  {#if title}
    <div class="mb-4 flex items-start justify-between gap-3 border-b border-line-subtle pb-3">
      <h2 class="text-[11.5px] font-semibold uppercase tracking-[0.11em] text-ink-secondary">{title}</h2>
      {#if subtitle}<span class="text-[11px] text-ink-tertiary">{subtitle}</span>{/if}
    </div>
  {/if}
  {@render children?.()}
</section>
