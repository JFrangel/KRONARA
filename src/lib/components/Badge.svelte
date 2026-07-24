<script>
  // tone: neutral | success | warning | error | info | purple | live
  // mono: render as font-mono uppercase (evidentiary status codes / IDs / counts).
  let { tone = 'neutral', mono = false, children } = $props();

  const TONES = {
    neutral: 'bg-surface-hover text-ink-secondary ring-1 ring-inset ring-line',
    success: 'bg-success/15 text-success ring-1 ring-inset ring-success/25',
    warning: 'bg-warning/15 text-warning ring-1 ring-inset ring-warning/25',
    error: 'bg-error/15 text-error ring-1 ring-inset ring-error/25',
    info: 'bg-info/15 text-info ring-1 ring-inset ring-info/25',
    purple: 'bg-purple-500/20 text-purple-300 ring-1 ring-inset ring-purple-500/30',
    // The one sanctioned home for the ember accent: a live/on-air signal.
    live: 'bg-ember-500/12 text-ember-400 ring-1 ring-inset ring-ember-500/30',
  };
</script>

<span
  class="inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] transition-colors {mono
    ? 'font-mono text-[10.5px] uppercase tracking-[0.06em]'
    : 'font-medium'} {TONES[tone] || TONES.neutral}"
>
  {#if tone === 'live'}<span class="live-dot mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-ember-500"></span>{/if}
  {@render children?.()}
</span>
