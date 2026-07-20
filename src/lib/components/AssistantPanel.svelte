<script>
  import Icon from './Icon.svelte';
  import { appendChatResponse, appendUserMessage, createOperationsState } from '../operations-state.js';
  import { callOperations } from '../tauri-operations.js';

  let { open = $bindable(false), connection = 'disconnected' } = $props();

  let state = $state(createOperationsState());
  let question = $state('');

  async function ask() {
    const message = question.trim();
    if (!message || state.chatStatus === 'thinking') return;
    const requestId = `req_${crypto.randomUUID()}`;
    question = '';
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
</script>

{#if open}
  <div class="fixed inset-0 z-40 bg-black/40" onclick={() => (open = false)} aria-hidden="true"></div>
  <aside class="fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col border-l border-line bg-bg shadow-2xl">
    <div class="flex items-center justify-between border-b border-line px-5 py-4">
      <div class="flex items-center gap-2">
        <Icon name="wand" size={16} class="text-purple-400" />
        <h2 class="font-display text-sm font-semibold text-ink">Pregunta a Kronara</h2>
      </div>
      <button class="grid h-7 w-7 place-items-center rounded-md text-ink-tertiary hover:bg-surface-hover hover:text-ink" onclick={() => (open = false)} aria-label="Cerrar asistente">
        ✕
      </button>
    </div>

    <div class="flex-1 space-y-3 overflow-y-auto px-5 py-4">
      {#if state.messages.length === 0}
        <p class="text-[13px] leading-relaxed text-ink-secondary">
          Pregunta por agentes, bloqueos, evidencia, métricas o decisiones. Los cambios se proponen; no se ejecutan desde el chat.
        </p>
      {/if}
      {#each state.messages as message}
        <article class="max-w-[92%] rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed" class:ml-auto={message.role === 'user'} class:bg-purple-500={message.role === 'user'} class:text-ink={message.role === 'user'} class:bg-surface={message.role === 'assistant'} class:border={message.role === 'assistant'} class:border-line={message.role === 'assistant'} class:text-ink-secondary={message.role === 'assistant'}>
          <p>{message.content}</p>
          {#if message.citations?.length}
            <p class="mt-1.5 text-[11px] text-ink-tertiary">{message.citations.length} evidencia(s) enlazada(s)</p>
          {/if}
        </article>
      {/each}
      {#if state.pendingAction}
        <aside class="rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-[12px] text-warning">
          Propuesta pendiente: {state.pendingAction.kind}. Requiere aprobación administrativa.
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
