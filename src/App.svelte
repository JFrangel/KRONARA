<script>
  import { onMount } from 'svelte';
  import Sidebar from './lib/components/Sidebar.svelte';
  import TopBar from './lib/components/TopBar.svelte';
  import AssistantPanel from './lib/components/AssistantPanel.svelte';
  import Panel from './lib/views/Panel.svelte';
  import Programas from './lib/views/Programas.svelte';
  import Episodios from './lib/views/Episodios.svelte';
  import Calendario from './lib/views/Calendario.svelte';
  import Estudio from './lib/views/Estudio.svelte';
  import Configuracion from './lib/views/Configuracion.svelte';
  import StubView from './lib/views/StubView.svelte';
  import { createControlState } from './lib/control-state.js';
  import { createOperationsState } from './lib/operations-state.js';
  import { callOperations, getControlState } from './lib/tauri-operations.js';

  const VIEW_META = {
    panel: { title: 'Panel' },
    programas: { title: 'Programas', icon: 'film', description: 'Administra los 7 programas editoriales: perfil narrativo, estilo visual, voz y parrilla semanal.' },
    episodios: { title: 'Episodios', icon: 'list', description: 'Ciclo de vida completo de cada episodio: investigación, guion, producción, publicación.' },
    calendario: { title: 'Calendario', icon: 'calendar', description: 'Parrilla editorial semanal, con arrastrar y soltar para reprogramar.' },
    estudio: { title: 'Estudio' },
    biblioteca: { title: 'Biblioteca', icon: 'folder', description: 'Imágenes, videos, música, SFX y documentos generados o curados, con derechos y uso rastreados.' },
    agentes: { title: 'Agentes', icon: 'cpu', description: 'Los agentes especializados de Kronara: capacidades, herramientas permitidas, rendimiento.' },
    analiticas: { title: 'Analíticas', icon: 'chart', description: 'Rendimiento por programa, episodio y plataforma una vez que haya contenido publicado.' },
    audiencia: { title: 'Audiencia', icon: 'users', description: 'Quién consume el contenido: demografía, comportamiento, fidelización.' },
    publicacion: { title: 'Publicación', icon: 'send', description: 'Prepara, valida, programa y publica en YouTube, Spotify, Instagram, Facebook y TikTok.' },
    configuracion: { title: 'Configuración', icon: 'gear', description: 'Proveedores de IA, voces, publicación, almacenamiento y seguridad.' },
  };

  let activeView = $state('panel');
  let sidebarCollapsed = $state(false);
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
</script>

<svelte:head>
  <meta name="description" content="Kronara Studio -- autonomous editorial operating system" />
</svelte:head>

<div class="flex h-screen bg-bg text-ink">
  <Sidebar
    {activeView}
    bind:collapsed={sidebarCollapsed}
    systemHealthy={operations.connection === 'connected'}
    onNavigate={(id) => (activeView = id)}
  />

  <div class="flex min-w-0 flex-1 flex-col">
    <TopBar title={VIEW_META[activeView]?.title ?? 'Panel'} onOpenAssistant={() => (assistantOpen = true)} notificationCount={0} />

    <main class="flex-1 overflow-y-auto px-6 py-5">
      {#if activeView === 'panel'}
        <Panel {operations} {control} onNavigate={(id) => (activeView = id)} />
      {:else if activeView === 'programas'}
        <Programas />
      {:else if activeView === 'episodios'}
        <Episodios />
      {:else if activeView === 'calendario'}
        <Calendario />
      {:else if activeView === 'estudio'}
        <Estudio bind:operations connection={operations.connection} />
      {:else if activeView === 'configuracion'}
        <Configuracion />
      {:else}
        <StubView icon={VIEW_META[activeView]?.icon} title={VIEW_META[activeView]?.title} description={VIEW_META[activeView]?.description} />
      {/if}
    </main>
  </div>

  <AssistantPanel bind:open={assistantOpen} connection={operations.connection} />
</div>
