<script>
  let { title = '', subtitle = '', class: className = '', children } = $props();
</script>

<section class="rounded-2xl border border-line bg-surface p-5 {className}">
  {#if title}
    <div class="mb-4 flex items-start justify-between gap-3">
      <h2 class="text-[11.5px] font-semibold uppercase tracking-[0.11em] text-ink-secondary">{title}</h2>
      {#if subtitle}<span class="text-[11px] text-ink-tertiary">{subtitle}</span>{/if}
    </div>
  {/if}
  {@render children?.()}
</section>
