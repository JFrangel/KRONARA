"""Audio mixing: deterministic ducking envelope, SFX cue matching, final mix.

Music ducking uses a piecewise-linear gain envelope computed in Python (not
`sidechaincompress` alone): the target reduction needs to be an *exact*,
reproducible number (per the product spec: music audibly present but clearly
under the narration), and this codebase's convention is that anything an
autonomous pipeline must hit a numeric target for is computed in code and
asserted in tests, not tuned by ear at render time. A light sidechaincompress
can still be layered on top purely for moment-to-moment texture; it is no
longer load-bearing for hitting the target once the envelope does the work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

# Narration word -> SFX tag. Curated, extensible (see knowledge/reddit-sources
# style curation notes for how the equivalent audio library is seeded).
DEFAULT_KEYWORD_SFX: dict[str, str] = {
    "puerta": "door_creak",
    "puertas": "door_creak",
    "pasos": "footsteps",
    "paso": "footsteps",
    "viento": "wind",
    "corazón": "heartbeat",
    "corazon": "heartbeat",
    "teléfono": "phone_ring",
    "telefono": "phone_ring",
    "página": "page_turn",
    "pagina": "page_turn",
    "páginas": "page_turn",
    "estática": "static",
    "estatica": "static",
    "susurro": "whisper",
    "susurra": "whisper",
    "susurró": "whisper",
    "susurraron": "whisper",
}

_WORD_STRIP_CHARS = ".,;:!?¡¿\"'()[]"


@dataclass(frozen=True)
class DuckingEnvelope:
    """Full volume before/after narration; ducked flat through the narrated
    span, with a short linear fade in/out at each transition."""

    narration_start_s: float
    narration_end_s: float
    duck_gain: float = 0.1  # ~-20dB; calibrated against real loudnorm in V4
    fade_s: float = 0.2

    def __post_init__(self) -> None:
        if self.narration_end_s <= self.narration_start_s:
            raise ValueError("narration_end_s must be after narration_start_s")
        if not 0.0 < self.duck_gain <= 1.0:
            raise ValueError("duck_gain must be in (0, 1]")
        if self.fade_s <= 0:
            raise ValueError("fade_s must be positive")

    @property
    def pre_roll_s(self) -> float:
        return max(0.0, self.narration_start_s)

    @property
    def duck_in_end_s(self) -> float:
        return self.pre_roll_s + self.fade_s

    @property
    def duck_out_start_s(self) -> float:
        return max(self.duck_in_end_s, self.narration_end_s - self.fade_s)

    @property
    def duck_out_end_s(self) -> float:
        return max(self.duck_out_start_s, self.narration_end_s)

    def as_ffmpeg_expression(self) -> str:
        """`eval=frame` volume expression: re-evaluated every frame against t."""
        return (
            f"if(lt(t,{self.pre_roll_s:.3f}),1.0,"
            f"if(lt(t,{self.duck_in_end_s:.3f}),"
            f"1.0-(1.0-{self.duck_gain:.4f})*(t-{self.pre_roll_s:.3f})/{self.fade_s:.3f},"
            f"if(lt(t,{self.duck_out_start_s:.3f}),{self.duck_gain:.4f},"
            f"if(lt(t,{self.duck_out_end_s:.3f}),"
            f"{self.duck_gain:.4f}+(1.0-{self.duck_gain:.4f})*"
            f"(t-{self.duck_out_start_s:.3f})/{self.fade_s:.3f},1.0))))"
        )

    def as_volume_filter(self, *, label_in: str, label_out: str) -> str:
        return f"[{label_in}]volume=eval=frame:volume='{self.as_ffmpeg_expression()}'[{label_out}]"


@dataclass(frozen=True)
class SfxCue:
    tag: str
    offset_ms: int
    word: str


def match_sfx_cues(
    word_boundaries: Sequence,
    *,
    cooldown_ms: int = 4000,
    max_cues: int = 15,
    keyword_map: Mapping[str, str] | None = None,
) -> tuple[SfxCue, ...]:
    """Anchor SFX to real word timings. `word_boundaries` carry GLOBAL offsets
    already (SceneDurationMeasurer accumulates offset across scenes), so this
    needs no scene-relative math. A per-tag cooldown avoids the same SFX
    firing twice in quick succession; max_cues bounds it to texture, not a
    sound-effects reel, and keeps the eventual filter_complex a sane size."""
    keywords = keyword_map or DEFAULT_KEYWORD_SFX
    cues: list[SfxCue] = []
    last_by_tag: dict[str, int] = {}
    for boundary in word_boundaries:
        word = getattr(boundary, "word", "")
        offset = getattr(boundary, "offset_ms", 0)
        normalized = word.strip(_WORD_STRIP_CHARS).casefold()
        tag = keywords.get(normalized)
        if tag is None:
            continue
        last = last_by_tag.get(tag, -cooldown_ms - 1)
        if offset - last < cooldown_ms:
            continue
        cues.append(SfxCue(tag=tag, offset_ms=offset, word=word))
        last_by_tag[tag] = offset
        if len(cues) >= max_cues:
            break
    return tuple(cues)


def build_mix_filters(
    *,
    music_envelope: DuckingEnvelope,
    sfx_cues: Sequence[SfxCue],
    sfx_input_labels: Mapping[str, str],
    sfx_gain: float = 0.032,
    narration_input: str = "0:a",
    music_input: str = "1:a",
    output_label: str = "mix",
) -> tuple[str, ...]:
    """Duck the music, delay+gain each SFX to its cue timestamp, then combine
    with `amix`. `normalize=0` is required — amix's default attenuates every
    stream by 1/N, which would flatten the carefully authored per-layer gains
    (narration full, music ducked ~-20dB, SFX ~-30dB — a clear ~10dB gap below
    music, not "also low"). `duration=first` uses the narration length; the
    alternative `shortest` would truncate the whole episode to a 1s SFX blip."""
    lines: list[str] = []
    music_env_label = "music_env"
    lines.append(music_envelope.as_volume_filter(label_in=music_input, label_out=music_env_label))

    sfx_labels: list[str] = []
    for index, cue in enumerate(sfx_cues):
        source = sfx_input_labels.get(cue.tag)
        if source is None:
            continue  # no asset for this tag in the library -> silently skip the cue
        out_label = f"sfx{index}"
        lines.append(
            f"[{source}]adelay={cue.offset_ms}|{cue.offset_ms},volume={sfx_gain:.4f}[{out_label}]"
        )
        sfx_labels.append(out_label)

    inputs = f"[{narration_input}][{music_env_label}]" + "".join(f"[{label}]" for label in sfx_labels)
    total_inputs = 2 + len(sfx_labels)
    lines.append(f"{inputs}amix=inputs={total_inputs}:normalize=0:duration=first[{output_label}]")
    return tuple(lines)
