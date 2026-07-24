from kronara.social_agent import (
    PLATFORM_STYLE,
    draft_comment_reply,
    packaging_for_platforms,
    platform_packaging,
)


class FakeRouter:
    """Registra las llamadas y responde según la task, sin tocar la red."""

    def __init__(self, payloads):
        self.calls = []
        self._payloads = payloads

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return self._payloads[kwargs["task"]]


def test_platform_packaging_injects_platform_style_and_returns_fields():
    router = FakeRouter({"social.packaging": {
        "title": "La cámara en el detector de humo",
        "description": "Un hallazgo que nadie esperaba.",
        "hashtags": ["#caso", "#reddit", "#misterio"],
    }})
    result = platform_packaging(
        router, script="El protagonista encontró una cámara oculta...",
        base_title="Caso real", platform="tiktok", program="Cronicas de Justicia",
    )
    assert result["platform"] == "tiktok"
    assert result["title"]
    assert result["hashtags"] == ["#caso", "#reddit", "#misterio"]
    # The agent was told the platform + its style + the script.
    call = router.calls[0]
    assert call["task"] == "social.packaging"
    assert call["input_payload"]["platform"] == "tiktok"
    assert call["input_payload"]["platform_style"] == PLATFORM_STYLE["tiktok"]
    assert "cámara oculta" in call["input_payload"]["script"]


def test_packaging_for_platforms_produces_one_per_platform():
    router = FakeRouter({"social.packaging": {"title": "T", "description": "D", "hashtags": ["#a"]}})
    results = packaging_for_platforms(
        router, script="guion", base_title="base", platforms=["facebook", "instagram", "youtube"],
    )
    assert [r["platform"] for r in results] == ["facebook", "instagram", "youtube"]


def test_packaging_degrades_to_base_title_on_model_failure():
    class Boom:
        def complete(self, **kwargs):
            raise RuntimeError("model down")

    result = platform_packaging(Boom(), script="s", base_title="Título base", platform="facebook")
    assert result["title"] == "Título base"
    assert result["description"] == ""
    assert result["hashtags"] == []


def test_comment_reply_is_grounded_in_the_script():
    router = FakeRouter({"social.comment_reply": {
        "reply": "En el episodio, la cámara estaba en el detector de humo.",
        "grounded": True,
    }})
    result = draft_comment_reply(
        router, script="La cámara estaba escondida en el detector de humo.",
        comment="¿Dónde estaba la cámara?",
    )
    assert result["grounded"] is True
    assert "detector de humo" in result["reply"]
    call = router.calls[0]
    assert call["input_payload"]["comment"] == "¿Dónde estaba la cámara?"
    assert "detector de humo" in call["input_payload"]["script"]


def test_comment_reply_honest_when_script_lacks_the_answer():
    router = FakeRouter({"social.comment_reply": {
        "reply": "El episodio no menciona ese detalle, así que no puedo confirmarlo.",
        "grounded": False,
    }})
    result = draft_comment_reply(router, script="El caso trata de una herencia.", comment="¿De qué color era el auto?")
    assert result["grounded"] is False
    assert result["reply"]
