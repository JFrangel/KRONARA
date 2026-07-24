import pytest

from kronara.hooks_library import HookLibrary, load_hooks


@pytest.fixture()
def library() -> HookLibrary:
    return load_hooks()


def test_library_loads_the_shipped_catalog(library):
    assert library.philosophy
    ids = [m["id"] for m in library.mechanisms()]
    # A representative spread of the documented mechanisms must be present.
    for expected in ("consequence_first", "impossible_contradiction", "moral_dilemma", "hidden_pattern"):
        assert expected in ids
    # Every mechanism carries the fields the playbook exposes.
    assert all(m.get("name") and m.get("when_to_use") and m.get("structure") for m in library.mechanisms())


@pytest.mark.parametrize(
    "program_id,expected",
    [
        ("Viernes Paranormal", "impossible_contradiction"),
        ("owned_viernes_paranormal_2026", "impossible_contradiction"),
        ("Mentes Ocultas", "hidden_pattern"),
        ("Crónicas de Justicia", "evidence_object"),
    ],
)
def test_program_hints_bias_the_preferred_mechanisms(library, program_id, expected):
    assert expected in library.preferred_mechanism_ids(program_id)


def test_unknown_program_falls_back_to_every_mechanism(library):
    preferred = library.preferred_mechanism_ids("totally-unknown-program")
    assert set(preferred) == {m["id"] for m in library.mechanisms()}


def test_playbook_never_leaks_example_text(library):
    # The anti-echo guarantee: the injected playbook exposes the mechanism but
    # NOT a single copyable example sentence.
    playbook = library.playbook(program_id="Viernes Paranormal")
    blob = repr(playbook)
    for example in library.example_texts():
        assert example not in blob
    # It does carry the craft fields the writer needs.
    assert playbook["philosophy"] and playbook["usage_contract"] and playbook["selection_rules"]
    assert all("when_to_use" in m and "structure" in m for m in playbook["mechanisms"])
    # Program bias is surfaced so the model knows which to prefer.
    assert any(m["preferred_for_program"] for m in playbook["mechanisms"])


def test_avoid_mechanisms_are_flagged_for_consecutive_variety(library):
    playbook = library.playbook(program_id="Viernes Paranormal", avoid_mechanisms=("impossible_contradiction",))
    flagged = [m["id"] for m in playbook["mechanisms"] if m["avoid_now"]]
    assert flagged == ["impossible_contradiction"]
    assert playbook["avoid_mechanisms"] == ["impossible_contradiction"]


def test_example_texts_are_available_for_a_future_opening_check(library):
    examples = library.example_texts()
    assert len(examples) >= 15
    assert all(isinstance(x, str) and x for x in examples)
