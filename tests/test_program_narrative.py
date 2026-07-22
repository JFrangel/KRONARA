from kronara.program_narrative import narrative_contract, program_quality_findings


PROGRAM_IDS = (
    "decisiones-dificiles",
    "confesiones-anonimas",
    "cronicas-de-justicia",
    "mentes-ocultas",
    "viernes-paranormal",
    "historias-medianoche",
    "caso-de-la-semana",
)


def test_every_weekly_program_has_a_narrative_template():
    for program_id in PROGRAM_IDS:
        contract = narrative_contract(program_id)
        assert len(contract) >= 4
        assert program_id.split("-")[0].title() in contract[0] or "Programa" in contract[0]


def test_decisiones_dificiles_accepts_moral_dilemma_shape():
    text = (
        "Mi madre estaba en el hospital y mi hermana queria mantenerla conectada. "
        "Yo habia prometido elegir cuando el dolor fuera insoportable. Tome la decision, "
        "rompi a mi familia y desde entonces vivo con culpa."
    )

    assert program_quality_findings("decisiones-dificiles", text, (text,)) == ()


def test_decisiones_dificiles_blocks_unmotivated_paranormal_story():
    text = "Una entidad aparecio en una casa embrujada y una puerta se abrio sola."

    findings = program_quality_findings("decisiones-dificiles", text, (text,))

    assert "missing_decisiones-dificiles_core_signals" in findings
    assert "off_brand_decisiones-dificiles_elements" in findings


def test_viernes_paranormal_keeps_specific_failure_names():
    text = "Mateo mira un contrato azul en el muelle. El. Un."

    findings = program_quality_findings("viernes-paranormal", text, (text,))

    assert "missing_clear_paranormal_threat" in findings
    assert "fragmented_articles" in findings


def test_cronicas_de_justicia_accepts_evidence_to_consequence_arc():
    text = (
        "Guarde mensajes, correos y pruebas durante meses. Luego el abogado llevo la evidencia "
        "al juicio, la traicion quedo expuesta y la consecuencia fue inevitable."
    )

    assert program_quality_findings("cronicas-de-justicia", text, (text,)) == ()
