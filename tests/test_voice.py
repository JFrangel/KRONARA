from kronara.voice import DEFAULT_VOICES, VoiceRegistry


def test_required_latam_voices_are_registered():
    registry = VoiceRegistry(DEFAULT_VOICES)

    assert registry.get("es-BO-MarceloNeural").locale == "es-BO"
    assert registry.get("es-CL-LorenzoNeural").locale == "es-CL"
    assert registry.get("es-BO-SofiaNeural").gender == "female"

