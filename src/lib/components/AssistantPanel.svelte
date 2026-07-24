<script>
  import Icon from './Icon.svelte';
  import { appendChatResponse, appendUserMessage, createOperationsState } from '../operations-state.js';
  import { callOperations } from '../local-operations.js';

  let { open = $bindable(false), connection = 'disconnected' } = $props();

  let state = $state(createOperationsState());
  let question = $state('');
  let approving = $state(false);

  async function ask(overrideMessage) {
    const raw = typeof overrideMessage === 'string' ? overrideMessage : question;
    const message = raw.trim();
    if (!message || state.chatStatus === 'thinking') return;
    const requestId = `req_${crypto.randomUUID()}`;
    if (typeof overrideMessage !== 'string') question = '';
    state = appendUserMessage(state, message);
    try {
      const response = await callOperations('operations.chat', {
        schema_version: 1,
        request_id: requestId,
        conversation_id: 'operations_primary',
        message,
      });
      state = appendChatResponse(state, response);
    } catch (error) {
      state = {
        ...state,
        chatStatus: 'failed',
        messages: [...state.messages, { role: 'assistant', content: 'No pude consultar la operación en este momento.', citations: [] }],
      };
    }
  }

  function dismissAction() {
    state = { ...state, pendingAction: null };
  }

  // Fase 1f: clicking a guided-flow chip sends its text as the next message.
  function sendQuickReply(text) {
    ask(text);
  }

  async function approveAction() {
    const intent = state.pendingAction;
    if (!intent || approving) return;
    approving = true;
    try {
      const outcome = await callOperations('action.approve', { idempotency_key: intent.idempotency_key });
      let content;
      if (outcome.status === 'executed' && outcome.result?.status === 'completed') {
        content = `Episodio creado: "${outcome.result.story?.title ?? outcome.result.run_id}".`;
      } else if (outcome.status === 'executed') {
        content = `No se pudo completar el episodio (${outcome.result?.error_code ?? outcome.result?.status}). No se publica nada a menos que Reddit, los modelos, los derechos y la calidad pasen todas las validaciones.`;
      } else if (outcome.status === 'not_found') {
        content = 'Esa propuesta ya no está disponible (expiró o ya se ejecutó).';
      } else {
        content = 'Esa propuesta todavía no se puede ejecutar automáticamente.';
      }
      state = { ...state, pendingAction: null, messages: [...state.messages, { role: 'assistant', content, citations: [] }] };
    } catch (error) {
      state = {
        ...state,
        messages: [...state.messages, { role: 'assistant', content: 'No pude aprobar la propuesta; la operación local la rechazó.', citations: [] }],
      };
    } finally {
      approving = false;
    }
  }
</script>

{#if open}
  <div class="fixed inset-0 z-40 bg-black/40" onclick={() => (open = false)} aria-hidden="true"></div>
  <aside class="fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col border-l border-line bg-bg shadow-2xl">
    <div class="flex items-center justify-between border-b border-line px-5 py-4">
      <div class="flex items-center gap-2">
        <Icon name="wand" size={16} class="text-purple-400" />
        <h2 class="text-sm font-semibold text-ink">Pregunta a Kronara</h2>
      </div>
      <button class="grid h-7 w-7 place-items-center rounded-md text-ink-tertiary hover:bg-surface-hover hover:text-ink" onclick={() => (open = false)} aria-label="Cerrar asistente">
        ✕
      </button>
    </div>

    <div class="flex-1 space-y-3 overflow-y-auto px-5 py-4">
      {#if state.messages.length === 0}
        <p class="text-[13px] leading-relaxed text-ink-secondary">
          Pregunta por agentes, bloqueos, evidencia, métricas o decisiones -- o di "quiero crear un video" y te guío paso a paso. Los cambios se proponen; no se ejecutan desde el chat sin tu aprobación.
        </p>
      {/if}
      {#each state.messages as message, index}
        <article class="max-w-[92%] rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed" class:ml-auto={message.role === 'user'} class:bg-purple-500={message.role === 'user'} class:text-ink={message.role === 'user'} class:bg-surface={message.role === 'assistant'} class:border={message.role === 'assistant'} class:border-line={message.role === 'assistant'} class:text-ink-secondary={message.role === 'assistant'}>
          <p>{message.content}</p>
          {#if message.citations?.length}
            <p class="mt-1.5 text-[11px] text-ink-tertiary">{message.citations.length} evidencia(s) enlazada(s)</p>
          {/if}
        </article>
        {#if message.role === 'assistant' && message.options?.length && index === state.messages.length - 1}
          <div class="flex flex-wrap gap-1.5">
            {#each message.options as option}
              <button
                class="rounded-full border border-purple-500/40 bg-purple-500/10 px-3 py-1 text-[11.5px] text-purple-200 transition-colors hover:bg-purple-500/20 disabled:cursor-not-allowed disabled:opacity-40"
                onclick={() => sendQuickReply(option)}
                disabled={connection !== 'connected' || state.chatStatus === 'thinking'}
              >
                {option}
              </button>
            {/each}
          </div>
        {/if}
      {/each}
      {#if state.pendingAction}
        <aside class="rounded-lg border border-warning/40 bg-warning/10 px-3 py-2.5 text-[12px] text-warning">
          <p>
            {#if state.pendingAction.kind === 'create_episode'}
              Propuesta: crear un episodio nuevo. Nada se ejecuta hasta que la apruebes.
            {:else}
              Propuesta pendiente: {state.pendingAction.kind}. Requiere aprobación administrativa.
            {/if}
          </p>
          <div class="mt-2 flex gap-2">
            {#if state.pendingAction.kind === 'create_episode'}
              <button
                class="rounded-full bg-purple-500 px-3 py-1 text-[11.5px] font-medium text-ink hover:bg-purple-600 disabled:cursor-not-allowed disabled:opacity-40"
                onclick={approveAction}
                disabled={approving || connection !== 'connected'}
              >
                {approving ? 'Ejecutando…' : 'Aprobar y crear'}
              </button>
            {/if}
            <button class="rounded-full border border-line px-3 py-1 text-[11.5px] text-ink-secondary hover:text-ink" onclick={dismissAction} disabled={approving}>
              Descartar
            </button>
          </div>
        </aside>
      {/if}
    </div>

    <form class="border-t border-line p-4" onsubmit={(event) => { event.preventDefault(); ask(); }}>
      <textarea
        class="w-full resize-none rounded-xl border border-line bg-surface-inset p-3 text-[13px] text-ink placeholder:text-ink-tertiary focus:border-purple-500 focus:outline-none"
        rows="3"
        placeholder="¿Qué agente está bloqueado y qué evidencia lo explica?"
        bind:value={question}
      ></textarea>
      <button
        type="submit"
        class="mt-2 w-full rounded-full bg-purple-500 py-2 text-[13px] font-medium text-ink hover:bg-purple-600 disabled:cursor-not-allowed disabled:opacity-40"
        disabled={connection !== 'connected' || state.chatStatus === 'thinking'}
      >
        {state.chatStatus === 'thinking' ? 'Consultando…' : 'Consultar operación'}
      </button>
    </form>
  </aside>
{/if}
