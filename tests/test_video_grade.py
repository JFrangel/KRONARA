import pytest

from kronara.video_grade import documentary_grade, grade_key_for


def test_default_grade_is_subtle_and_ends_in_yuv420p():
    grade = documentary_grade()
    assert "eq=" in grade and "vignette" in grade
    assert grade.endswith("format=yuv420p")  # playback-safe pixel format


@pytest.mark.parametrize(
    "program,expected_key",
    [
        ("Viernes Paranormal", "terror"),
        ("Historias de Medianoche", "terror"),
        ("Analog Horror / VHS", "analog"),
        ("Confesiones Anonimas", "intimo"),
        ("Cronicas de Justicia", "investigativo"),
        ("El Caso de la Semana", "investigativo"),
        ("Algo sin palabra clave", "default"),
    ],
)
def test_program_maps_to_expected_grade(program, expected_key):
    assert grade_key_for(program) == expected_key


def test_terror_grade_adds_film_grain_and_desaturates():
    terror = documentary_grade("terror")
    assert "noise=" in terror  # visible film grain
    assert "saturation=0.82" in terror  # colder / desaturated


def test_unknown_mood_falls_back_to_default():
    assert documentary_grade("no-existe") == documentary_grade("default")
