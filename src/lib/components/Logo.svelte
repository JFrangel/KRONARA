<script>
  // Inline brand mark used by the local web app.
  let { size = 32, class: className = '' } = $props();
</script>

<svg viewBox="0 0 512 512" width={size} height={size} class={className} xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="kronara-logo-g" x1="64" y1="448" x2="448" y2="64" gradientUnits="userSpaceOnUse">
      <stop stop-color="#7b5cff" />
      <stop offset="1" stop-color="#ed496e" />
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="116" fill="#090b12" />
  <circle cx="256" cy="256" r="166" fill="none" stroke="#242836" stroke-width="18" />
  <path
    d="M168 118v276M174 276 344 116M176 274l180 132"
    fill="none"
    stroke="url(#kronara-logo-g)"
    stroke-width="46"
    stroke-linecap="round"
    stroke-linejoin="round"
  />
  <circle cx="168" cy="118" r="20" fill="#9f83ff" />
  <circle cx="344" cy="116" r="20" fill="#ed496e" />
  <circle cx="356" cy="406" r="20" fill="#ed496e" />
</svg>
