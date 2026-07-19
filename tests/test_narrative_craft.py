from kronara.narrative_craft import LiteraryCraftEvaluator


CLEAN_LITERARY = (
    "La lluvia golpeaba el techo de zinc mientras Mara sostenía la grabadora. "
    "El aire olía a tierra mojada y a cobre. Contó los latidos entre un crujido y el siguiente. "
    "Afuera, una silueta cruzó la penumbra; adentro, solo el zumbido del viejo casete. "
    "Guardó una copia. Cerró la puerta. No volvió a mirar atrás."
)

CLICHE_PILEUP = (
    "De repente, su corazón latía a mil. Sin previo aviso, la sangre se le heló y un "
    "escalofrío le recorrió la espalda. Lágrimas rodaron por sus mejillas mientras el "
    "tiempo se detuvo lentamente y trágicamente."
)

# Plain but clean, in the register of the deterministic golden fixture.
FIXTURE_STYLE = (
    "Mara no espera permiso. Mara recibe el audio incompleto; por eso decide restaurarlo "
    "a escondidas. Anota la hora, conserva una copia verificable y compara cada ruido antes "
    "de avanzar. La decisión acerca la verdad, pero también vuelve personal el conflicto "
    "sobre la lealtad. Cuando parece posible retroceder, una consecuencia concreta cierra esa salida."
)


def test_clean_literary_prose_passes_and_is_not_blocking():
    report = LiteraryCraftEvaluator().assess(CLEAN_LITERARY)
    assert report.blocking is False
    assert report.passed is True
    assert report.sensory_density > 0
    assert report.cliche_count == 0


def test_cliche_pileup_is_blocking():
    report = LiteraryCraftEvaluator().assess(CLICHE_PILEUP)
    assert report.cliche_count >= 2
    assert "cliche_pileup" in report.antipatterns
    assert report.blocking is True
    assert report.passed is False


def test_deterministic_fixture_style_text_is_never_blocked():
    # The golden StoryEngine fixture must keep passing once craft gating is wired in.
    report = LiteraryCraftEvaluator().assess(FIXTURE_STYLE)
    assert report.blocking is False


def test_adverb_overload_is_flagged():
    text = (
        "Caminó lentamente, habló suavemente, sonrió tímidamente, respondió rápidamente "
        "y finalmente se alejó silenciosamente y cuidadosamente."
    )
    report = LiteraryCraftEvaluator().assess(text)
    assert "adverb_overload" in report.antipatterns


def test_report_serializes_to_plain_dict():
    report = LiteraryCraftEvaluator().assess(CLEAN_LITERARY)
    data = report.as_dict()
    assert set(
        ["craft_score", "sensory_density", "antipatterns", "blocking", "passed"]
    ) <= set(data)
    assert isinstance(data["antipatterns"], list)
