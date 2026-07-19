"""Literary craft analysis for Spanish narration.

This module measures *prose quality* directly from the script text, independent of
the numeric critic scores handled by :mod:`kronara.narrative_quality`. It is
deterministic (regex + lexical heuristics, no model calls) so it can run as a
fast, auditable gate and produce observable metrics.

Design contract:
- ``NarrativeQualityEvaluator`` keeps its 11 numeric dimensions untouched. This
  is an *additional* layer (composition, not modification).
- ``assess()`` never blocks clean, plain prose. It only flags egregious craft
  antipatterns (cliché pile-ups, filter-word overload, flat "telling" of
  emotion, adverb overload, monotone rhythm, purple prose). The golden
  deterministic fixture, which is plain but clean, must pass.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field


# Spanish sensory lexicon (sight / sound / smell / taste / touch). Grounding a
# scene in the senses is the core of "show, don't tell".
_SENSORY_TERMS = (
    # vista
    "luz", "sombra", "brillo", "destello", "penumbra", "reflejo", "color",
    "oscuridad", "resplandor", "silueta", "borroso", "nítido", "grieta",
    # oído
    "ruido", "silencio", "eco", "susurro", "crujido", "golpe", "zumbido",
    "chirrido", "murmullo", "latido", "respiración", "voz",
    # olfato / gusto
    "olor", "aroma", "perfume", "humo", "polvo", "sabor", "amargo", "ácido",
    "dulce", "metálico", "tierra mojada",
    # tacto / cuerpo
    "frío", "calor", "húmedo", "áspero", "temblor", "sudor", "piel", "peso",
    "roce", "aliento", "pulso", "nudo en", "escalofrío",
)

# Filter words distance the reader from experience ("vio que llovía" vs "llovía").
_FILTER_PATTERNS = (
    r"\bvio que\b", r"\bvi que\b", r"\bviendo que\b",
    r"\bsinti[óo] que\b", r"\bsentir que\b", r"\bsintiendo que\b",
    r"\bnot[óo] que\b", r"\bse dio cuenta de que\b", r"\bdarse cuenta de que\b",
    r"\bpens[óo] que\b", r"\bpensando que\b", r"\bpareci[óo] que\b",
    r"\bparec[íi]a que\b", r"\bempez[óo] a\b", r"\bcomenz[óo] a\b",
    r"\bpudo ver\b", r"\bpod[íi]a ver\b", r"\bpudo o[íi]r\b",
    r"\bpudo sentir\b", r"\brecord[óo] que\b",
)

# Overused narrative clichés. Two or more is a pile-up and blocks.
_CLICHE_PATTERNS = (
    r"coraz[óo]n (le )?lat[íi]a a mil", r"su coraz[óo]n se aceler|el coraz[óo]n se le aceler[óo]",
    r"(la )?sangre se (le )?hel[óo]", r"sangre helada",
    r"un escalofr[íi]o (le )?recorri[óo] (la|el|su)",
    r"sin previo aviso", r"\bde repente\b", r"de la nada",
    r"[ée]rase una vez", r"el destino (quiso|ten[íi]a)",
    r"l[áa]grimas (rodaron|corr[íi]an) por sus mejillas",
    r"silencio sepulcral", r"fr[íi]o glacial", r"a sangre fr[íi]a",
    r"su mundo se derrumb[óo]", r"el tiempo se detuvo",
    r"contra todo pron[óo]stico", r"con el alma en un hilo",
    r"un mar de l[áa]grimas", r"m[áa]s r[áa]pido que un rayo",
    r"blanco como (el papel|un fantasma|la nieve)",
    r"nunca imagin[óo] que", r"poco (se|se lo) imaginaba",
    r"lo que no sab[íi]a (era|es) que",
)

# Flatly *telling* emotion instead of dramatizing it.
_TELLING_PATTERNS = (
    r"\bestaba (muy )?(feliz|triste|enojad[oa]|asustad[oa]|furios[oa]|content[oa]|nervios[oa]|preocupad[oa])\b",
    r"\bse sinti[óo] (muy )?(feliz|triste|enojad[oa]|asustad[oa]|furios[oa]|content[oa]|nervios[oa])\b",
    r"\bten[íi]a (mucho )?miedo\b", r"\bestaba lleno de (ira|rabia|alegr[íi]a|tristeza)\b",
    r"\bsent[íi]a una (gran|profunda) (tristeza|alegr[íi]a|rabia|angustia)\b",
)


@dataclass(frozen=True)
class CraftReport:
    """Deterministic prose-quality snapshot of a narration script."""

    sentence_count: int
    word_count: int
    sensory_density: float          # sensory hits per sentence
    filter_word_ratio: float        # filter phrases per 100 words
    cliche_count: int
    telling_emotion_count: int
    adverb_ratio: float             # "-mente" adverbs per 100 words
    rhythm_variance: float          # stdev of sentence word-counts (prose music)
    dialogue_ratio: float           # share of lines that carry dialogue
    craft_score: float              # 0..10 composite
    passed: bool                    # advisory craft threshold
    blocking: bool                  # egregious failure → hard gate should stop
    antipatterns: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, object]:
        return {
            "sentence_count": self.sentence_count,
            "word_count": self.word_count,
            "sensory_density": round(self.sensory_density, 3),
            "filter_word_ratio": round(self.filter_word_ratio, 3),
            "cliche_count": self.cliche_count,
            "telling_emotion_count": self.telling_emotion_count,
            "adverb_ratio": round(self.adverb_ratio, 3),
            "rhythm_variance": round(self.rhythm_variance, 3),
            "dialogue_ratio": round(self.dialogue_ratio, 3),
            "craft_score": round(self.craft_score, 2),
            "passed": self.passed,
            "blocking": self.blocking,
            "antipatterns": list(self.antipatterns),
        }


class LiteraryCraftEvaluator:
    """Measures literary craft in narration text and flags craft antipatterns.

    Thresholds are tuned so that plain-but-clean prose passes and only genuinely
    poor craft (cliché pile-ups, filter/adverb overload, monotone rhythm, purple
    prose) is flagged. ``blocking`` is reserved for failures that should stop the
    pipeline; everything else is advisory and surfaced for observability.
    """

    def __init__(
        self,
        *,
        craft_threshold: float = 6.0,
        min_sensory_density: float = 0.15,
    ):
        self.craft_threshold = craft_threshold
        self.min_sensory_density = min_sensory_density

    def assess(self, text: str) -> CraftReport:
        normalized = text.strip()
        sentences = [s for s in re.split(r"(?<=[.!?…])\s+|\n+", normalized) if s.strip()]
        words = re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)
        word_count = len(words)
        sentence_count = max(1, len(sentences))
        lowered = normalized.casefold()

        sensory_hits = sum(lowered.count(term) for term in _SENSORY_TERMS)
        sensory_density = sensory_hits / sentence_count

        filter_hits = sum(len(re.findall(p, lowered)) for p in _FILTER_PATTERNS)
        filter_word_ratio = 100.0 * filter_hits / max(1, word_count)

        cliche_count = sum(1 for p in _CLICHE_PATTERNS if re.search(p, lowered))
        telling_count = sum(len(re.findall(p, lowered)) for p in _TELLING_PATTERNS)

        adverbs = re.findall(r"\b\w+mente\b", lowered)
        adverb_ratio = 100.0 * len(adverbs) / max(1, word_count)

        lengths = [len(re.findall(r"[^\W_]+", s, flags=re.UNICODE)) for s in sentences]
        rhythm_variance = statistics.pstdev(lengths) if len(lengths) > 1 else 0.0

        dialogue_lines = sum(
            1 for s in sentences if s.lstrip().startswith(("—", "-", "«", '"', "“"))
        )
        dialogue_ratio = dialogue_lines / sentence_count

        antipatterns: list[str] = []
        if cliche_count >= 2:
            antipatterns.append("cliche_pileup")
        if filter_word_ratio >= 3.0:
            antipatterns.append("filter_word_overload")
        if telling_count >= 2:
            antipatterns.append("telling_emotion")
        if adverb_ratio >= 6.0:
            antipatterns.append("adverb_overload")
        if word_count >= 60 and sentence_count >= 4 and rhythm_variance < 1.0:
            antipatterns.append("monotone_rhythm")
        if adverb_ratio >= 4.0 and cliche_count >= 1:
            antipatterns.append("purple_prose")

        craft_score = self._score(
            sensory_density=sensory_density,
            filter_word_ratio=filter_word_ratio,
            cliche_count=cliche_count,
            telling_count=telling_count,
            adverb_ratio=adverb_ratio,
            rhythm_variance=rhythm_variance,
        )

        # Blocking failures: egregious craft problems that should stop the run.
        blocking = "cliche_pileup" in antipatterns or "purple_prose" in antipatterns
        passed = craft_score >= self.craft_threshold and not blocking

        return CraftReport(
            sentence_count=sentence_count,
            word_count=word_count,
            sensory_density=sensory_density,
            filter_word_ratio=filter_word_ratio,
            cliche_count=cliche_count,
            telling_emotion_count=telling_count,
            adverb_ratio=adverb_ratio,
            rhythm_variance=rhythm_variance,
            dialogue_ratio=dialogue_ratio,
            craft_score=craft_score,
            passed=passed,
            blocking=blocking,
            antipatterns=tuple(antipatterns),
        )

    def detect_craft_antipatterns(self, text: str) -> tuple[str, ...]:
        """Convenience: just the antipattern codes for a piece of text."""
        return self.assess(text).antipatterns

    @staticmethod
    def _score(
        *,
        sensory_density: float,
        filter_word_ratio: float,
        cliche_count: int,
        telling_count: int,
        adverb_ratio: float,
        rhythm_variance: float,
    ) -> float:
        score = 7.0
        score += min(1.5, sensory_density * 2.0)          # reward the senses
        score += min(1.0, rhythm_variance / 6.0)           # reward prose music
        score -= min(3.0, filter_word_ratio)               # punish filtering
        score -= 1.2 * cliche_count                        # punish clichés
        score -= 0.6 * telling_count                       # punish telling
        score -= min(2.0, max(0.0, adverb_ratio - 2.0) * 0.5)  # punish adverb spam
        return max(0.0, min(10.0, score))
