<script>
  import { onMount } from 'svelte';
  import { createControlState } from './lib/control-state.js';
  import {
    appendChatResponse,
    appendUserMessage,
    applyProgressEvent,
    createOperationsState,
  } from './lib/operations-state.js';
  import { callOperations, getControlState, setGlobalPause } from './lib/tauri-operations.js';

  let control = createControlState();
  let operations = createOperationsState();
  let question = '';
  let notice = '';
  let subreddit = 'Historias';
  let contentRunning = false;
  let contentResult = null;

  const stages = [
    ['Opportunity Intelligence', 'Señales permitidas y deduplicadas'],
    ['Writing Room', 'Tres conceptos, crítica independiente'],
    ['Production Direction', 'Timeline reproducible y control de calidad'],
    ['Distribution', 'Facebook Reels bajo autoridad de Rust'],
  ];

  onMount(async () => {
    try {
      const snapshot = await getControlState();
      control = { ...control, ...snapshot };
      const context = await callOperations('operations.context', {});
      operations = { ...operations, connection: 'connected', context };
    } catch (error) {
      operations = { ...operations, connection: 'unavailable' };
      notice = 'El plano cognitivo no está disponible. Abre Kronara desde la aplicación de escritorio.';
    }
  });

  async function toggleGlobalPause() {
    try {
      const snapshot = await setGlobalPause(!control.paused);
      control = { ...control, ...snapshot };
      notice = snapshot.paused
        ? 'La autoridad de Rust detuvo nuevas acciones.'
        : 'La operación puede reanudarse dentro de sus límites.';
    } catch (error) {
      notice = 'No fue posible cambiar la pausa global.';
    }
  }

  async function askKronara() {
    const message = question.trim();
    if (!message || operations.chatStatus === 'thinking') return;
    const requestId = `req_${crypto.randomUUID()}`;
    question = '';
    notice = '';
    operations = appendUserMessage(operations, message);
    try {
      const response = await callOperations('operations.chat', {
        schema_version: 1,
        request_id: requestId,
        conversation_id: 'operations_primary',
        message,
      });
      operations = appendChatResponse(operations, response);
      await refreshTimeline(`chat:${requestId}`);
    } catch (error) {
      operations = {
        ...operations,
        chatStatus: 'failed',
        messages: [
          ...operations.messages,
          { role: 'assistant', content: 'No pude consultar la operación en este momento.', citations: [] },
        ],
      };
    }
  }

  async function runStoryTest() {
    const terminal = ['completed', 'blocked', 'failed', 'cancelled'];
    if (operations.activeRun && !terminal.includes(operations.activeRun.status)) return;
    notice = '';
    try {
      const run = await callOperations('story.test', {
        story_id: `owned_ui_${Date.now()}`,
        wait: false,
      });
      operations = { ...operations, activeRun: run };
      await pollRun(run.run_id);
    } catch (error) {
      notice = 'La prueba narrativa no pudo iniciarse.';
    }
  }

  async function runProductionContent() {
    if (contentRunning || operations.connection !== 'connected') return;
    const community = subreddit.trim().replace(/^r\//, '');
    if (!community) {
      notice = 'Escribe una comunidad de Reddit para investigar.';
      return;
    }
    contentRunning = true;
    contentResult = null;
    notice = '';
    try {
      const result = await callOperations('content.run', {
        story_id: `owned_reddit_${Date.now()}`,
        subreddits: [community],
        sort: 'hot',
        limit: 25,
        target_duration_seconds: 90,
      });
      contentResult = result;
      await refreshTimeline(result.run_id);
    } catch (error) {
      notice = 'El vertical productivo se detuvo: ninguna historia se publica si falla Reddit, los modelos, los derechos o la calidad.';
    } finally {
      contentRunning = false;
    }
  }

  async function pollRun(runId) {
    const progress = await callOperations('run.progress', { run_id: runId });
    operations = { ...operations, activeRun: progress };
    await refreshTimeline(runId);
    if (!['completed', 'blocked', 'failed', 'cancelled'].includes(progress.status)) {
      setTimeout(() => pollRun(runId).catch(() => (notice = 'Se perdió la actualización de progreso.')), 700);
    }
  }

  async function cancelRun() {
    if (!operations.activeRun) return;
    const progress = await callOperations('run.cancel', { run_id: operations.activeRun.run_id });
    operations = { ...operations, activeRun: progress };
  }

  async function refreshTimeline(runId) {
    const timeline = await callOperations('tools.timeline', { run_id: runId });
    for (const event of timeline.events) operations = applyProgressEvent(operations, event);
  }
</script>

<svelte:head>
  <meta name="description" content="Kronara autonomous editorial operating system" />
</svelte:head>

<main>
  <header>
    <div>
      <span class="eyebrow">KRONARA OS · v0.5</span>
      <h1>La fábrica editorial está <em>{control.paused ? 'en pausa' : 'bajo control'}</em></h1>
      <p>Agentes autónomos con evidencia, límites, memoria y recuperación.</p>
    </div>
    <button class:resume={control.paused} onclick={toggleGlobalPause}>
      {control.paused ? 'Reanudar operación' : 'Pausa global'}
    </button>
  </header>

  {#if notice}<p class="notice">{notice}</p>{/if}

  <section class="status-grid">
    <article class="hero-card">
      <span class="label">MODO ACTIVO</span>
      <strong>FULL AUTO</strong>
      <p>Solo avanza cuando derechos, originalidad, calidad y políticas pasan.</p>
      <div class="meter"><i></i></div>
    </article>
    <article>
      <span class="label">PLANO COGNITIVO</span>
      <strong class="compact">{operations.connection === 'connected' ? 'CONECTADO' : 'SIN CONEXIÓN'}</strong>
      <p>RPC local autenticado</p>
    </article>
    <article>
      <span class="label">AUTORIDAD</span>
      <strong class="compact">RUST</strong>
      <p>secretos y efectos externos</p>
    </article>
  </section>

  <section class="production-vertical" aria-label="Crear historia original desde señales de Reddit">
    <div class="section-title">
      <span>VERTICAL PRODUCTIVO</span>
      <small>Reddit oficial → oportunidad abstracta → historia propia</small>
    </div>
    <div class="production-controls">
      <label for="subreddit">Comunidad para observar</label>
      <input id="subreddit" bind:value={subreddit} autocomplete="off" placeholder="Historias" />
      <button onclick={runProductionContent} disabled={contentRunning || operations.connection !== 'connected'}>
        {contentRunning ? 'Investigando y creando…' : 'Crear historia gobernada'}
      </button>
    </div>
    <p class="tool-route"><code>reddit.list_signals</code> usa solo señales abstractas; nunca entrega el cuerpo externo al escritor.</p>
    {#if contentResult}
      <div class="production-result" data-status={contentResult.status}>
        <div>
          <span class="label">RESULTADO</span>
          <h2>{contentResult.story?.title ?? contentResult.status}</h2>
          <p>{contentResult.story?.hook ?? 'La ejecución fue bloqueada de forma segura.'}</p>
        </div>
        {#if contentResult.story}
          <dl>
            <div><dt>Generador</dt><dd>{contentResult.story.generator_family}</dd></div>
            <div><dt>Crítico</dt><dd>{contentResult.story.critic_family}</dd></div>
            <div><dt>Duración</dt><dd>{Math.round(contentResult.story.estimated_seconds)} s</dd></div>
            <div><dt>RAG citado</dt><dd>{contentResult.rag_citations?.length ?? 0}</dd></div>
          </dl>
          <details>
            <summary>Ver guion propio y evidencia</summary>
            <p class="script">{contentResult.story.script}</p>
            {#each contentResult.rag_citations ?? [] as citation}
              <small class="citation">{citation}</small>
            {/each}
          </details>
        {/if}
      </div>
    {/if}
  </section>

  <div class="workspace-grid">
    <section class="pipeline">
      <div class="section-title"><span>PIPELINE COGNITIVO</span><small>Persistente y recuperable</small></div>
      {#each stages as stage, index}
        <div class="stage">
          <span class="index">0{index + 1}</span>
          <div><h2>{stage[0]}</h2><p>{stage[1]}</p></div>
          <span class:active={index === 0 && !control.paused} class="dot"></span>
        </div>
      {/each}
      <div class="story-controls">
        <button class="secondary" onclick={runStoryTest}>Probar historia propia</button>
        {#if operations.activeRun}
          <div class="run-progress">
            <span>{operations.activeRun.status} · {operations.activeRun.progress_percent}%</span>
            <div><i style={`width:${operations.activeRun.progress_percent}%`}></i></div>
          </div>
          {#if !['completed', 'blocked', 'failed', 'cancelled'].includes(operations.activeRun.status)}
            <button class="ghost" onclick={cancelRun}>Cancelar</button>
          {/if}
        {/if}
      </div>
    </section>

    <section class="operations-chat" aria-label="Chat de operaciones">
      <div class="section-title"><span>PREGUNTA A KRONARA</span><small>{operations.chatStatus}</small></div>
      <div class="messages" aria-live="polite">
        {#if operations.messages.length === 0}
          <p class="empty">Pregunta por agentes, bloqueos, evidencia, métricas o decisiones. Los cambios se proponen; no se ejecutan desde el chat.</p>
        {/if}
        {#each operations.messages as message}
          <article class:assistant={message.role === 'assistant'}>
            <span>{message.role === 'assistant' ? 'Kronara' : 'Tú'}</span>
            <p>{message.content}</p>
            {#if message.citations?.length}
              <small>{message.citations.length} evidencia(s) enlazada(s)</small>
            {/if}
          </article>
        {/each}
      </div>
      {#if operations.pendingAction}
        <aside class="intent">Propuesta pendiente: {operations.pendingAction.kind}. Requiere aprobación administrativa.</aside>
      {/if}
      <form onsubmit={(event) => { event.preventDefault(); askKronara(); }}>
        <label for="question">Tu pregunta</label>
        <textarea id="question" bind:value={question} rows="3" placeholder="¿Qué agente está bloqueado y qué evidencia lo explica?"></textarea>
        <button type="submit" disabled={operations.connection !== 'connected' || operations.chatStatus === 'thinking'}>Consultar operación</button>
      </form>
    </section>
  </div>

  <section class="tool-timeline" aria-label="Herramientas utilizadas">
    <div class="section-title"><span>HERRAMIENTAS UTILIZADAS</span><small>Trazas resumidas, sin secretos</small></div>
    {#if operations.toolEvents.length === 0}
      <p class="empty">Las llamadas aparecerán aquí con su agente, resultado, tiempo y evidencia.</p>
    {/if}
    <div class="tool-grid">
      {#each operations.toolEvents.slice(-12).reverse() as event}
        <article data-status={event.status}>
          <div><strong>{event.agent_id}</strong><span>{event.status} · {event.duration_ms ?? 0} ms</span></div>
          <h3>{event.tool_id}</h3>
          <p>{event.result_summary}</p>
          {#if event.evidence_refs?.length}<small>{event.evidence_refs.length} evidencia(s)</small>{/if}
        </article>
      {/each}
    </div>
  </section>
</main>
