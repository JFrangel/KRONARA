import pytest

from kronara.programs import ProgramDescriptor, ProgramRegistry, default_registry_path


def descriptor(**overrides) -> ProgramDescriptor:
    payload = dict(
        program_id="viernes-paranormal",
        name="Viernes Paranormal",
        weekday="viernes",
        genre="Terror y fenomenos sobrenaturales",
        description="...",
        visual_style_id="viernes-paranormal",
        target_duration_seconds=120,
        platforms=("youtube", "facebook"),
    )
    payload.update(overrides)
    return ProgramDescriptor(**payload)


def test_descriptor_rejects_short_target_duration():
    with pytest.raises(ValueError):
        descriptor(target_duration_seconds=10)


def test_default_registry_loads_all_seven_programs():
    registry = ProgramRegistry.load(default_registry_path())
    assert len(registry.program_ids) == 7
    assert "viernes-paranormal" in registry.program_ids


def test_default_registry_program_ids_match_visual_style_program_ids():
    """programs.v1.json and visual_style.v1.json must share program_id slugs
    so a program's visual identity always resolves."""
    from kronara.visual_style import VisualStyleRegistry, default_registry_path as visual_style_path

    programs = ProgramRegistry.load(default_registry_path())
    styles = VisualStyleRegistry.load(visual_style_path())
    assert set(programs.program_ids) == set(styles.program_ids)


def test_by_weekday_returns_the_right_program():
    registry = ProgramRegistry.load(default_registry_path())
    assert registry.by_weekday("viernes").program_id == "viernes-paranormal"
    assert registry.by_weekday("domingo").program_id == "caso-de-la-semana"


def test_by_weekday_returns_none_for_unknown_day():
    registry = ProgramRegistry.load(default_registry_path())
    assert registry.by_weekday("not-a-day") is None


def test_get_unknown_program_id_raises():
    registry = ProgramRegistry.load(default_registry_path())
    with pytest.raises(KeyError):
        registry.get("not-a-real-program")


def test_registry_rejects_duplicate_program_id(tmp_path):
    import json

    payload = {
        "schema_version": 1,
        "programs": [
            {"program_id": "dup", "name": "A", "weekday": "lunes", "genre": "x",
             "target_duration_seconds": 90},
            {"program_id": "dup", "name": "B", "weekday": "martes", "genre": "y",
             "target_duration_seconds": 90},
        ],
    }
    path = tmp_path / "dup.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        ProgramRegistry.load(path)
