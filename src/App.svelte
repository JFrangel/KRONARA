<script>
  import { createControlState, togglePause } from './lib/control-state.js';

  let control = createControlState();
  const stages = [
    ['Opportunity Intelligence', 'Leyendo señales permitidas'],
    ['Writing Room', 'Esperando una oportunidad'],
    ['Production Direction', 'Sin trabajos activos'],
    ['Distribution', 'Facebook Reels · preparado'],
  ];
</script>

<svelte:head><meta name="description" content="Kronara autonomous editorial operating system" /></svelte:head>

<main>
  <header>
    <div>
      <span class="eyebrow">KRONARA OS · v0.2</span>
      <h1>La fábrica editorial está <em>{control.paused ? 'en pausa' : 'bajo control'}</em></h1>
      <p>Agentes autónomos con evidencia, límites y recuperación completa.</p>
    </div>
    <button class:resume={control.paused} onclick={() => (control = togglePause(control))}>
      {control.paused ? 'Reanudar operación' : 'Pausa global'}
    </button>
  </header>

  <section class="status-grid">
    <article class="hero-card">
      <span class="label">MODO ACTIVO</span>
      <strong>FULL AUTO</strong>
      <p>Publica solo cuando derechos, originalidad, calidad y políticas pasan.</p>
      <div class="meter"><i></i></div>
    </article>
    <article><span class="label">LÍMITE DIARIO</span><strong>{control.dailyPublicationLimit}</strong><p>publicaciones</p></article>
    <article><span class="label">PRESUPUESTO</span><strong>${control.maxDailyCostUsd}</strong><p>máximo diario</p></article>
  </section>

  <section class="pipeline">
    <div class="section-title"><span>PIPELINE COGNITIVO</span><small>Persistente y recuperable</small></div>
    {#each stages as stage, index}
      <div class="stage">
        <span class="index">0{index + 1}</span>
        <div><h2>{stage[0]}</h2><p>{stage[1]}</p></div>
        <span class:active={index === 0} class="dot"></span>
      </div>
    {/each}
  </section>
</main>

