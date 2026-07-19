from __future__ import annotations

import re

from kronara.research_contracts import (
    AnalyticalBrief,
    EvidenceMatrix,
    ResearchPlan,
    ResearchQuestion,
    SourceQuery,
    StoppingRule,
    SubQuestion,
)


class ResearchPlanner:
    _INTENT_MARKERS = (
        ("causal", ("por qué", "causa", "provoca", "impacta")),
        ("comparative", ("mejor", "compar", " versus ", " vs ", "diferencia")),
        ("metric", ("métrica", "retención", "porcentaje", "tasa", "cuánto")),
        ("editorial", ("historia", "guion", "tema", "editorial")),
    )

    def plan(self, question: ResearchQuestion) -> ResearchPlan:
        normalized = self._normalize(question.question)
        intent = self._classify(normalized)
        risk = "high" if question.sensitive else "low"
        focuses = self._focuses(intent)
        count = min(len(focuses), question.max_sources)
        focuses = focuses[:count]
        base, remainder = divmod(question.max_sources, count)
        minimum_sources = 2 if question.max_sources >= count * 2 else 1
        subquestions = tuple(
            SubQuestion(
                subquestion_id=f"{question.question_id}:{focus}",
                question=self._subquestion_text(question.question, focus),
                focus=focus,
                source_budget=base + (1 if index < remainder else 0),
                minimum_independent_sources=minimum_sources,
            )
            for index, focus in enumerate(focuses)
        )
        queries = tuple(
            SourceQuery(
                subquestion_id=item.subquestion_id,
                source_types=("first_party_metrics", "authoritative_reference", "official_api"),
                max_results=item.source_budget,
            )
            for item in subquestions
        )
        return ResearchPlan(
            schema_version=1,
            question_id=question.question_id,
            intent=intent,
            risk=risk,
            subquestions=subquestions,
            queries=queries,
            stopping_rule=StoppingRule(
                minimum_coverage=1.0,
                minimum_independent_sources=minimum_sources,
                maximum_cost_usd=question.max_cost_usd,
                maximum_queries=len(queries),
            ),
        )

    @classmethod
    def _classify(cls, normalized: str) -> str:
        for intent, markers in cls._INTENT_MARKERS:
            if any(marker in normalized for marker in markers):
                return intent
        if normalized.startswith(("qué ", "cual ", "cuál ", "cuando ", "cuándo ")):
            return "factual"
        return "exploratory"

    @staticmethod
    def _focuses(intent: str) -> tuple[str, ...]:
        return {
            "comparative": ("measurement", "comparison", "confounders"),
            "causal": ("association", "alternatives", "counterevidence"),
            "metric": ("definition", "baseline", "segments"),
            "editorial": ("audience", "patterns", "constraints"),
            "factual": ("claim", "recency", "corroboration"),
            "exploratory": ("landscape", "signals", "unknowns"),
        }[intent]

    @staticmethod
    def _subquestion_text(question: str, focus: str) -> str:
        prompts = {
            "measurement": "¿Qué métrica y denominador permiten responder con precisión?",
            "comparison": f"¿Qué evidencia compara directamente las alternativas de: {question}",
            "confounders": "¿Qué audiencia, horario, duración o sesgo puede explicar la diferencia?",
            "association": f"¿Qué asociación medible existe en: {question}",
            "alternatives": "¿Qué explicaciones alternativas son compatibles con la evidencia?",
            "counterevidence": "¿Qué evidencia contradice o limita la explicación propuesta?",
            "definition": "¿Cómo se define exactamente la métrica y su denominador?",
            "baseline": f"¿Cuál es el baseline comparable para: {question}",
            "segments": "¿Cómo cambia la métrica por segmentos relevantes?",
            "audience": "¿Qué necesidad verificable de audiencia está involucrada?",
            "patterns": f"¿Qué patrones editoriales aparecen en: {question}",
            "constraints": "¿Qué derechos, políticas y límites de producción aplican?",
            "claim": f"¿Cuál es la afirmación verificable central de: {question}",
            "recency": "¿La evidencia sigue vigente a la fecha de investigación?",
            "corroboration": "¿Qué fuente independiente corrobora la afirmación?",
            "landscape": f"¿Cuáles son los componentes principales de: {question}",
            "signals": "¿Qué señales verificables favorecen cada interpretación?",
            "unknowns": "¿Qué información falta para una conclusión fiable?",
        }
        return prompts[focus]

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower())


class ResearchSynthesizer:
    def synthesize(self, plan: ResearchPlan, matrix: EvidenceMatrix) -> AnalyticalBrief:
        sections: dict[str, list[str]] = {
            "fact": [],
            "calculation": [],
            "inference": [],
            "hypothesis": [],
            "recommendation": [],
        }
        for claim in matrix.claims:
            if claim.status == "supported":
                sections[claim.kind].append(claim.text)
            elif claim.status == "contested":
                sections["hypothesis"].append(claim.text)
            elif claim.kind in {"inference", "hypothesis"} and claim.status == "weak":
                sections[claim.kind].append(claim.text)

        status = "complete"
        if not matrix.claims:
            status = "blocked"
        elif not matrix.coverage.complete or matrix.contradictions:
            status = "partial"
        confidence = 0.0
        if matrix.claims:
            confidence = sum(item.confidence for item in matrix.claims) / len(matrix.claims)
            if matrix.contradictions:
                confidence *= 0.75

        return AnalyticalBrief(
            schema_version=1,
            brief_id=f"brief:{plan.question_id}",
            status=status,
            facts=tuple(sections["fact"]),
            calculations=tuple(sections["calculation"]),
            inferences=tuple(sections["inference"]),
            hypotheses=tuple(sections["hypothesis"]),
            recommendations=tuple(sections["recommendation"]),
            citations=matrix.source_uris,
            confidence=round(confidence, 4),
            coverage=matrix.coverage,
            contradictions=matrix.contradictions,
            warnings=matrix.warnings,
        )
