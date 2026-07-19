from datetime import UTC, datetime, timedelta

import pytest

from kronara.research import ResearchPlanner, ResearchSynthesizer
from kronara.research_contracts import (
    ResearchQuestion,
    SourceAssertion,
    SourceRecord,
)
from kronara.evidence import EvidenceEngine


NOW = datetime(2026, 7, 19, tzinfo=UTC)


@pytest.mark.parametrize(
    ("kind", "stance"),
    (("unknown", "support"), ("fact", "neutral")),
)
def test_source_assertion_rejects_unknown_kind_or_stance(kind, stance):
    with pytest.raises(ValueError):
        SourceAssertion(
            claim_id="invalid",
            subquestion_id="rq:claim",
            text="Invalid boundary value.",
            kind=kind,
            stance=stance,
            confidence=0.5,
        )


def test_planner_creates_non_overlapping_work_with_bounded_source_budgets():
    question = ResearchQuestion(
        question_id="rq-voice-1",
        question="¿Qué voz retiene mejor y en qué horario conviene publicar?",
        language="es",
        max_cost_usd=3.0,
        max_sources=9,
    )

    plan = ResearchPlanner().plan(question)

    assert plan.intent == "comparative"
    assert len(plan.subquestions) >= 2
    assert len({item.focus for item in plan.subquestions}) == len(plan.subquestions)
    assert sum(item.source_budget for item in plan.subquestions) <= question.max_sources
    assert all(item.source_budget > 0 for item in plan.subquestions)
    assert plan.stopping_rule.minimum_coverage > 0
    assert plan.stopping_rule.maximum_cost_usd == question.max_cost_usd


def test_evidence_matrix_preserves_contradictions_and_source_dependence():
    claim = SourceAssertion(
        claim_id="claim-retention",
        subquestion_id="rq-voice-1:comparison",
        text="La voz A mejora la finalización.",
        kind="fact",
        stance="support",
        confidence=0.9,
    )
    records = (
        _record("source-a", "family-a", claim),
        _record("source-a-copy", "family-a", claim, depends_on=("source-a",)),
        _record(
            "source-b",
            "family-b",
            SourceAssertion(
                claim_id=claim.claim_id,
                subquestion_id=claim.subquestion_id,
                text=claim.text,
                kind=claim.kind,
                stance="oppose",
                confidence=0.8,
            ),
        ),
    )

    matrix = EvidenceEngine(now=NOW).build(records)
    result = matrix.claims[0]

    assert result.status == "contested"
    assert result.independent_source_count == 2
    assert result.supporting_source_ids == ("source-a", "source-a-copy")
    assert result.opposing_source_ids == ("source-b",)
    assert matrix.contradictions[0].claim_id == claim.claim_id
    assert matrix.dependent_source_groups == (("source-a", "source-a-copy"),)


def test_coverage_is_incomplete_when_a_planned_subquestion_has_no_evidence():
    plan = ResearchPlanner().plan(
        ResearchQuestion(
            question_id="rq-coverage",
            question="¿Qué tema funciona mejor y por qué?",
            language="es",
            max_cost_usd=2.0,
            max_sources=6,
        )
    )
    first = plan.subquestions[0]
    matrix = EvidenceEngine(now=NOW).build(
        (
            _record(
                "source-only",
                "family-only",
                SourceAssertion(
                    claim_id="claim-only",
                    subquestion_id=first.subquestion_id,
                    text="El tema de misterio tiene mayor finalización.",
                    kind="fact",
                    stance="support",
                    confidence=0.8,
                ),
            ),
        ),
        expected_subquestion_ids=tuple(item.subquestion_id for item in plan.subquestions),
    )

    assert matrix.coverage.complete is False
    assert matrix.coverage.covered_subquestion_ids == (first.subquestion_id,)
    assert set(matrix.coverage.missing_subquestion_ids) == {
        item.subquestion_id for item in plan.subquestions[1:]
    }


def test_explicit_source_dependency_does_not_count_as_independent_corroboration():
    assertion = SourceAssertion(
        claim_id="copied-claim",
        subquestion_id="rq:claim",
        text="La plataforma reportó una nueva métrica.",
        kind="fact",
        stance="support",
        confidence=0.9,
    )
    matrix = EvidenceEngine(now=NOW).build(
        (
            _record("primary", "official", assertion),
            _record("syndicated", "news-site", assertion, depends_on=("primary",)),
        )
    )

    assert matrix.claims[0].independent_source_count == 1
    assert matrix.claims[0].status == "weak"
    assert matrix.dependent_source_groups == (("primary", "syndicated"),)


def test_expired_and_rights_rejected_records_never_enter_evidence():
    assertion = SourceAssertion(
        claim_id="unsafe-claim",
        subquestion_id="rq:claim",
        text="Una afirmación no utilizable.",
        kind="fact",
        stance="support",
        confidence=0.9,
    )
    expired = _record("expired", "family-expired", assertion)
    expired = SourceRecord(
        **{
            **expired.__dict__,
            "valid_until": NOW - timedelta(seconds=1),
        }
    )
    denied = _record("denied", "family-denied", assertion)
    denied = SourceRecord(**{**denied.__dict__, "rights_mode": "denied"})

    matrix = EvidenceEngine(now=NOW).build((expired, denied))

    assert matrix.claims == ()
    assert matrix.source_uris == ()
    assert set(matrix.warnings) == {"expired:expired", "rights_rejected:denied"}


def test_synthesizer_separates_supported_facts_from_contested_hypotheses():
    plan = ResearchPlanner().plan(
        ResearchQuestion(
            question_id="rq-brief",
            question="¿Qué voz ofrece mejor retención?",
            language="es",
            max_cost_usd=2.0,
            max_sources=6,
        )
    )
    subquestion_id = plan.subquestions[0].subquestion_id
    supported = SourceAssertion(
        claim_id="supported",
        subquestion_id=subquestion_id,
        text="La muestra contiene 120 publicaciones.",
        kind="fact",
        stance="support",
        confidence=0.95,
    )
    contested = SourceAssertion(
        claim_id="contested",
        subquestion_id=subquestion_id,
        text="La voz A causa mayor retención.",
        kind="fact",
        stance="support",
        confidence=0.7,
    )
    matrix = EvidenceEngine(now=NOW).build(
        (
            _record("source-1", "family-1", supported),
            _record("source-2", "family-2", supported),
            _record("source-3", "family-3", contested),
            _record(
                "source-4",
                "family-4",
                SourceAssertion(
                    claim_id=contested.claim_id,
                    subquestion_id=contested.subquestion_id,
                    text=contested.text,
                    kind=contested.kind,
                    stance="oppose",
                    confidence=0.75,
                ),
            ),
        ),
        expected_subquestion_ids=(subquestion_id,),
    )

    brief = ResearchSynthesizer().synthesize(plan, matrix)

    assert brief.facts == (supported.text,)
    assert contested.text not in brief.facts
    assert contested.text in brief.hypotheses
    assert brief.status == "partial"
    assert brief.citations == (
        "https://sources.local/source-1",
        "https://sources.local/source-2",
        "https://sources.local/source-3",
        "https://sources.local/source-4",
    )


def _record(
    record_id: str,
    source_family: str,
    assertion: SourceAssertion,
    *,
    depends_on: tuple[str, ...] = (),
) -> SourceRecord:
    return SourceRecord(
        record_id=record_id,
        source_uri=f"https://sources.local/{record_id}",
        publisher=source_family,
        source_family=source_family,
        published_at=NOW - timedelta(days=1),
        retrieved_at=NOW,
        valid_until=NOW + timedelta(days=30),
        rights_mode="reference_only",
        assertions=(assertion,),
        depends_on=depends_on,
    )
