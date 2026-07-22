<script>
  import { onMount } from 'svelte';
  import Sidebar from './lib/components/Sidebar.svelte';
  import TopBar from './lib/components/TopBar.svelte';
  import AssistantPanel from './lib/components/AssistantPanel.svelte';
  import Panel from './lib/views/Panel.svelte';
  import Programas from './lib/views/Programas.svelte';
  import Calendario from './lib/views/Calendario.svelte';
  import Estudio from './lib/views/Estudio.svelte';
  import Analiticas from './lib/views/Analiticas.svelte';
  import Biblioteca from './lib/views/Biblioteca.svelte';
  import Configuracion from './lib/views/Configuracion.svelte';
  import StubView from './lib/views/StubView.svelte';
  import { createControlState } from './lib/control-state.js';
  import { createOperationsState } from './lib/operations-state.js';
  import { currentGenerationDetail, currentGenerationStage, episodeGeneration, formatElapsed, generationPercent } from './lib/generation-state.js';
  import { callOperations, getControlState } from './lib/local-operations.js';

  const VIEW_META = {
    panel: { title: 'Panel' },
    programas: { title: 'Programas', icon: 'film', description: 'Administra los 7 programas editoriales: perfil narrativo, estilo visual, voz, episodios y parrilla semanal.' },
    calendario: { title: 'Calendario', icon: 'calendar', description: 'Parrilla editorial semanal, con arrastrar y soltar para reprogramar.' },
    estudio: { title: 'Estudio' },
    biblioteca: { title: 'Biblioteca', icon: 'folder', description: 'Imágenes, videos, música, SFX y documentos generados o curados, con derechos y uso rastreados.' },
    agentes: { title: 'Agentes', icon: 'cpu', description: 'Los agentes especializados de Kronara: capacidades, herramientas permitidas, rendimiento.' },
    analiticas: { title: 'Analíticas', icon: 'chart', description: 'Rendimiento por programa y episodio, y audiencia por plataforma una vez que haya contenido publicado.' },
    publicacion: { title: 'Publicación', icon: 'send', description: 'Prepara, valida, programa y publica en YouTube, Spotify, Instagram, Facebook y TikTok.' },
    configuracion: { title: 'Configuración', icon: 'gear', description: 'Proveedores de IA, voces, publicación, almacenamiento y seguridad.' },
  };

  let activeView = $state('panel');
  let selectedProgramId = $state(null);
  let programOpenToken = $state(0);
  // Narrow windows (a narrow browser window, or one resized down)
  // start with the sidebar collapsed to its icon rail so content isn't
  // squeezed into a sliver -- one-time default, not a live sync, so a
  // manual expand isn't fought on every subsequent resize.
  let sidebarCollapsed = $state(typeof window !== 'undefined' && window.innerWidth < 768);
  let assistantOpen = $state(false);
  let control = $state(createControlState());
  let operations = $state(createOperationsState());

  onMount(async () => {
    try {
      const snapshot = await getControlState();
      control = { ...control, ...snapshot };
      const context = await callOperations('operations.context', {});
      operations = { ...operations, connection: 'connected', context };
    } catch (error) {
      operations = { ...operations, connection: 'unavailable' };
    }
  });

  function openGeneratingEpisode() {
    if (!$episodeGeneration?.programId) return;
    activeView = 'programas';
    selectedProgramId = $episodeGeneration.programId;
    programOpenToken += 1;
  }
</script>

<svelte:head>
  <meta name="description" content="Kronara Studio -- autonomous editorial operating system" />
</svelte:head>

<div class="flex h-screen bg-bg text-ink">
  <Sidebar
    {activeView}
    bind:collapsed={sidebarCollapsed}
    systemHealthy={operations.connection !== 'unavailable'}
    systemStatus={operations.connection === 'connected' ? 'Web local' : undefined}
      onNavigate={(id) => { activeView = id; selectedProgramId = null; }}
  />

  <div class="flex min-w-0 flex-1 flex-col">
    <TopBar
      title={VIEW_META[activeView]?.title ?? 'Panel'}
      activeRun={$episodeGeneration?.status === 'running' ? { status: 'running' } : operations.activeRun}
      onOpenAssistant={() => (assistantOpen = true)}
      notificationCount={0}
    />

    {#if $episodeGeneration}
      {@const stage = currentGenerationStage($episodeGeneration)}
      {@const percent = generationPercent($episodeGeneration)}
      <button
        class="border-b border-ember-500/25 bg-ember-500/10 px-4 py-2 text-left transition hover:bg-ember-500/15 sm:px-6"
        onclick={openGeneratingEpisode}
      >
        <div class="mx-auto flex w-full max-w-[1780px] flex-wrap items-center justify-between gap-3">
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <span class="live-dot h-2 w-2 rounded-full" class:bg-ember-500={$episodeGeneration.status === 'running'} class:bg-success={$episodeGeneration.status === 'completed'} class:bg-error={$episodeGeneration.status === 'failed'}></span>
              <p class="truncate text-[12px] font-semibold text-ink">{$episodeGeneration.status === 'running' ? 'Generando episodio' : $episodeGeneration.status === 'completed' ? 'Episodio generado' : 'Generación detenida'} · {$episodeGeneration.programName ?? 'Programa'}</p>
            </div>
            <p class="mt-0.5 truncate text-[11px] text-ink-tertiary">{$episodeGeneration.status === 'failed' ? $episodeGeneration.message : `${stage.label}: ${currentGenerationDetail($episodeGeneration)}`}</p>
          </div>
          <div class="flex min-w-[180px] items-center gap-3">
            <div class="h-1.5 min-w-28 flex-1 overflow-hidden rounded-full bg-line">
              <div class="h-full rounded-full bg-ember-500 transition-all duration-500" style={`width:${percent}%`}></div>
            </div>
            <span class="font-mono text-[11px] text-ink-tertiary">{percent}% · {formatElapsed($episodeGeneration.elapsedSeconds)}</span>
          </div>
        </div>
      </button>
    {/if}

    <main class="min-w-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6 lg:px-8">
      <div class="mx-auto w-full max-w-[1780px]">
      {#if activeView === 'panel'}
        <Panel {operations} {control} onNavigate={(id, params = {}) => { activeView = id; selectedProgramId = params.programId ?? null; }} />
      {:else if activeView === 'programas'}
        <Programas connection={operations.connection} initialProgramId={selectedProgramId} openToken={programOpenToken} />
      {:else if activeView === 'calendario'}
        <Calendario />
      {:else if activeView === 'estudio'}
        <Estudio bind:operations connection={operations.connection} />
      {:else if activeView === 'analiticas'}
        <Analiticas {operations} onNavigate={(id) => (activeView = id)} />
      {:else if activeView === 'biblioteca'}
        <Biblioteca {operations} />
      {:else if activeView === 'configuracion'}
        <Configuracion />
      {:else}
        <StubView icon={VIEW_META[activeView]?.icon} title={VIEW_META[activeView]?.title} description={VIEW_META[activeView]?.description} />
      {/if}
      </div>
    </main>
  </div>

  <AssistantPanel bind:open={assistantOpen} connection={operations.connection} />
</div>
