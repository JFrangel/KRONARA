// Per-program visual identity for card art -- CSS gradients (never a fake
// stock photo standing in for a real thumbnail) derived directly from each
// program's actual style_prompt palette in config/programs/visual_style.v1.json,
// so a program's card art and its real generated episode art are describing
// the same visual world, not two unrelated aesthetic choices. Shared between
// Panel.svelte and Programas.svelte so a program's identity is consistent
// everywhere it appears.
export const PROGRAM_GRADIENTS = {
  'decisiones-dificiles': 'linear-gradient(155deg, #4a3520 0%, #2b2013 55%, #14100a 100%)',
  'confesiones-anonimas': 'linear-gradient(155deg, #3a1f3d 0%, #221226 55%, #120a15 100%)',
  'cronicas-de-justicia': 'linear-gradient(155deg, #263344 0%, #171f2b 55%, #0c1017 100%)',
  'mentes-ocultas': 'linear-gradient(155deg, #16302c 0%, #101f1e 55%, #090f0f 100%)',
  'viernes-paranormal': 'linear-gradient(155deg, #142d3a 0%, #1a2e1f 55%, #0a1210 100%)',
  'historias-medianoche': 'linear-gradient(155deg, #221a35 0%, #14101f 55%, #08060d 100%)',
  'caso-de-la-semana': 'linear-gradient(155deg, #2a3138 0%, #191f24 55%, #0d1013 100%)',
};

export const DEFAULT_PROGRAM_GRADIENT = 'linear-gradient(155deg, #241f38 0%, #151228 55%, #0a0815 100%)';

export function programGradient(programId) {
  return PROGRAM_GRADIENTS[programId] || DEFAULT_PROGRAM_GRADIENT;
}
