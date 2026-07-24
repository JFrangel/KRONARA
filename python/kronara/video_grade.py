"""Grade documental por programa/mood (edición de video).

Aplica un "look" con filtros ffmpeg para que el episodio parezca más documental:
contraste/curva, leve desaturación, viñeta y un grano de film sutil. Se aplica
como pasada aparte sobre el video ya compuesto (como la normalización de loudness),
así NO toca el filter_complex intrincado del render (zoompan+xfade).

``documentary_grade(mood)`` es puro (devuelve el string ``-vf``) -> testeable.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# Cada grade es una cadena de filtros -vf de ffmpeg. Sutil por defecto (no debe
# tapar la imagen); más marcado en terror/analog. Todos terminan en yuv420p para
# compatibilidad de reproducción.
_GRADES = {
    # Documental sobrio: contraste leve + desaturación mínima + viñeta suave.
    "default": "eq=contrast=1.05:saturation=0.95:gamma=0.98,vignette=PI/6,format=yuv420p",
    # Terror/paranormal: más frío, más contraste, viñeta y grano visible.
    "terror": "eq=contrast=1.12:saturation=0.82:gamma=0.94,curves=preset=darker,vignette=PI/4.5,noise=alls=7:allf=t,format=yuv420p",
    # Analog/VHS: verde-frío, grano fuerte, ligera pérdida.
    "analog": "eq=contrast=1.1:saturation=0.7,curves=b='0/0.05 1/0.95',vignette=PI/4.5,noise=alls=12:allf=t,format=yuv420p",
    # Emotivo/íntimo: cálido, suave, poco contraste.
    "intimo": "eq=contrast=1.02:saturation=1.02:gamma=1.03,vignette=PI/6.5,format=yuv420p",
    # Investigativo/justicia: neutro y limpio, contraste firme, sin grano.
    "investigativo": "eq=contrast=1.07:saturation=0.9,vignette=PI/6,format=yuv420p",
}

# Palabras del programa/estilo -> grade. Se busca por substring (case-insensitive).
_KEYWORD_TO_GRADE = {
    "paranormal": "terror",
    "terror": "terror",
    "medianoche": "terror",
    "analog": "analog",
    "vhs": "analog",
    "horror": "analog",
    "confesion": "intimo",
    "acuarela": "intimo",
    "melancol": "intimo",
    "justicia": "investigativo",
    "caso": "investigativo",
    "mentes": "investigativo",
    "documental": "investigativo",
}


def grade_key_for(program_or_style: str) -> str:
    text = (program_or_style or "").casefold()
    for keyword, key in _KEYWORD_TO_GRADE.items():
        if keyword in text:
            return key
    return "default"


def documentary_grade(mood: str = "default") -> str:
    """Cadena -vf de ffmpeg para el mood dado (o el default documental)."""
    return _GRADES.get(mood, _GRADES["default"])


def apply_grade(input_path: str, output_path: str, *, mood: str = "default", ffmpeg: str = "ffmpeg", timeout: int = 600) -> str:
    """Re-codifica el video aplicando el grade; copia el audio. Best-effort: el
    caller decide qué hacer si lanza (conservar el video sin grade)."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg, "-y", "-i", str(input_path), "-vf", documentary_grade(mood), "-c:a", "copy", str(output_path)],
        check=True,
        capture_output=True,
        timeout=timeout,
    )
    return str(output_path)
