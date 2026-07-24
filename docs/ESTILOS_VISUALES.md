# Estilos visuales (Kronara v0.8, Fase 1)

Cada video se renderiza bajo **un** estilo visual: la estética (medio, paleta,
iluminación, composición) que comparten todas las escenas de un episodio para
que se lea como una sola historia y no como un collage de fotos sueltas.

## Los 10 estilos de fábrica

Viven en [`config/visual_styles/styles.v1.json`](../config/visual_styles/styles.v1.json).
Cada uno tiene `style_id`, `name`, `identidad` (para qué historias sirve, en
español), `style_prompt` y `negative_prompt` (en inglés, calibrados para Flux),
`motion_bias` (`subtle`/`standard`/`dynamic`), `music_moods` y `asset_tags`.

| style_id | Nombre | Para |
|---|---|---|
| `anime-neo-noir` | Anime Neo-Noir | Engaños, secretos, relaciones tóxicas |
| `acuarela-melancolica` | Acuarela Melancólica | Pérdida, amor, nostalgia, familia |
| `comic-cinematografico` | Cómic Cinematográfico | Conflicto, confrontaciones, giros |
| `low-poly-estilizado` | 3D Low-Poly Estilizado | Escalar producción, consistencia |
| `pixel-art-moderno` | Pixel Art Moderno | Terror, misterio, drama urbano |
| `recortes-de-papel` | Recortes de Papel | Relatos irónicos, humor, storytelling |
| `analog-horror-vhs` | Analog Horror / VHS | Paranormal, stalkers, desapariciones |
| `editorial-minimalista` | Ilustración Editorial Minimalista | Dilemas morales, culpa, psicología |
| `realismo-cinematografico-ilustrado` | Realismo Cinematográfico Ilustrado | Relatos serios, intensos, inmersivos |
| `diorama-isometrico` | Diorama Isométrico | Casa, oficina, vecinos, escenas paralelas |

### Base universal + consistencia

El archivo trae también `universal_base` (9:16, buena composición, personajes
consistentes), `universal_negative` (sin texto/marcas/manos deformes) y
`consistency_note`. `StyleLibrary` los **compone dentro** de cada `style_prompt` /
`negative_prompt` al cargar, así que cada toma los hereda sin que
`build_shot_prompt` tenga que saber de ellos.

Un estilo nombrado es un *master style* (`is_master_style == True`): su prompt ya
fija el medio (anime, acuarela, pixel art…). Por eso `visual_production.py`
**suprime** sus defaults fotográficos (`cinematic photograph`, `35mm film stock`)
cuando el estilo es master — si no, un episodio en pixel art terminaría empujado
hacia "película con grano".

## Cómo se elige el estilo de un episodio

`StyleResolver.resolve()` decide, de la señal más nueva a la más vieja
([`visual_style.py`](../python/kronara/visual_style.py)):

1. **Override por episodio**: `style_id` explícito (selector de Estudio o chat
   guiado) → se pasa en los `params` de `content.run`.
2. **Estilo del programa**: el `visual_style_id` configurado en
   [`programs.v1.json`](../config/programs/programs.v1.json).
3. **Fallback legacy**: el registro por-programa (`visual_style.v1.json`) si nada
   nombrado resuelve.

Un `style_id` desconocido degrada al estilo del programa en vez de romper la
corrida. Programa → estilo por defecto:

| Programa | Estilo |
|---|---|
| decisiones-dificiles | editorial-minimalista |
| confesiones-anonimas | acuarela-melancolica |
| cronicas-de-justicia | realismo-cinematografico-ilustrado |
| mentes-ocultas | anime-neo-noir |
| viernes-paranormal | analog-horror-vhs |
| historias-medianoche | pixel-art-moderno |
| caso-de-la-semana | comic-cinematografico |

## Estilos personalizados

En **Configuración → Estilos** puedes crear un estilo nuevo o editar uno de
fábrica (lo *sombrea* sin tocar el original). Se guardan en el `data_dir` de
runtime (`custom_visual_styles.v1.json`), nunca en el repo. RPCs:

- `styles.list` → base + personalizados, cada fila con `source`
  (`base` | `custom` | `custom-override`).
- `styles.upsert` → agrega o edita (valida como `NamedVisualStyle`).
- `styles.delete` → quita un custom; borrar un `custom-override` revierte al de
  fábrica.

Los estilos personalizados aparecen de inmediato en el selector de Estudio y en
el chat guiado (el resolver se reconstruye por corrida leyendo el `data_dir`), sin
reiniciar el sidecar.

## Imágenes solo por API (v0.8)

Por defecto las imágenes se generan con la **cascada API**: Pollinations →
Cloudflare Workers AI (Flux) → placeholder. El SDXL local (~7 min/imagen) **salió
del camino por defecto**; se reincorpora con:

- `KRONARA_IMAGE_PROVIDER=sdxl` — fuerza solo SDXL local.
- `KRONARA_ENABLE_SDXL=1` — lo agrega como último eslabón antes del placeholder.

Sin credenciales API la cascada resuelve a placeholder (rápido y honesto) en vez
de saturar la GPU.

## Chat guiado (≤5 preguntas)

Di *"quiero crear un video"* en el Asistente y el flujo pregunta, con opciones
clicables: **programa → estilo → duración**, y propone `create_episode` para tu
aprobación (nada se crea hasta aprobar). Si nombras el programa directamente
("crea un episodio de Viernes Paranormal") se mantiene el atajo de una sola
propuesta.
