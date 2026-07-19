from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class VoiceProfile:
    voice_id: str
    locale: str
    gender: str
    provider: str
    production_stable: bool


DEFAULT_VOICES = (
    VoiceProfile("es-BO-MarceloNeural", "es-BO", "male", "azure", True),
    VoiceProfile("es-CL-LorenzoNeural", "es-CL", "male", "azure", True),
    VoiceProfile("es-BO-SofiaNeural", "es-BO", "female", "azure", True),
    VoiceProfile("es-CO-GonzaloNeural", "es-CO", "male", "azure", True),
    VoiceProfile("es-CO-SalomeNeural", "es-CO", "female", "azure", True),
)


class VoiceRegistry:
    def __init__(self, voices: Iterable[VoiceProfile]):
        self._voices = {voice.voice_id: voice for voice in voices}

    def get(self, voice_id: str) -> VoiceProfile:
        try:
            return self._voices[voice_id]
        except KeyError as error:
            raise LookupError(voice_id) from error

