<script>
  // Placeholder de carga con shimmer. Props: lines (nº de barras), y clase extra.
  let { lines = 3, class: extra = '' } = $props();
</script>

<div class="space-y-2 {extra}" aria-hidden="true">
  {#each Array(lines) as _, i}
    <div
      class="kronara-skeleton h-3 rounded-full"
      style={`width:${[92, 78, 64, 85, 70][i % 5]}%`}
    ></div>
  {/each}
</div>

<style>
  .kronara-skeleton {
    background: linear-gradient(
      90deg,
      color-mix(in srgb, currentColor 8%, transparent) 25%,
      color-mix(in srgb, currentColor 16%, transparent) 37%,
      color-mix(in srgb, currentColor 8%, transparent) 63%
    );
    background-size: 400% 100%;
    animation: kronara-shimmer 1.4s ease-in-out infinite;
    color: var(--ink, #9aa);
  }
  @keyframes kronara-shimmer {
    0% { background-position: 100% 0; }
    100% { background-position: -100% 0; }
  }
  @media (prefers-reduced-motion: reduce) {
    .kronara-skeleton { animation: none; }
  }
</style>
