"""Biblioteca de ganchos (openings) para el guionista.

Identidad editorial: "No leemos historias de Reddit; reconstruimos casos que
aparecieron en Reddit". Cada gancho es un MECANISMO de oficio (evidencia,
contradicción, cuenta regresiva, dilema...), no una plantilla de texto: el
escritor construye una apertura ORIGINAL con los hechos concretos de la historia
y jamás copia un ejemplo.

Anti-eco por diseño: ``playbook()`` inyecta el mecanismo (nombre + cuándo usarlo
+ estructura) pero NUNCA el texto literal de los ejemplos -- el modelo aprende el
patrón sin ver jamás una frase copiable, así que no puede reproducir un ejemplo
que no recibe. Es la garantía más fuerte: la originalidad del pipeline compara el
guion COMPLETO contra sus referencias, de modo que una sola frase de apertura
copiada apenas movería la métrica; por eso el anti-eco vive en no exponer el
texto, no en la verificación posterior. ``example_texts()`` queda disponible por
si un chequeo futuro, específico de la apertura, quisiera usarlo.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from kronara.resource_root import resource_root


def _default_path() -> Path:
    return resource_root() / "config" / "hooks" / "hooks.v1.json"


def _normalize_key(value: str) -> str:
    """Programa/categoría -> clave snake sin acentos ('Viernes Paranormal' ->
    'viernes_paranormal') para casar con program_hints."""
    stripped = unicodedata.normalize("NFKD", value or "")
    ascii_only = "".join(ch for ch in stripped if not unicodedata.combining(ch))
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in ascii_only.lower())
    return "_".join(part for part in cleaned.split("_") if part)


@dataclass(frozen=True)
class HookLibrary:
    data: dict[str, Any]

    @property
    def philosophy(self) -> str:
        return str(self.data.get("philosophy", ""))

    def mechanisms(self) -> tuple[dict[str, Any], ...]:
        return tuple(self.data.get("mechanisms", ()))

    def preferred_mechanism_ids(self, program_id: str | None) -> tuple[str, ...]:
        """Los ids sugeridos para el programa (por program_hints); si no hay
        match, todos -- el modelo elige por selection_rules."""
        hints = self.data.get("program_hints", {})
        if program_id:
            key = _normalize_key(program_id)
            if key in hints:
                return tuple(hints[key])
            # match parcial: 'owned_viernes_paranormal_2026' contiene la clave
            for hint_key, ids in hints.items():
                if hint_key in key:
                    return tuple(ids)
        return tuple(m["id"] for m in self.mechanisms())

    def example_texts(self) -> tuple[str, ...]:
        """Todas las frases-ejemplo, para la referencia anti-copia de
        originalidad. Copiar un ejemplo hace fallar la originalidad."""
        out: list[str] = []
        for mech in self.mechanisms():
            out.extend(str(x) for x in mech.get("examples_illustrative", ()))
        return tuple(out)

    def playbook(
        self, *, program_id: str | None = None, avoid_mechanisms: tuple[str, ...] = ()
    ) -> dict[str, Any]:
        """Guía de oficio para inyectar en el prompt del concepto/gancho. NO
        incluye el texto de los ejemplos (anti-eco): solo mecanismo, cuándo y
        cómo. ``avoid_mechanisms`` son los usados en episodios recientes para no
        repetir el mismo mecanismo dos veces seguidas."""
        preferred = self.preferred_mechanism_ids(program_id)
        avoid = set(avoid_mechanisms)
        mechanisms = [
            {
                "id": m["id"],
                "name": m.get("name", m["id"]),
                "when_to_use": m.get("when_to_use", ""),
                "structure": m.get("structure", ""),
                "preferred_for_program": m["id"] in preferred,
                "avoid_now": m["id"] in avoid,
            }
            for m in self.mechanisms()
        ]
        return {
            "philosophy": self.philosophy,
            "usage_contract": list(self.data.get("usage_contract", ())),
            "preferred_mechanisms": list(preferred),
            "avoid_mechanisms": list(avoid_mechanisms),
            "mechanisms": mechanisms,
            "selection_rules": list(self.data.get("selection_rules", ())),
            "source_attribution_variations": list(self.data.get("source_attribution_variations", ())),
            "verifiability_disclaimers": list(self.data.get("verifiability_disclaimers", ())),
            "format_rules": self.data.get("format_rules", {}),
            "prohibitions": list(self.data.get("prohibitions", ())),
            "quality_rubric": self.data.get("quality_rubric", {}),
        }


@lru_cache(maxsize=4)
def load_hooks(path: str | None = None) -> HookLibrary:
    target = Path(path) if path else _default_path()
    data = json.loads(target.read_text(encoding="utf-8"))
    return HookLibrary(data=data)
