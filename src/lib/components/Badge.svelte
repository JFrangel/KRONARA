<script>
  // tone: neutral | success | warning | error | info | purple
  let { tone = 'neutral', children } = $props();

  const TONES = {
    neutral: 'bg-surface-hover text-ink-secondary',
    success: 'bg-success/15 text-success',
    warning: 'bg-warning/15 text-warning',
    error: 'bg-error/15 text-error',
    info: 'bg-info/15 text-info',
    purple: 'bg-purple-500/20 text-purple-300',
  };
</script>

<span class="inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium {TONES[tone] || TONES.neutral}">
  {@render children?.()}
</span>
