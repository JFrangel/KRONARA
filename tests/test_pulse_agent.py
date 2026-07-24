from kronara.pulse_agent import analyze_performance, trend_brief


class FakeRouter:
    def __init__(self, payloads):
        self.calls = []
        self._payloads = payloads

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return self._payloads[kwargs["task"]]


def test_analyze_performance_returns_actionable_recommendations():
    router = FakeRouter({"pulse.performance": {
        "what_works": ["Los ganchos de contradicción retienen más"],
        "what_to_change": ["Acortar la intro a <3s"],
        "title_formulas": ["[Consecuencia] por [detalle mínimo]"],
        "next_topics": ["herencias en disputa"],
    }})
    result = analyze_performance(router, episodes=[
        {"title": "El recibo de 3 dólares", "views": 12000, "retention": 0.62, "hook": "contradicción"},
    ], program="Cronicas de Justicia")
    assert result["status"] == "ok"
    assert result["what_works"] and result["title_formulas"] and result["next_topics"]
    call = router.calls[0]
    assert call["task"] == "pulse.performance"
    assert call["input_payload"]["episodes"][0]["views"] == 12000


def test_analyze_performance_no_data_without_metrics():
    result = analyze_performance(FakeRouter({}), episodes=[])
    assert result["status"] == "no_data"


def test_trend_brief_extracts_formulas_from_samples():
    router = FakeRouter({"pulse.trends": {
        "patterns": ["Abren con una cifra concreta"],
        "title_formulas": ["Durante [N años], [anomalía]"],
        "angles_to_try": ["objeto misterioso"],
        "avoid": ["'no creerás'"],
    }})
    result = trend_brief(router, samples=[
        {"title": "Durante 4 años alguien pagó sus facturas", "platform": "tiktok", "views": 900000},
    ], niche="casos reales")
    assert result["status"] == "ok"
    assert result["title_formulas"] and result["avoid"]
    assert router.calls[0]["input_payload"]["niche"] == "casos reales"


def test_trend_brief_no_data_without_samples():
    assert trend_brief(FakeRouter({}), samples=[])["status"] == "no_data"


def test_agents_degrade_without_crashing_on_model_failure():
    class Boom:
        def complete(self, **kwargs):
            raise RuntimeError("down")

    assert analyze_performance(Boom(), episodes=[{"title": "x"}])["status"] == "error"
    assert trend_brief(Boom(), samples=[{"title": "y"}])["status"] == "error"
