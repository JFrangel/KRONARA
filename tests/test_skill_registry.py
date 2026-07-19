import pytest

from kronara.skills import SkillRegistry, SkillSpec


def test_registry_selects_smallest_relevant_skill_set():
    registry = SkillRegistry(
        [
            SkillSpec("narrative_planning", 1, ("plan_story", "structure_scenes")),
            SkillSpec("originality_guard", 1, ("check_originality",)),
            SkillSpec("voice_direction", 1, ("select_voice",)),
        ]
    )

    selected = registry.select(("plan_story", "check_originality"))

    assert [skill.skill_id for skill in selected] == [
        "narrative_planning",
        "originality_guard",
    ]


def test_registry_rejects_duplicate_skill_versions():
    with pytest.raises(ValueError, match="duplicate skill"):
        SkillRegistry(
            [
                SkillSpec("writer", 1, ("write",)),
                SkillSpec("writer", 1, ("rewrite",)),
            ]
        )


def test_registry_fails_closed_when_capability_is_missing():
    registry = SkillRegistry([SkillSpec("writer", 1, ("write",))])

    with pytest.raises(LookupError, match="unsupported capabilities"):
        registry.select(("publish",))


def test_operations_skills_do_not_grant_tools_or_authority():
    skill = SkillSpec(
        "operations_chat",
        1,
        ("answer_operation_question",),
        instruction_uri="kronara://skills/operations-chat",
    )

    assert not hasattr(skill, "allowed_tools")
    assert not hasattr(skill, "permissions")
