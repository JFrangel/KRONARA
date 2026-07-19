import pytest

from kronara.graph_memory import KronaraGraph
from kronara.series import SeriesCanonBuilder, StoryPart


def builder(tmp_path):
    graph = KronaraGraph(tmp_path / "kg.db").initialize()
    return SeriesCanonBuilder(graph), graph


def test_non_final_part_requires_cliffhanger():
    with pytest.raises(ValueError):
        StoryPart("s1", 1, "story1", cliffhanger="", is_final=False)
    # Final part may end without a cliffhanger.
    StoryPart("s1", 3, "story3", cliffhanger="", is_final=True)


def test_part_two_inherits_part_one_canon(tmp_path):
    canon_builder, graph = builder(tmp_path)
    part1 = StoryPart("s1", 1, "story:part1", cliffhanger="¿Quién dejó la grabadora?")
    canon_builder.ingest(
        part1,
        characters=("Mara", "Tía Rosa"),
        facts=("Mara es restauradora", "El audio se conserva como evidencia"),
        now=100,
    )

    context = canon_builder.context_for_part("s1", next_part=2, now=200)

    assert "Mara" in context.established_characters
    assert "Tía Rosa" in context.established_characters
    assert "Mara es restauradora" in context.established_facts
    assert "¿Quién dejó la grabadora?" in context.open_threads
    assert "CANON DE LA SERIE" in context.context_block
    assert "Mara" in context.context_block
    graph.close()


def test_recurring_character_is_not_duplicated_across_parts(tmp_path):
    canon_builder, graph = builder(tmp_path)
    canon_builder.ingest(
        StoryPart("s1", 1, "p1", cliffhanger="gancho 1"), characters=("Mara",), facts=(), now=100
    )
    canon_builder.ingest(
        StoryPart("s1", 2, "p2", cliffhanger="gancho 2"), characters=("Mara",), facts=(), now=200
    )
    characters = [
        e for e in graph.canon("s1").entities if e.entity_type == "character"
    ]
    assert [c.name for c in characters] == ["Mara"]
    graph.close()


def test_ingest_from_story_result_object(tmp_path):
    canon_builder, graph = builder(tmp_path)

    class FakeScene:
        def __init__(self, characters):
            self.characters = characters

    class FakeContinuity:
        facts = ("Mara es restauradora",)

    class FakeResult:
        run_id = "story:owned_1"
        scenes = (FakeScene(("Mara",)), FakeScene(("Mara", "Testigo")))
        continuity = FakeContinuity()

    part = canon_builder.ingest_story_result(
        "s1", 1, FakeResult(), now=100, cliffhanger="¿Qué dijo el testigo?"
    )
    assert part.part_number == 1
    context = canon_builder.context_for_part("s1", next_part=2, now=150)
    assert set(context.established_characters) == {"Mara", "Testigo"}
    assert "Mara es restauradora" in context.established_facts
    graph.close()


def test_empty_series_context_is_marked_empty(tmp_path):
    canon_builder, graph = builder(tmp_path)
    context = canon_builder.context_for_part("unknown", next_part=1, now=100)
    assert context.is_empty()
    assert context.context_block == ""
    graph.close()
