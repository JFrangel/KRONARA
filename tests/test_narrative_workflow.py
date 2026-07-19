from pathlib import Path

import pytest

from kronara.llm import NarrativeConcept
from kronara.narrative_workflow import NarrativeWorkflow, OriginalityViolation
from kronara.trends import TrendSignal


class FakeKnowledge:
    def search(self, query, limit=8):
        return [
            type(
                "Result",
                (),
                {
                    "document_id": "dna_1",
                    "title": "Escalada paranormal",
                    "score": 0.9,
                    "citation_uri": "kronara://knowledge/dna_1",
                },
            )()
        ]


class OriginalProvider:
    def generate_concept(self, context):
        return NarrativeConcept(
            "Una restauradora descubre que los retratos cambian cuando el museo cierra.",
            "paranormal",
            "Las pinturas alteran únicamente recuerdos que nadie se atreve a contar.",
            ("https://www.reddit.com/r/stories/abc",),
        )


def signal():
    return TrendSignal(
        source_id="abc",
        source_uri="https://www.reddit.com/r/stories/abc",
        theme_hint="A locked room changed my family",
        velocity=4.2,
        engagement=400,
    )


def test_vertical_builds_cited_concept_and_ten_stage_blueprint(tmp_path: Path):
    workflow = NarrativeWorkflow(tmp_path / "narrative.db", FakeKnowledge(), OriginalProvider())

    result = workflow.run("episode-1", [signal()], target_duration_seconds=90)

    assert result["concept"]["genre"] == "paranormal"
    assert len(result["blueprint"]["stages"]) == 10
    assert sum(stage["target_seconds"] for stage in result["blueprint"]["stages"]) == 90
    assert result["citations"] == ["kronara://knowledge/dna_1"]


class CopyingProvider:
    def generate_concept(self, context):
        return NarrativeConcept(
            "A locked room changed my family",
            "drama",
            "A locked room changed my family",
            ("https://www.reddit.com/r/stories/abc",),
        )


def test_vertical_blocks_concept_that_copies_signal_title(tmp_path: Path):
    workflow = NarrativeWorkflow(tmp_path / "narrative.db", FakeKnowledge(), CopyingProvider())

    with pytest.raises(OriginalityViolation):
        workflow.run("episode-1", [signal()], target_duration_seconds=90)

