from kronara.store import KronaraStore
from kronara.story_engine import (
    DeterministicIndependentCritic,
    DeterministicStoryProvider,
    StoryBrief,
    StoryEngine,
)


def brief(story_id: str) -> StoryBrief:
    return StoryBrief(
        story_id=story_id,
        title="El audio que terminó antes de decir su nombre",
        premise="Una restauradora debe elegir entre una promesa y una verdad verificable.",
        theme="lealtad frente a verdad",
        target_duration_seconds=90,
        rights_mode="owned_original",
        source_uri=f"kronara://artifacts/{story_id}",
        evidence_refs=("ev_owned",),
    )


def engine(tmp_path, generator=None):
    store = KronaraStore(tmp_path / "duration.db")
    store.initialize()
    return StoryEngine(
        store=store,
        generator=generator or DeterministicStoryProvider(),
        critic=DeterministicIndependentCritic(),
    ), store


def test_story_engine_compresses_script_into_ten_percent_duration_window(tmp_path):
    story_engine, store = engine(tmp_path)

    result = story_engine.run(brief("duration_fit"))

    assert result.status == "completed"
    assert result.duration_qc.passed
    assert 81 <= result.script.estimated_seconds <= 99
    assert result.duration_qc.target_seconds == 90
    assert result.duration_qc.revision_applied
    store.close()


class UncompressibleProvider(DeterministicStoryProvider):
    def revise(self, scenes, revision):
        if revision.get("operation") == "fit_duration":
            return scenes
        return super().revise(scenes, revision)


def test_story_engine_blocks_when_provider_cannot_fit_duration(tmp_path):
    story_engine, store = engine(tmp_path, UncompressibleProvider())

    result = story_engine.run(brief("duration_blocked"))

    assert result.status == "blocked"
    assert result.error_code == "DURATION_OUT_OF_RANGE"
    store.close()


class DreamResetProvider(DeterministicStoryProvider):
    def scenes(self, brief, concept, blueprint):
        scenes = list(super().scenes(brief, concept, blueprint))
        first = scenes[0]
        scenes[0] = type(first)(
            scene_id=first.scene_id,
            purpose=first.purpose,
            narration="Todo era solo un sueño. " + first.narration,
            target_seconds=first.target_seconds,
            characters=first.characters,
            seed_ids=first.seed_ids,
            payoff_ids=first.payoff_ids,
        )
        return tuple(scenes)


def test_guardian_blocks_known_narrative_antipattern_even_if_critic_scores_high(tmp_path):
    story_engine, store = engine(tmp_path, DreamResetProvider())

    result = story_engine.run(brief("antipattern_blocked"))

    assert result.status == "blocked"
    assert result.error_code == "NARRATIVE_ANTIPATTERN"
    store.close()
