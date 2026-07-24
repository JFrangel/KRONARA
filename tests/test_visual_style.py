import pytest

from kronara.visual_style import (
    StyleLibrary,
    VisualStyleDescriptor,
    VisualStyleRegistry,
    apply_style,
    default_registry_path,
    default_style_library_path,
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


# ---- StyleLibrary (v0.8 named style catalog) --------------------------------


def test_style_library_loads_all_ten_named_styles():
    library = StyleLibrary.load(default_style_library_path())
    assert len(library.list()) == 10
    expected = {
        "anime-neo-noir",
        "acuarela-melancolica",
        "comic-cinematografico",
        "low-poly-estilizado",
        "pixel-art-moderno",
        "recortes-de-papel",
        "analog-horror-vhs",
        "editorial-minimalista",
        "realismo-cinematografico-ilustrado",
        "diorama-isometrico",
    }
    assert set(library.style_ids) == expected


def test_named_style_bakes_in_universal_base_and_consistency():
    """Every named style must carry the registry-wide 9:16 base and the
    consistency note so each shot inherits them without build_shot_prompt
    knowing about them."""
    library = StyleLibrary.load(default_style_library_path())
    style = library.get("analog-horror-vhs")
    assert "vertical 9:16" in style.style_prompt
    assert "same visual style" in style.style_prompt.lower()
    assert "watermark" in style.negative_prompt


def test_named_style_works_with_apply_style_by_duck_typing():
    """A NamedVisualStyle exposes .style_prompt/.negative_prompt, so the same
    apply_style used for per-program styles composes it unchanged."""
    library = StyleLibrary.load(default_style_library_path())
    style = library.get("acuarela-melancolica")
    prompt, negative = apply_style("a woman by a window", "blurry", style)
    assert prompt.startswith("a woman by a window, melancholic digital watercolor")
    assert "blurry" in negative


def test_style_library_find_degrades_to_none_on_unknown_id():
    library = StyleLibrary.load(default_style_library_path())
    assert library.find("no-such-style") is None
    assert library.find(None) is None
    assert library.find("anime-neo-noir").style_id == "anime-neo-noir"


def test_two_named_styles_produce_distinguishable_prompts():
    """Fase 1 acceptance: two different styles over the same base shot must
    produce different generation inputs (distinct frames)."""
    library = StyleLibrary.load(default_style_library_path())
    base = "a person stands at a doorway"
    anime, _ = apply_style(base, "", library.get("anime-neo-noir"))
    watercolor, _ = apply_style(base, "", library.get("acuarela-melancolica"))
    assert anime != watercolor
    assert "neo-noir" in anime
    assert "watercolor" in watercolor


def test_style_library_rejects_duplicate_style_id():
    with pytest.raises(ValueError):
        StyleLibrary(
            (
                _named_style("dup"),
                _named_style("dup"),
            )
        )


def _named_style(style_id: str):
    from kronara.visual_style import NamedVisualStyle

    return NamedVisualStyle(
        style_id=style_id,
        name="Dup",
        identidad="",
        style_prompt="x",
        negative_prompt="",
        motion_bias="standard",
        music_moods=(),
        asset_tags=(),
    )


# ---- Custom styles: persistence + listing (Fase 1d) -------------------------

from kronara.visual_style import (  # noqa: E402
    StyleResolver,
    default_style_resolver,
    delete_custom_style,
    list_styles,
    read_custom_styles,
    upsert_custom_style,
)


def _valid_custom(**overrides) -> dict:
    payload = dict(
        style_id="mi-estilo-neon",
        name="Neón Personal",
        identidad="Prueba",
        style_prompt="glowing neon cyberpunk alley, custom user style",
        negative_prompt="daylight",
        motion_bias="dynamic",
        music_moods=["misterio-investigativo"],
        asset_tags=["neon"],
    )
    payload.update(overrides)
    return payload


def test_upsert_and_read_custom_style_roundtrip(tmp_path):
    path = tmp_path / "custom.json"
    saved = upsert_custom_style(path, _valid_custom())
    assert saved["style_id"] == "mi-estilo-neon"
    assert read_custom_styles(path)[0]["style_prompt"].startswith("glowing neon")


def test_read_custom_styles_missing_file_is_empty(tmp_path):
    assert read_custom_styles(tmp_path / "nope.json") == []
    assert read_custom_styles(None) == []


def test_upsert_rejects_invalid_motion_bias(tmp_path):
    with pytest.raises(ValueError):
        upsert_custom_style(tmp_path / "c.json", _valid_custom(motion_bias="chaotic"))


def test_upsert_rejects_missing_required_fields(tmp_path):
    with pytest.raises(ValueError):
        upsert_custom_style(tmp_path / "c.json", _valid_custom(style_prompt="   "))


def test_upsert_replaces_same_style_id(tmp_path):
    path = tmp_path / "custom.json"
    upsert_custom_style(path, _valid_custom(name="First"))
    upsert_custom_style(path, _valid_custom(name="Second"))
    rows = read_custom_styles(path)
    assert len(rows) == 1
    assert rows[0]["name"] == "Second"


def test_delete_custom_style(tmp_path):
    path = tmp_path / "custom.json"
    upsert_custom_style(path, _valid_custom())
    assert delete_custom_style(path, "mi-estilo-neon") is True
    assert read_custom_styles(path) == []
    assert delete_custom_style(path, "mi-estilo-neon") is False


def test_list_styles_tags_base_custom_and_override(tmp_path):
    base = default_style_library_path()
    custom = tmp_path / "custom.json"
    # A brand-new style plus an edit of a shipped one.
    upsert_custom_style(custom, _valid_custom())
    upsert_custom_style(
        custom, _valid_custom(style_id="anime-neo-noir", name="Mi Anime Editado")
    )
    rows = list_styles(base, custom)
    by_id = {row["style_id"]: row for row in rows}
    assert by_id["mi-estilo-neon"]["source"] == "custom"
    assert by_id["anime-neo-noir"]["source"] == "custom-override"
    assert by_id["anime-neo-noir"]["name"] == "Mi Anime Editado"
    # Untouched base styles stay tagged base.
    assert by_id["analog-horror-vhs"]["source"] == "base"


def test_load_merged_custom_style_is_resolvable_with_universal_base(tmp_path):
    custom = tmp_path / "custom.json"
    upsert_custom_style(custom, _valid_custom())
    resolver = default_style_resolver(custom_styles_path=custom)
    resolved = resolver.resolve(style_id="mi-estilo-neon")
    assert resolved is not None
    assert resolved.style_id == "mi-estilo-neon"
    # Universal base is composed onto the custom master prompt too.
    assert "vertical 9:16" in resolved.style_prompt


def test_load_merged_custom_override_shadows_base(tmp_path):
    custom = tmp_path / "custom.json"
    upsert_custom_style(
        custom,
        _valid_custom(style_id="anime-neo-noir", style_prompt="totally different look"),
    )
    resolver = default_style_resolver(custom_styles_path=custom)
    resolved = resolver.resolve(style_id="anime-neo-noir")
    assert resolved.style_prompt.startswith("totally different look")
