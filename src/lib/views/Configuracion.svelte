<script>
  import { onMount } from 'svelte';
  import Card from '../components/Card.svelte';
  import Badge from '../components/Badge.svelte';
  import Icon from '../components/Icon.svelte';
  import { callOperations } from '../local-operations.js';

  const TABS = ['general', 'ia', 'estilos', 'voces', 'publicacion', 'almacenamiento', 'seguridad'];
  const TAB_LABELS = {
    general: 'General', ia: 'IA y modelos', estilos: 'Estilos', voces: 'Voces', publicacion: 'Publicación',
    almacenamiento: 'Almacenamiento', seguridad: 'Seguridad',
  };
  const MOTION_BIASES = ['subtle', 'standard', 'dynamic'];
  const MOTION_LABELS = { subtle: 'Sutil', standard: 'Estándar', dynamic: 'Dinámico' };

  let activeTab = $state('general');
  let context = $state(null);
  let loadError = $state(false);

  // --- Estilos visuales (Fase 1d) ---
  let styles = $state([]);
  let stylesLoaded = $state(false);
  let stylesError = $state('');
  let styleNotice = $state('');
  let savingStyle = $state(false);
  const emptyForm = () => ({
    style_id: '', name: '', identidad: '', style_prompt: '',
    negative_prompt: '', motion_bias: 'standard', music_moods: '', asset_tags: '',
  });
  let form = $state(emptyForm());
  let editingId = $state(null); // null = creating; a style_id = editing that one

  async function loadStyles() {
    try {
      const result = await callOperations('styles.list', {});
      styles = result.styles ?? [];
      stylesError = '';
    } catch (error) {
      stylesError = 'No se pudo cargar la lista de estilos. ¿Está conectado Python?';
    } finally {
      stylesLoaded = true;
    }
  }

  function startNewStyle() {
    editingId = null;
    form = emptyForm();
    styleNotice = '';
  }

  function editStyle(style) {
    editingId = style.style_id;
    form = {
      style_id: style.style_id,
      name: style.name ?? '',
      identidad: style.identidad ?? '',
      style_prompt: style.style_prompt ?? '',
      negative_prompt: style.negative_prompt ?? '',
      motion_bias: MOTION_BIASES.includes(style.motion_bias) ? style.motion_bias : 'standard',
      music_moods: (style.music_moods ?? []).join(', '),
      asset_tags: (style.asset_tags ?? []).join(', '),
    };
    styleNotice = '';
  }

  function toList(text) {
    return String(text || '')
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
  }

  async function saveStyle() {
    if (savingStyle) return;
    if (!form.style_id.trim() || !form.name.trim() || !form.style_prompt.trim()) {
      styleNotice = 'ID, nombre y prompt del estilo son obligatorios.';
      return;
    }
    savingStyle = true;
    styleNotice = '';
    try {
      await callOperations('styles.upsert', {
        style_id: form.style_id.trim(),
        name: form.name.trim(),
        identidad: form.identidad.trim(),
        style_prompt: form.style_prompt.trim(),
        negative_prompt: form.negative_prompt.trim(),
        motion_bias: form.motion_bias,
        music_moods: toList(form.music_moods),
        asset_tags: toList(form.asset_tags),
      });
      await loadStyles();
      styleNotice = `Estilo "${form.name.trim()}" guardado. Se aplicará en la próxima generación.`;
      startNewStyle();
    } catch (error) {
      styleNotice = 'No se pudo guardar el estilo. Revisa que el sesgo de movimiento sea válido.';
    } finally {
      savingStyle = false;
    }
  }

  async function deleteStyle(style) {
    const question = `¿Quitar el estilo "${style.name}"?${
      style.source === 'custom-override' ? ' Volverá al estilo original de fábrica.' : ''
    }`;
    if (typeof window !== 'undefined' && window.confirm && !window.confirm(question)) return;
    try {
      await callOperations('styles.delete', { style_id: style.style_id });
      await loadStyles();
      if (editingId === style.style_id) startNewStyle();
      styleNotice = `Estilo "${style.name}" eliminado.`;
    } catch (error) {
      styleNotice = 'No se pudo eliminar el estilo.';
    }
  }

  const SOURCE_TONE = { base: 'neutral', custom: 'success', 'custom-override': 'warning' };
  const SOURCE_LABEL = { base: 'De fábrica', custom: 'Personalizado', 'custom-override': 'Editado' };

  // --- Voces (Fase 2: VoiceBox) ---
  // Cosecha de video-loops (Pexels): da movimiento real a las escenas (fuente
  // video_loop) en vez de solo imágenes fijas. Requiere KRONARA_PEXELS_ENABLED=1.
  let harvestingLoops = $state(false);
  let harvestReport = $state(null);
  let harvestError = $state('');

  async function harvestVideoLoops() {
    if (harvestingLoops) return;
    harvestingLoops = true;
    harvestReport = null;
    harvestError = '';
    try {
      const result = await callOperations('library.harvest_video_loops', {});
      if (result.status === 'library_unavailable') {
        harvestError = 'La biblioteca de assets no está disponible en esta sesión.';
      } else {
        harvestReport = result;
      }
    } catch (error) {
      harvestError = 'Pexels no respondió. Activa KRONARA_PEXELS_ENABLED=1 y revisa KRONARA_PEXELS_API_KEY.';
    } finally {
      harvestingLoops = false;
    }
  }

  let voiceInfo = $state(null);
  let voicesLoaded = $state(false);

  async function loadVoices() {
    try {
      voiceInfo = await callOperations('voice.profiles', {});
    } catch (error) {
      voiceInfo = { reachable: false, profiles: [], engines: [], base_url: '', configured_profile: '' };
    } finally {
      voicesLoaded = true;
    }
  }

  // --- Clonación de voces (Fase 3) ---
  let cloneForm = $state({ name: '', reference_text: '', engine: 'qwen', language: 'es' });
  let cloneFile = $state(null);
  let cloning = $state(false);
  let cloneNotice = $state('');
  let improvingProfile = $state(null); // when set, the form adds a sample to this voice
  let voiceSpeed = $state(1.0);

  const cloneEngines = $derived((voiceInfo?.engines ?? []).filter((e) => e.clone));

  async function loadVoiceSettings() {
    try {
      const s = await callOperations('voice.settings', {});
      voiceSpeed = s.speed ?? 1.0;
    } catch (error) {
      voiceSpeed = 1.0;
    }
  }

  async function saveVoiceSpeed(value) {
    voiceSpeed = value;
    try {
      await callOperations('voice.settings', { speed: value });
    } catch (error) {
      /* best-effort */
    }
  }

  function startImprove(profile) {
    improvingProfile = profile;
    cloneFile = null;
    cloneNotice = '';
  }

  function cancelImprove() {
    improvingProfile = null;
    cloneNotice = '';
  }

  function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = String(reader.result || '');
        const comma = result.indexOf(',');
        resolve(comma >= 0 ? result.slice(comma + 1) : result);
      };
      reader.onerror = () => reject(new Error('no se pudo leer el archivo'));
      reader.readAsDataURL(file);
    });
  }

  async function cloneVoice() {
    if (cloning) return;
    const needsName = !improvingProfile;
    if ((needsName && !cloneForm.name.trim()) || !cloneForm.reference_text.trim() || !cloneFile) {
      cloneNotice = improvingProfile
        ? 'Texto exacto y audio de referencia son obligatorios.'
        : 'Nombre, texto exacto y audio de referencia son obligatorios.';
      return;
    }
    cloning = true;
    cloneNotice = '';
    try {
      const audio_base64 = await readFileAsBase64(cloneFile);
      let result;
      if (improvingProfile) {
        result = await callOperations('voice.add_sample', {
          profile_id: improvingProfile.id,
          reference_text: cloneForm.reference_text.trim(),
          filename: cloneFile.name,
          audio_base64,
        });
      } else {
        result = await callOperations('voice.clone', {
          name: cloneForm.name.trim(),
          reference_text: cloneForm.reference_text.trim(),
          engine: cloneForm.engine,
          language: cloneForm.language,
          filename: cloneFile.name,
          audio_base64,
        });
      }
      if (result.status === 'created' || result.status === 'added') {
        voiceInfo = result;
        cloneNotice = improvingProfile
          ? `Muestra añadida a "${improvingProfile.name || improvingProfile.id}". La voz mejorará en la próxima narración.`
          : `Voz "${result.profile?.name ?? cloneForm.name.trim()}" clonada. Ya aparece en la lista.`;
        improvingProfile = null;
        cloneForm = { name: '', reference_text: '', engine: cloneForm.engine, language: cloneForm.language };
        cloneFile = null;
      } else if (result.reachable === false) {
        cloneNotice = 'VoiceBox no está corriendo. Arráncalo e inténtalo de nuevo.';
      } else {
        cloneNotice = `No se pudo: ${result.error ?? 'error desconocido'}`;
      }
    } catch (error) {
      cloneNotice = 'No se pudo completar la operación.';
    } finally {
      cloning = false;
    }
  }

  async function deleteProfile(profile) {
    const question = `¿Quitar la voz "${profile.name || profile.id}"? Los programas que la usen quedarán sin voz asignada.`;
    if (typeof window !== 'undefined' && window.confirm && !window.confirm(question)) return;
    try {
      const result = await callOperations('voice.delete_profile', { profile_id: profile.id });
      if (result.profiles !== undefined) voiceInfo = result;
    } catch (error) {
      cloneNotice = 'No se pudo quitar la voz.';
    }
  }

  onMount(async () => {
    try {
      context = await callOperations('operations.context', {});
    } catch (error) {
      loadError = true;
    }
    loadStyles();
    loadVoices();
    loadVoiceSettings();
  });

  const PROVIDERS = [
    { id: 'openrouter', label: 'OpenRouter (Qwen / Kimi / Nemotron / Hy3)', envVar: 'KRONARA_OPENROUTER_API_KEY' },
    { id: 'groq', label: 'Groq', envVar: 'KRONARA_GROQ_API_KEY' },
    { id: 'reddit', label: 'Reddit OAuth (opcional -- RSS funciona sin credenciales)', envVar: 'KRONARA_REDDIT_CLIENT_ID' },
    { id: 'meta', label: 'Meta (Facebook Reels)', envVar: 'KRONARA_META_PAGE_TOKEN' },
    { id: 'pexels', label: 'Pexels (video loops)', envVar: 'KRONARA_PEXELS_API_KEY' },
    { id: 'freesound', label: 'Freesound (música y SFX)', envVar: 'KRONARA_FREESOUND_ACCESS_TOKEN' },
  ];

  const CHANNELS = [
    { label: 'YouTube', icon: 'youtube', note: 'Video largo y Shorts' },
    { label: 'Spotify', icon: 'spotify', note: 'Podcast de audio' },
    { label: 'Instagram', icon: 'instagram', note: 'Reels y teasers' },
    { label: 'Facebook', icon: 'facebook', note: 'Video y comunidad' },
  ];
</script>

<div class="space-y-4">
  <div class="flex gap-1 overflow-x-auto border-b border-line">
    {#each TABS as tab}
      <button
        class="shrink-0 border-b-2 px-3 py-2 text-[12.5px] font-medium transition-colors"
        class:border-purple-500={activeTab === tab}
        class:text-ink={activeTab === tab}
        class:border-transparent={activeTab !== tab}
        class:text-ink-tertiary={activeTab !== tab}
        onclick={() => (activeTab = tab)}
      >
        {TAB_LABELS[tab]}
      </button>
    {/each}
  </div>

  {#if activeTab === 'general'}
    <div class="grid grid-cols-1 gap-4 xl:grid-cols-[1.1fr_1fr_1fr]">
      <Card title="Perfil del espacio" subtitle="Preferencias locales">
        <div class="flex items-center gap-3 rounded-xl border border-purple-500/25 bg-purple-500/10 p-3">
          <div class="grid h-11 w-11 place-items-center rounded-xl bg-purple-500/20 text-purple-300"><Icon name="wand" size={20} /></div>
          <div class="min-w-0">
            <p class="font-display text-base font-semibold text-ink">Kronara Studio</p>
            <p class="mt-0.5 text-[11px] text-ink-secondary">Estudio editorial local</p>
          </div>
          <Badge tone="success">Activo</Badge>
        </div>
        <dl class="mt-4 space-y-3 text-[12px]">
          <div class="flex items-center justify-between border-b border-line-subtle pb-2"><dt class="text-ink-tertiary">Idioma</dt><dd class="text-ink">Español (ES)</dd></div>
          <div class="flex items-center justify-between border-b border-line-subtle pb-2"><dt class="text-ink-tertiary">Zona horaria</dt><dd class="text-ink">UTC−05:00 Bogotá</dd></div>
          <div class="flex items-center justify-between"><dt class="text-ink-tertiary">Modo operativo</dt><dd class="text-purple-300">FULL AUTO</dd></div>
        </dl>
      </Card>

      <Card title="Preferencias de interfaz" subtitle="Diseño del estudio">
        <div class="space-y-3">
          <div class="flex items-center justify-between rounded-xl border border-line bg-surface-inset p-3">
            <div><p class="text-[12px] font-medium text-ink">Tema</p><p class="mt-0.5 text-[11px] text-ink-tertiary">Oscuro cinematográfico</p></div>
            <span class="rounded-lg border border-line px-2.5 py-1 text-[11px] text-ink-secondary">Oscuro</span>
          </div>
          <div class="flex items-center justify-between rounded-xl border border-line bg-surface-inset p-3">
            <div><p class="text-[12px] font-medium text-ink">Vista compacta</p><p class="mt-0.5 text-[11px] text-ink-tertiary">Más información por pantalla</p></div>
            <span class="relative h-5 w-9 rounded-full bg-purple-500"><span class="absolute right-1 top-1 h-3 w-3 rounded-full bg-white"></span></span>
          </div>
          <div class="flex items-center justify-between rounded-xl border border-line bg-surface-inset p-3">
            <div><p class="text-[12px] font-medium text-ink">Guardado automático</p><p class="mt-0.5 text-[11px] text-ink-tertiary">Protege cambios de producción</p></div>
            <span class="relative h-5 w-9 rounded-full bg-purple-500"><span class="absolute right-1 top-1 h-3 w-3 rounded-full bg-white"></span></span>
          </div>
        </div>
      </Card>

      <Card title="Estado del sistema" subtitle="Comprobación local">
        <div class="flex items-center gap-2 rounded-xl border border-success/25 bg-success/10 p-3">
          <span class="h-2 w-2 rounded-full bg-success"></span><span class="text-[12px] font-medium text-success">Interfaz operativa</span>
        </div>
        <div class="mt-3 grid grid-cols-3 gap-2 text-center">
          <div class="rounded-lg border border-line bg-surface-inset p-2"><p class="text-lg font-semibold text-ink">100%</p><p class="text-[10px] text-ink-tertiary">UI</p></div>
          <div class="rounded-lg border border-line bg-surface-inset p-2"><p class="text-lg font-semibold text-ink">D:</p><p class="text-[10px] text-ink-tertiary">Modelos</p></div>
          <div class="rounded-lg border border-line bg-surface-inset p-2"><p class="text-lg font-semibold text-ink">0</p><p class="text-[10px] text-ink-tertiary">Errores</p></div>
        </div>
        <p class="mt-3 text-[11px] leading-relaxed text-ink-tertiary">La generación visual local usa SDXL y conserva sus pesos en el disco D del proyecto.</p>
      </Card>

      <Card title="Motor visual y voz" subtitle="Producción de episodios">
        <div class="space-y-2.5">
          <div class="flex items-center gap-3 rounded-xl border border-line bg-surface-inset p-3"><div class="grid h-8 w-8 place-items-center rounded-lg bg-purple-500/15 text-purple-300"><Icon name="film" size={15} /></div><div><p class="text-[12px] font-medium text-ink">SDXL local</p><p class="text-[10.5px] text-ink-tertiary">RTX 4060 Ti · CUDA</p></div><Badge tone="success">Listo</Badge></div>
          <div class="flex items-center gap-3 rounded-xl border border-line bg-surface-inset p-3"><div class="grid h-8 w-8 place-items-center rounded-lg bg-ember-500/15 text-ember-400"><Icon name="wand" size={15} /></div><div><p class="text-[12px] font-medium text-ink">Narración local</p><p class="text-[10.5px] text-ink-tertiary">Fallback sin coste por episodio</p></div><Badge tone="neutral">Configurar</Badge></div>
        </div>
      </Card>

      <Card title="Publicación e integraciones" subtitle="Canales disponibles">
        <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {#each CHANNELS as channel}
            <div class="flex items-center gap-2.5 rounded-xl border border-line bg-surface-inset p-2.5"><div class="h-2 w-2 rounded-full bg-ink-tertiary"></div><div class="min-w-0"><p class="text-[11.5px] font-medium text-ink">{channel.label}</p><p class="truncate text-[10px] text-ink-tertiary">{channel.note}</p></div><span class="ml-auto text-[10px] text-ink-tertiary">Pendiente</span></div>
          {/each}
        </div>
        <p class="mt-3 text-[11px] text-ink-tertiary">Las credenciales se mantienen fuera de la interfaz y se leen desde el entorno local.</p>
      </Card>

      <Card title="Almacenamiento local" subtitle="Archivos y caché">
        <div class="rounded-xl border border-line bg-surface-inset p-3"><p class="text-[10px] uppercase tracking-wide text-ink-tertiary">Ruta de trabajo</p><p class="mt-1 truncate font-mono text-[11px] text-ink">D:\Proyecto Redit\.kronara</p></div>
        <div class="mt-3 flex items-center justify-between text-[11.5px]"><span class="text-ink-tertiary">Modelos SDXL</span><span class="text-success">Instalados</span></div>
        <div class="mt-2 h-1.5 rounded-full bg-line"><div class="h-full w-[42%] rounded-full bg-purple-500"></div></div>
      </Card>
    </div>
  {:else if activeTab === 'ia'}
    <Card title="Presupuesto" subtitle="operations.context -- dato real">
      {#if loadError}
        <p class="text-[13px] text-ink-secondary">No se pudo cargar. Inicia la web local y verifica que Python esté conectado.</p>
      {:else if context}
        <div class="flex items-center justify-between text-[13px]">
          <span class="text-ink-secondary">Disponible hoy</span>
          <span class="font-mono font-semibold text-ink">${context.budget_status.remaining_usd.toFixed(2)} / ${context.budget_status.maximum_usd.toFixed(2)}</span>
        </div>
        <div class="mt-2 h-1.5 rounded-full bg-line">
          <div
            class="h-full rounded-full bg-purple-500"
            style={`width:${(context.budget_status.remaining_usd / context.budget_status.maximum_usd) * 100}%`}
          ></div>
        </div>
      {:else}
        <p class="text-[13px] text-ink-secondary">Cargando…</p>
      {/if}
    </Card>

    <Card title="Proveedores" subtitle="Configurados vía .env -- todos gratuitos">
      <ul class="divide-y divide-line-subtle">
        {#each PROVIDERS as provider}
          <li class="flex items-center justify-between py-2.5">
            <div>
              <p class="text-[12.5px] text-ink">{provider.label}</p>
              <p class="mt-0.5 font-mono text-[11px] text-ink-tertiary">{provider.envVar}</p>
            </div>
            <Badge tone="neutral">Ver .env</Badge>
          </li>
        {/each}
      </ul>
      <p class="mt-3 text-[11.5px] text-ink-tertiary">
        La edición de credenciales desde esta pantalla (sin tocar .env a mano) todavía no está conectada. Por ahora, configúralas directamente en el archivo local `.env`.
      </p>
    </Card>
  {:else if activeTab === 'estilos'}
    <div class="grid grid-cols-1 gap-4 xl:grid-cols-[1.15fr_1fr]">
      <Card title="Estilos visuales" subtitle="Se aplican a cada video según el programa o tu elección">
        {#if stylesError}
          <p class="text-[13px] text-ink-secondary">{stylesError}</p>
        {:else if !stylesLoaded}
          <p class="text-[13px] text-ink-secondary">Cargando estilos…</p>
        {:else}
          <ul class="space-y-2">
            {#each styles as style (style.style_id)}
              <li class="flex items-start gap-3 rounded-xl border border-line bg-surface-inset p-3">
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2">
                    <p class="truncate text-[12.5px] font-medium text-ink">{style.name}</p>
                    <Badge tone={SOURCE_TONE[style.source] ?? 'neutral'}>{SOURCE_LABEL[style.source] ?? style.source}</Badge>
                  </div>
                  <p class="mt-0.5 font-mono text-[10.5px] text-ink-tertiary">{style.style_id}</p>
                  {#if style.identidad}
                    <p class="mt-1 line-clamp-2 text-[11px] leading-relaxed text-ink-secondary">{style.identidad}</p>
                  {/if}
                </div>
                <div class="flex shrink-0 flex-col gap-1">
                  <button
                    class="rounded-lg border border-line px-2.5 py-1 text-[11px] text-ink-secondary transition-colors hover:text-ink"
                    onclick={() => editStyle(style)}
                  >
                    {style.source === 'base' ? 'Ajustar' : 'Editar'}
                  </button>
                  {#if style.source !== 'base'}
                    <button
                      class="rounded-lg border border-error/25 px-2.5 py-1 text-[11px] text-error transition-colors hover:bg-error/10"
                      onclick={() => deleteStyle(style)}
                    >
                      Quitar
                    </button>
                  {/if}
                </div>
              </li>
            {/each}
          </ul>
        {/if}
      </Card>

      <Card
        title={editingId ? 'Editar estilo' : 'Nuevo estilo'}
        subtitle={editingId ? `Editando: ${editingId}` : 'Crea un estilo visual personalizado'}
      >
        <div class="space-y-3">
          <label class="block">
            <span class="text-[11px] text-ink-tertiary">ID del estilo (sin espacios)</span>
            <input
              class="mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2 font-mono text-[12px] text-ink outline-none focus:border-purple-500 disabled:opacity-60"
              placeholder="mi-estilo-personal"
              bind:value={form.style_id}
              disabled={editingId !== null}
            />
          </label>
          <label class="block">
            <span class="text-[11px] text-ink-tertiary">Nombre</span>
            <input class="mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2 text-[12px] text-ink outline-none focus:border-purple-500" placeholder="Mi Estilo" bind:value={form.name} />
          </label>
          <label class="block">
            <span class="text-[11px] text-ink-tertiary">Identidad (para qué historias sirve)</span>
            <input class="mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2 text-[12px] text-ink outline-none focus:border-purple-500" placeholder="Drama íntimo, nostalgia, pérdida…" bind:value={form.identidad} />
          </label>
          <label class="block">
            <span class="text-[11px] text-ink-tertiary">Prompt del estilo (inglés recomendado para Flux)</span>
            <textarea class="mt-1 h-24 w-full resize-y rounded-lg border border-line bg-surface px-3 py-2 text-[12px] text-ink outline-none focus:border-purple-500" placeholder="cinematic illustration, soft light, muted palette…" bind:value={form.style_prompt}></textarea>
          </label>
          <label class="block">
            <span class="text-[11px] text-ink-tertiary">Prompt negativo (opcional)</span>
            <input class="mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2 text-[12px] text-ink outline-none focus:border-purple-500" placeholder="blurry, deformed hands…" bind:value={form.negative_prompt} />
          </label>
          <div class="grid grid-cols-2 gap-3">
            <label class="block">
              <span class="text-[11px] text-ink-tertiary">Movimiento</span>
              <select class="mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2 text-[12px] text-ink outline-none focus:border-purple-500" bind:value={form.motion_bias}>
                {#each MOTION_BIASES as bias}
                  <option value={bias}>{MOTION_LABELS[bias]}</option>
                {/each}
              </select>
            </label>
            <label class="block">
              <span class="text-[11px] text-ink-tertiary">Etiquetas (coma)</span>
              <input class="mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2 text-[12px] text-ink outline-none focus:border-purple-500" placeholder="neon, urban-night" bind:value={form.asset_tags} />
            </label>
          </div>
          {#if styleNotice}
            <p class="text-[11.5px] text-purple-300">{styleNotice}</p>
          {/if}
          <div class="flex items-center gap-2">
            <button
              class="rounded-lg bg-purple-500 px-4 py-2 text-[12px] font-medium text-white transition-colors hover:bg-purple-400 disabled:opacity-60"
              onclick={saveStyle}
              disabled={savingStyle}
            >
              {savingStyle ? 'Guardando…' : editingId ? 'Guardar cambios' : 'Crear estilo'}
            </button>
            {#if editingId}
              <button class="rounded-lg border border-line px-4 py-2 text-[12px] text-ink-secondary transition-colors hover:text-ink" onclick={startNewStyle}>
                Cancelar
              </button>
            {/if}
          </div>
        </div>
      </Card>
    </div>

    <Card title="Video-loops (animación)" subtitle="Metraje real en movimiento de Pexels para las escenas — no solo imágenes fijas">
      <div class="flex flex-wrap items-center gap-3">
        <button
          class="rounded-full bg-purple-500 px-5 py-2.5 text-[13px] font-medium text-ink transition-colors hover:bg-purple-600 disabled:cursor-not-allowed disabled:opacity-40"
          onclick={harvestVideoLoops}
          disabled={harvestingLoops}
        >
          {harvestingLoops ? 'Cosechando de Pexels…' : 'Cosechar video-loops'}
        </button>
        <p class="text-[11.5px] text-ink-tertiary">
          Descarga clips verticales por mood (noche, lluvia, niebla…) y los siembra con su licencia
          <a class="text-purple-300 hover:underline" href="https://www.pexels.com/license/" target="_blank" rel="noopener noreferrer">Pexels</a>.
          Requiere <code class="text-purple-300">KRONARA_PEXELS_ENABLED=1</code>.
        </p>
      </div>
      {#if harvestError}
        <p class="mt-3 rounded-lg border border-error/30 bg-error/10 px-3 py-2 text-[12px] text-error">{harvestError}</p>
      {/if}
      {#if harvestReport}
        <div class="mt-3 border-t border-line pt-3">
          <p class="text-[12px] text-ink">Sembrados <strong class="text-ink">{harvestReport.seeded}</strong> loop(s) nuevo(s).</p>
          <div class="mt-2 flex flex-wrap gap-1.5">
            {#each harvestReport.reports ?? [] as row}
              <span class={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] ${row.status === 'seeded' ? 'border-success text-success' : row.status === 'duplicate' ? 'border-line text-ink-secondary' : 'border-line text-ink-tertiary'}`}>
                {row.tag}: {row.status}
              </span>
            {/each}
          </div>
        </div>
      {/if}
    </Card>
  {:else if activeTab === 'voces'}
    <div class="grid grid-cols-1 gap-4 xl:grid-cols-[1.1fr_1fr]">
    <Card title="Motor de voz — VoiceBox" subtitle="Voz clonada, auto-hospedada (reemplaza edge-tts)">
      {#if !voicesLoaded}
        <p class="text-[13px] text-ink-secondary">Comprobando el servidor VoiceBox…</p>
      {:else if voiceInfo?.reachable}
        <div class="flex items-center gap-2 rounded-xl border border-success/25 bg-success/10 p-3">
          <span class="h-2 w-2 rounded-full bg-success"></span>
          <span class="text-[12px] font-medium text-success">VoiceBox conectado</span>
          <span class="ml-auto font-mono text-[11px] text-ink-tertiary">{voiceInfo.base_url}</span>
        </div>
        {#if voiceInfo.profiles?.length}
          <ul class="mt-3 space-y-2">
            {#each voiceInfo.profiles as profile (profile.id)}
              <li class="flex items-center gap-3 rounded-xl border border-line bg-surface-inset p-3">
                <div class="grid h-8 w-8 place-items-center rounded-lg bg-purple-500/15 text-purple-300"><Icon name="wand" size={15} /></div>
                <div class="min-w-0 flex-1">
                  <p class="truncate text-[12.5px] font-medium text-ink">{profile.name || profile.id}</p>
                  <p class="font-mono text-[10.5px] text-ink-tertiary">{profile.id}{profile.language ? ` · ${profile.language}` : ''}</p>
                </div>
                {#if profile.voice_type}<Badge tone="neutral">{profile.voice_type}</Badge>{/if}
                {#if profile.sample_count}<span class="text-[10px] text-ink-tertiary">{profile.sample_count} muestra{profile.sample_count === 1 ? '' : 's'}</span>{/if}
                {#if profile.id === voiceInfo.configured_profile}<Badge tone="success">Predeterminada</Badge>{/if}
                {#if profile.voice_type === 'cloned'}
                  <button
                    class="rounded-lg border border-purple-500/40 px-2 py-1 text-[11px] text-purple-200 transition-colors hover:bg-purple-500/10"
                    onclick={() => startImprove(profile)}
                    title="Añadir otra muestra para mejorar la voz"
                  >
                    Mejorar
                  </button>
                {/if}
                <button
                  class="rounded-lg border border-error/25 px-2 py-1 text-[11px] text-error transition-colors hover:bg-error/10"
                  onclick={() => deleteProfile(profile)}
                  title="Quitar voz"
                >
                  Quitar
                </button>
              </li>
            {/each}
          </ul>
        {:else}
          <p class="mt-3 text-[12px] text-ink-secondary">No hay voces todavía. Clona una abajo (sube unos segundos de audio con su texto exacto) y aparecerá aquí.</p>
        {/if}
        <p class="mt-3 text-[11px] text-ink-tertiary">La voz predeterminada por programa se fija con <code class="text-purple-300">KRONARA_VOICEBOX_PROFILE</code> en tu <code>.env</code> (usa el <span class="font-mono">id</span> de arriba).</p>
      {:else}
        <div class="flex items-center gap-2 rounded-xl border border-warning/25 bg-warning/10 p-3">
          <span class="h-2 w-2 rounded-full bg-warning"></span>
          <span class="text-[12px] font-medium text-warning">Servidor VoiceBox no detectado</span>
        </div>
        <div class="mt-3 space-y-2 text-[12px] text-ink-secondary">
          <p>VoiceBox es la voz principal (open source, MIT, corre en tu equipo). Para activarlo:</p>
          <ol class="ml-4 list-decimal space-y-1 text-[11.5px]">
            <li>Instala Python 3.12 (los paquetes ML no soportan 3.14 aún).</li>
            <li><code class="text-purple-300">git clone https://github.com/jamiepine/voicebox</code></li>
            <li>Crea el venv e instala <code>backend/requirements.txt</code>.</li>
            <li>Arranca solo el backend: <code class="text-purple-300">python -m uvicorn backend.main:app --port 17493</code></li>
            <li>Clona tu voz en la app y copia su <span class="font-mono">id</span> a <code class="text-purple-300">KRONARA_VOICEBOX_PROFILE</code>.</li>
          </ol>
          <p class="text-[11px] text-ink-tertiary">Detalle completo en <code>docs/VOICEBOX.md</code>. Mientras tanto, la generación no se cae: usa el estimador silencioso como respaldo anti-crash.</p>
        </div>
        <button class="mt-3 rounded-lg border border-line px-3 py-1.5 text-[11.5px] text-ink-secondary transition-colors hover:text-ink" onclick={loadVoices}>
          Reintentar conexión
        </button>
      {/if}
    </Card>

    <Card title="Voces y motores disponibles" subtitle="Qué puedes usar en VoiceBox">
      {#if voiceInfo?.engines?.length}
        <ul class="space-y-2">
          {#each voiceInfo.engines as engine (engine.id)}
            <li class="flex items-center gap-3 rounded-xl border border-line bg-surface-inset p-2.5">
              <div class="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-purple-500/15 text-purple-300"><Icon name="wand" size={13} /></div>
              <div class="min-w-0 flex-1">
                <p class="truncate text-[12px] font-medium text-ink">{engine.label}</p>
                <p class="truncate text-[10.5px] text-ink-tertiary">{engine.note}</p>
              </div>
              {#if engine.clone}
                <Badge tone="neutral">Clonable</Badge>
              {:else}
                <Badge tone="success">Sin clonar</Badge>
              {/if}
              {#if engine.id === voiceInfo.configured_engine}<Badge tone="warning">En uso</Badge>{/if}
            </li>
          {/each}
        </ul>
        <p class="mt-3 text-[11px] leading-relaxed text-ink-tertiary">
          Para español usa <span class="font-mono">qwen</span> (multilingüe) y clona tu voz, o <span class="font-mono">kokoro</span> para voces preset listas (inglés). El motor se fija con <code class="text-purple-300">KRONARA_VOICEBOX_ENGINE</code>.
        </p>
      {:else}
        <p class="text-[13px] text-ink-secondary">Cargando motores…</p>
      {/if}
    </Card>
    </div>

    {#if voiceInfo?.reachable}
      <Card
        title={improvingProfile ? `Mejorar "${improvingProfile.name || improvingProfile.id}"` : 'Clonar una voz'}
        subtitle={improvingProfile ? 'Añade otra muestra de audio + su texto exacto (más muestras = mejor voz)' : 'Sube unos segundos de audio + el texto exacto que dice'}
      >
        <div class="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {#if !improvingProfile}
          <label class="block">
            <span class="text-[11px] text-ink-tertiary">Nombre de la voz</span>
            <input class="mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2 text-[12px] text-ink outline-none focus:border-purple-500" placeholder="Voz narrador terror" bind:value={cloneForm.name} />
          </label>
          <div class="grid grid-cols-2 gap-3">
            <label class="block">
              <span class="text-[11px] text-ink-tertiary">Motor</span>
              <select class="mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2 text-[12px] text-ink outline-none focus:border-purple-500" bind:value={cloneForm.engine}>
                {#each cloneEngines as engine (engine.id)}
                  <option value={engine.id}>{engine.label}</option>
                {/each}
              </select>
            </label>
            <label class="block">
              <span class="text-[11px] text-ink-tertiary">Idioma</span>
              <select class="mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2 text-[12px] text-ink outline-none focus:border-purple-500" bind:value={cloneForm.language}>
                <option value="es">Español</option>
                <option value="en">Inglés</option>
                <option value="pt">Portugués</option>
                <option value="fr">Francés</option>
                <option value="it">Italiano</option>
                <option value="de">Alemán</option>
              </select>
            </label>
          </div>
          {/if}
          <label class="block lg:col-span-2">
            <span class="text-[11px] text-ink-tertiary">Audio de referencia (2–30 s · wav/mp3/m4a/ogg/flac)</span>
            <input
              type="file"
              accept="audio/*,.wav,.mp3,.m4a,.ogg,.flac,.aac,.webm,.opus"
              class="mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2 text-[12px] text-ink-secondary file:mr-3 file:rounded-md file:border-0 file:bg-purple-500/20 file:px-3 file:py-1 file:text-[11px] file:text-purple-200"
              onchange={(event) => (cloneFile = event.currentTarget.files?.[0] ?? null)}
            />
          </label>
          <label class="block lg:col-span-2">
            <span class="text-[11px] text-ink-tertiary">Texto exacto que se dice en el audio (obligatorio)</span>
            <textarea class="mt-1 h-20 w-full resize-y rounded-lg border border-line bg-surface px-3 py-2 text-[12px] text-ink outline-none focus:border-purple-500" placeholder="Escribe palabra por palabra lo que se dice en el audio de referencia." bind:value={cloneForm.reference_text}></textarea>
          </label>
        </div>
        {#if cloneNotice}
          <p class="mt-3 text-[11.5px] text-purple-300">{cloneNotice}</p>
        {/if}
        <div class="mt-3 flex items-center gap-2">
          <button
            class="rounded-lg bg-purple-500 px-4 py-2 text-[12px] font-medium text-white transition-colors hover:bg-purple-400 disabled:opacity-60"
            onclick={cloneVoice}
            disabled={cloning}
          >
            {cloning ? (improvingProfile ? 'Añadiendo…' : 'Clonando…') : improvingProfile ? 'Añadir muestra' : 'Clonar voz'}
          </button>
          {#if improvingProfile}
            <button class="rounded-lg border border-line px-4 py-2 text-[12px] text-ink-secondary transition-colors hover:text-ink" onclick={cancelImprove}>
              Cancelar
            </button>
          {:else}
            <span class="text-[11px] text-ink-tertiary">Puedes clonar varias voces; cada programa usará la que elijas.</span>
          {/if}
        </div>
      </Card>

      <Card title="Velocidad de la voz" subtitle="Aplica a la narración de todos los videos">
        <div class="flex items-center gap-4">
          <input
            type="range"
            min="0.5"
            max="2"
            step="0.05"
            value={voiceSpeed}
            class="h-1.5 flex-1 cursor-pointer accent-purple-500"
            oninput={(event) => saveVoiceSpeed(parseFloat(event.currentTarget.value))}
          />
          <span class="w-16 text-right font-mono text-[13px] text-ink">{voiceSpeed.toFixed(2)}×</span>
        </div>
        <div class="mt-1 flex justify-between text-[10.5px] text-ink-tertiary">
          <span>0.5× lento</span><span>1.0× normal</span><span>2.0× rápido</span>
        </div>
        <p class="mt-2 text-[11px] text-ink-tertiary">Se aplica con ffmpeg (mantiene el tono) sobre la narración generada. El cambio afecta la próxima generación.</p>
      </Card>
    {/if}
  {:else if activeTab === 'seguridad'}
    <Card title="Seguridad">
      <ul class="space-y-2 text-[12.5px] text-ink-secondary">
        <li>• Los secretos viven en `.env` local y no se muestran en la interfaz.</li>
        <li>• Cada acción con efectos externos pasa por una lista cerrada de métodos permitidos.</li>
        <li>• Las trazas de herramientas nunca incluyen el cuerpo de las señales externas (ej. texto de Reddit).</li>
      </ul>
    </Card>
  {:else}
    <Card title={TAB_LABELS[activeTab]}>
      <p class="text-[13px] text-ink-secondary">
        Esta pestaña necesita una ruta de RPC dedicada para leer/escribir configuración real -- todavía no conectada.
      </p>
    </Card>
  {/if}
</div>
