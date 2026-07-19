from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from kronara.contracts import EvidenceRef
from kronara.guardian import Guardian
from kronara.observable_tools import ObservableToolRegistry, ToolExecutionContext
from kronara.skills import SkillRegistry, SkillSpec
from kronara.tools import ToolRegistry


@dataclass(frozen=True)
class AgentTask:
    objective: str
    required_capabilities: tuple[str, ...]
    agent_id: str
    allowed_tools: tuple[str, ...]


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    tool_id: str
    arguments: dict[str, Any]
    estimated_cost_usd: float = 0.0


@dataclass(frozen=True)
class ExecutionPlan:
    objective: str
    steps: tuple[PlanStep, ...]
    decision_summary: str


@dataclass(frozen=True)
class RuntimeLimits:
    max_steps: int = 12
    max_tool_calls: int = 20
    max_revisions: int = 2
    max_cost_usd: float = 2.0
    timeout_seconds: float = 300.0


@dataclass(frozen=True)
class CognitiveResult:
    status: str
    state: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    decision_summary: str = ""
    model_families: tuple[str, ...] = ()
    private_reasoning: None = None


class Planner(Protocol):
    family: str

    def plan(self, task: AgentTask, skills: tuple[SkillSpec, ...]) -> ExecutionPlan: ...


class Critic(Protocol):
    family: str

    def review(self, task: AgentTask, state: dict[str, Any]) -> dict[str, Any]: ...


class CognitiveRuntime:
    """Bounded plan/act/critic/guardian loop for a single governed agent task."""

    def __init__(
        self,
        *,
        skills: SkillRegistry,
        tools: ToolRegistry | ObservableToolRegistry,
        planner: Planner,
        critic: Critic,
        guardian: Guardian,
        limits: RuntimeLimits = RuntimeLimits(),
        clock: Callable[[], float] = time.monotonic,
    ):
        self.skills = skills
        self.tools = tools
        self.planner = planner
        self.critic = critic
        self.guardian = guardian
        self.limits = limits
        self.clock = clock

    def run(
        self,
        objective: str,
        required_capabilities: tuple[str, ...],
        agent_id: str,
        allowed_tools: tuple[str, ...],
        run_id: str | None = None,
    ) -> CognitiveResult:
        started_at = self.clock()
        task = AgentTask(objective, required_capabilities, agent_id, allowed_tools)
        families = (self.planner.family, self.critic.family)
        if self.planner.family == self.critic.family:
            return self._blocked("CRITIC_NOT_INDEPENDENT", families=families)
        try:
            selected = self.skills.select(required_capabilities)
        except LookupError:
            return self._blocked("CAPABILITY_UNAVAILABLE")
        try:
            plan = self.planner.plan(task, selected)
        except Exception:
            return self._blocked("PLANNER_FAILED", families=families)
        if self._expired(started_at):
            return self._blocked("RUNTIME_TIMEOUT", plan.decision_summary, families)
        if len(plan.steps) > self.limits.max_steps:
            return self._blocked("STEP_BUDGET_EXCEEDED", plan.decision_summary, families)
        if len(plan.steps) > self.limits.max_tool_calls:
            return self._blocked("TOOL_BUDGET_EXCEEDED", plan.decision_summary, families)
        if sum(step.estimated_cost_usd for step in plan.steps) > self.limits.max_cost_usd:
            return self._blocked("COST_BUDGET_EXCEEDED", plan.decision_summary, families)

        effective_run_id = run_id or f"run:{agent_id}:{int(started_at * 1000)}"
        state: dict[str, Any] = {
            "objective": objective,
            "artifacts": [],
            "run_id": effective_run_id,
        }
        last_step: PlanStep | None = None
        calls = 0
        for step in plan.steps:
            if self._expired(started_at):
                return self._blocked("RUNTIME_TIMEOUT", plan.decision_summary, families, state)
            last_step = step
            outcome = self._invoke_tool(
                effective_run_id,
                agent_id,
                allowed_tools,
                step.tool_id,
                step.arguments,
            )
            calls += 1
            if not outcome.ok:
                return self._blocked(
                    outcome.error_code or "TOOL_FAILED", plan.decision_summary, families, state
                )
            self._merge(state, step.step_id, outcome.value)

        revisions = 0
        spent_cost = sum(step.estimated_cost_usd for step in plan.steps)
        while True:
            if self._expired(started_at):
                return self._blocked("RUNTIME_TIMEOUT", plan.decision_summary, families, state)
            try:
                critique = self.critic.review(task, state)
            except Exception:
                return self._blocked("CRITIC_FAILED", plan.decision_summary, families, state)
            if self._expired(started_at):
                return self._blocked("RUNTIME_TIMEOUT", plan.decision_summary, families, state)
            if critique.get("passed"):
                break
            if last_step is None or revisions >= self.limits.max_revisions:
                return self._blocked("CRITIC_REJECTED", plan.decision_summary, families)
            if calls >= self.limits.max_tool_calls:
                return self._blocked("TOOL_BUDGET_EXCEEDED", plan.decision_summary, families)
            if spent_cost + last_step.estimated_cost_usd > self.limits.max_cost_usd:
                return self._blocked("COST_BUDGET_EXCEEDED", plan.decision_summary, families, state)
            arguments = dict(last_step.arguments)
            arguments["revision"] = critique.get("revision", {})
            outcome = self._invoke_tool(
                effective_run_id,
                agent_id,
                allowed_tools,
                last_step.tool_id,
                arguments,
            )
            calls += 1
            revisions += 1
            spent_cost += last_step.estimated_cost_usd
            if not outcome.ok:
                return self._blocked(outcome.error_code or "TOOL_FAILED", plan.decision_summary, families)
            self._merge(state, last_step.step_id, outcome.value)

        claims = tuple(state.get("claims", ()))
        evidence = tuple(item for item in state.get("evidence", ()) if isinstance(item, EvidenceRef))
        guardian_report = self.guardian.verify_claims(claims, evidence)
        if not guardian_report.passed:
            state["unverified_claims"] = guardian_report.unverified_claims
            return CognitiveResult(
                "blocked", state, "UNVERIFIED_CLAIMS", plan.decision_summary, families
            )
        state["selected_skills"] = tuple(skill.skill_id for skill in selected)
        state["tool_calls"] = calls
        state["revisions"] = revisions
        return CognitiveResult("completed", state, None, plan.decision_summary, families)

    @staticmethod
    def _merge(state: dict[str, Any], step_id: str, value: Any) -> None:
        state[step_id] = value
        if isinstance(value, dict):
            for key in ("claims", "evidence"):
                if key in value:
                    state[key] = value[key]
            if "artifact" in value:
                state["artifacts"].append(value["artifact"])

    @staticmethod
    def _blocked(
        code: str,
        summary: str = "",
        families: tuple[str, ...] = (),
        state: dict[str, Any] | None = None,
    ) -> CognitiveResult:
        return CognitiveResult(
            "blocked",
            state=dict(state or {}),
            error_code=code,
            decision_summary=summary,
            model_families=families,
        )

    def _expired(self, started_at: float) -> bool:
        return self.clock() - started_at > self.limits.timeout_seconds

    def _invoke_tool(
        self,
        run_id: str,
        agent_id: str,
        allowed_tools: tuple[str, ...],
        tool_id: str,
        arguments: dict[str, Any],
    ):
        if isinstance(self.tools, ObservableToolRegistry):
            return self.tools.invoke(
                ToolExecutionContext(
                    run_id=run_id,
                    agent_id=agent_id,
                    allowed_tools=allowed_tools,
                    cost_budget_usd=self.limits.max_cost_usd,
                ),
                tool_id,
                arguments,
            )
        return self.tools.invoke(agent_id, allowed_tools, tool_id, arguments)
