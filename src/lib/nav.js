// Single source of truth for the sidebar's sections -- icons are inline
// SVG path data (no icon package dependency, matches the project's
// minimal-runtime-dependency stance).
//
// Episodios lives inside Programas (every episode belongs to a program, so
// it never needs its own top-level section -- see Programas.svelte's
// "Episodios" tab). Audiencia is folded into Analíticas: they're two lenses
// on the same underlying performance data, not two separate datasets.
export const PRINCIPAL_NAV = [
  { id: 'panel', label: 'Panel', icon: 'grid' },
  { id: 'programas', label: 'Programas', icon: 'film' },
  { id: 'calendario', label: 'Calendario', icon: 'calendar' },
  { id: 'estudio', label: 'Estudio', icon: 'wand' },
  { id: 'biblioteca', label: 'Biblioteca', icon: 'folder' },
  { id: 'agentes', label: 'Agentes', icon: 'cpu' },
  { id: 'analiticas', label: 'Analíticas', icon: 'chart' },
  { id: 'publicacion', label: 'Publicación', icon: 'send' },
  { id: 'configuracion', label: 'Configuración', icon: 'gear' },
];

export const CHANNELS = [
  { id: 'youtube', label: 'YouTube' },
  { id: 'spotify', label: 'Spotify' },
  { id: 'instagram', label: 'Instagram' },
  { id: 'facebook', label: 'Facebook' },
  { id: 'tiktok', label: 'TikTok' },
];
