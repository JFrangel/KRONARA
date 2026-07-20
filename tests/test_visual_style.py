import pytest

from kronara.visual_style import (
    VisualStyleDescriptor,
    VisualStyleRegistry,
    apply_style,
    default_registry_path,
)


def descriptor(**overrides) -> VisualStyleDescriptor:
    payload = dict(
        program_id="viernes-paranormal",
        display_name="Viernes Paranormal",
        weekday="viernes",
        style_prompt="dark blue and sickly green palette, fog, heavy grain",
        negative_prompt="bright colors, cheerful, cartoon",
        motion_bias="subtle",
        music_moods=("paranormal-tension",),
        asset_tags=("fog", "abandoned"),
    )
    payload.update(overrides)
    return VisualStyleDescriptor(**payload)


# ---- VisualStyleDescriptor validation ---------------------------------------


def test_descriptor_rejects_empty_style_prompt():
    with pytest.raises(ValueError):
        descriptor(style_prompt="   ")


def test_descriptor_rejects_unknown_motion_bias():
    with pytest.raises(ValueError):
        descriptor(motion_bias="chaotic")


# ---- VisualStyleRegistry.load (the real shipped config) ---------------------


def test_default_registry_loads_all_seven_programs():
    registry = VisualStyleRegistry.load(default_registry_path())
    assert len(registry.program_ids) == 7
    assert "viernes-paranormal" in registry.program_ids
    assert "cronicas-de-justicia" in registry.program_ids


def test_default_registry_program_ids_match_reddit_source_node_slugs():
    """The visual style registry and F0's Reddit source nodes must share the
    same program_id slugs (nodo-<slug>.md) so downstream code (later phases)
    can look up both by one identifier."""
    registry = VisualStyleRegistry.load(default_registry_path())
    expected = {
        "decisiones-dificiles",
        "confesiones-anonimas",
        "cronicas-de-justicia",
        "mentes-ocultas",
        "viernes-paranormal",
        "historias-medianoche",
        "caso-de-la-semana",
    }
    assert set(registry.program_ids) == expected


def test_registry_rejects_duplicate_program_id(tmp_path):
    import json

    payload = {
        "schema_version": 1,
        "programs": [
            {
                "program_id": "dup",
                "display_name": "A",
                "weekday": "lunes",
                "style_prompt": "x",
            },
            {
                "program_id": "dup",
                "display_name": "B",
                "weekday": "martes",
                "style_prompt": "y",
            },
        ],
    }
    path = tmp_path / "dup.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        VisualStyleRegistry.load(path)


def test_get_unknown_program_id_raises():
    registry = VisualStyleRegistry.load(default_registry_path())
    with pytest.raises(KeyError):
        registry.get("not-a-real-program")


# ---- apply_style --------------------------------------------------------------


def test_apply_style_appends_program_style_to_base_prompt():
    style = descriptor()
    prompt, negative = apply_style("a woman stands in a hallway", "blurry", style)
    assert prompt == "a woman stands in a hallway, dark blue and sickly green palette, fog, heavy grain"
    assert negative == "blurry, bright colors, cheerful, cartoon"


def test_apply_style_with_none_style_returns_base_prompts_unchanged():
    prompt, negative = apply_style("a woman stands in a hallway", "blurry", None)
    assert prompt == "a woman stands in a hallway"
    assert negative == "blurry"


def test_two_programs_produce_visually_distinguishable_prompts():
    """The V3 acceptance criterion: the same base shot, rendered under two
    different programs, must produce different generation inputs."""
    registry = VisualStyleRegistry.load(default_registry_path())
    base_prompt = "a person stands at a doorway, evening light"
    paranormal_prompt, _ = apply_style(base_prompt, "", registry.get("viernes-paranormal"))
    justice_prompt, _ = apply_style(base_prompt, "", registry.get("cronicas-de-justicia"))
    assert paranormal_prompt != justice_prompt
    assert "fog" in paranormal_prompt or "green" in paranormal_prompt
    assert "documentary" in justice_prompt or "office" in justice_prompt
