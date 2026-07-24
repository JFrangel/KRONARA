import pytest

from kronara.agents import LEGACY_TO_SUPER, SUPER_AGENTS, super_agent


def test_there_are_exactly_three_super_agents():
    assert SUPER_AGENTS == ("estratega", "guionista", "productor")


@pytest.mark.parametrize(
    "legacy,expected",
    [
        ("executive_orchestrator", "estratega"),
        ("opportunity_intelligence", "estratega"),
        ("operations_chat", "estratega"),
        ("memory_curator", "estratega"),
        ("concept_architect", "guionista"),
        ("writer_room", "guionista"),
        ("automated_qc", "guionista"),
        ("rights_provenance", "guionista"),
        ("visual_director", "productor"),
        ("video_composer", "productor"),
        ("voice_director", "productor"),
        ("distribution", "productor"),
    ],
)
def test_legacy_ids_map_to_their_super_agent(legacy, expected):
    assert super_agent(legacy) == expected


def test_super_agent_is_idempotent_and_safe():
    # A super-agent maps to itself; an unknown id passes through unchanged.
    for name in SUPER_AGENTS:
        assert super_agent(name) == name
    assert super_agent("totally-unknown") == "totally-unknown"


def test_all_twenty_four_legacy_ids_collapse_into_the_three():
    assert len(LEGACY_TO_SUPER) == 24
    assert set(LEGACY_TO_SUPER.values()) == set(SUPER_AGENTS)
