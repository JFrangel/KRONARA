<script>
  // Shimmer loading placeholder (uses the global .kron-shimmer sweep).
  // Props: lines (nº of body bars), heading (add a taller title bar first so
  // the ghost echoes a title-over-paragraph shape), and an extra class.
  let { lines = 3, heading = false, class: extra = '' } = $props();
</script>

<div class="space-y-2 {extra}" aria-hidden="true">
  {#if heading}
    <div class="kron-shimmer mb-1 h-4 w-2/3 rounded-md"></div>
  {/if}
  {#each Array(lines) as _, i}
    <div class="kron-shimmer h-3 rounded-full" style={`width:${[92, 78, 64, 85, 70][i % 5]}%`}></div>
  {/each}
</div>
