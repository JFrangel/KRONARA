from kronara.cognitive_runtime import (
    CognitiveRuntime,
    ExecutionPlan,
    PlanStep,
    RuntimeLimits,
)
from kronara.contracts import EvidenceRef
from kronara.guardian import Guardian
from kronara.observable_tools import ObservableToolRegistry
from kronara.skills import SkillRegistry, SkillSpec
from kronara.store import KronaraStore
from kronara.tools import ToolRegistry, ToolSpec


class Planner:
    family = "qwen"

    def plan(self, task, skills):
        assert [item.skill_id for item in skills] == ["narrative_planning"]
        return ExecutionPlan(
            objective=task.objective,
            steps=(PlanStep("draft", "story.draft", {"topic": "injusticia"}),),
            decision_summary="Crear y verificar un borrador original.",
        )


class Critic:
    family = "kimi"

    def __init__(self):
        self.calls = 0

    def review(self, task, state):
        self.calls += 1
        if self.calls == 1:
            return {"passed": False, "revision": {"hook": "abre con una decisión"}}
        return {"passed": True}


def test_runtime_plans_executes_local_revision_and_verifies_evidence():
    drafts = []

    def draft(args):
        drafts.append(args)
        return {
            "artifact": "story-1",
            "claims": ["originality_checked"],
            "evidence": [
                EvidenceRef("ev-1", "kronara://qc/1", ("originality_checked",), 0.95)
            ],
        }

    runtime = CognitiveRuntime(
        skills=SkillRegistry([SkillSpec("narrative_planning", 1, ("plan_story",))]),
        tools=ToolRegistry([ToolSpec("story.draft", draft)]),
        planner=Planner(),
        critic=Critic(),
        guardian=Guardian(),
        limits=RuntimeLimits(max_steps=4, max_tool_calls=4, max_revisions=1),
    )

    result = runtime.run(
        objective="Crear historia",
        required_capabilities=("plan_story",),
        agent_id="concept_architect",
        allowed_tools=("story.draft",),
    )

    assert result.status == "completed"
    assert result.model_families == ("qwen", "kimi")
    assert result.decision_summary == "Crear y verificar un borrador original."
    assert result.private_reasoning is None
    assert drafts[1]["revision"] == {"hook": "abre con una decisión"}


def test_runtime_fails_when_step_budget_is_exceeded():
    class LongPlanner(Planner):
        def plan(self, task, skills):
            return ExecutionPlan(
                task.objective,
                tuple(PlanStep(str(i), "noop", {}) for i in range(3)),
                "plan largo",
            )

    runtime = CognitiveRuntime(
        skills=SkillRegistry([SkillSpec("planning", 1, ("plan",))]),
        tools=ToolRegistry([ToolSpec("noop", lambda _: {})]),
        planner=LongPlanner(),
        critic=Critic(),
        guardian=Guardian(),
        limits=RuntimeLimits(max_steps=2),
    )

    result = runtime.run("x", ("plan",), "agent", ("noop",))

    assert result.status == "blocked"
    assert result.error_code == "STEP_BUDGET_EXCEEDED"


def test_runtime_blocks_cost_overrun_before_calling_tools():
    called = []

    class CostlyPlanner(Planner):
        def plan(self, task, skills):
            return ExecutionPlan(
                task.objective,
                (PlanStep("costly", "noop", {}, estimated_cost_usd=3.0),),
                "plan costoso",
            )

    runtime = CognitiveRuntime(
        skills=SkillRegistry([SkillSpec("planning", 1, ("plan",))]),
        tools=ToolRegistry([ToolSpec("noop", lambda _: called.append(True))]),
        planner=CostlyPlanner(),
        critic=Critic(),
        guardian=Guardian(),
        limits=RuntimeLimits(max_cost_usd=1.0),
    )

    result = runtime.run("x", ("plan",), "agent", ("noop",))

    assert result.error_code == "COST_BUDGET_EXCEEDED"
    assert called == []


def test_runtime_requires_independent_critic_family():
    critic = Critic()
    critic.family = "qwen"
    runtime = CognitiveRuntime(
        skills=SkillRegistry([SkillSpec("planning", 1, ("plan_story",))]),
        tools=ToolRegistry([ToolSpec("story.draft", lambda _: {})]),
        planner=Planner(),
        critic=critic,
        guardian=Guardian(),
    )

    result = runtime.run("x", ("plan_story",), "agent", ("story.draft",))

    assert result.error_code == "CRITIC_NOT_INDEPENDENT"


def test_runtime_converts_planner_failure_to_structured_block():
    class BrokenPlanner(Planner):
        def plan(self, task, skills):
            raise TimeoutError("private provider detail")

    runtime = CognitiveRuntime(
        skills=SkillRegistry([SkillSpec("planning", 1, ("plan",))]),
        tools=ToolRegistry([]),
        planner=BrokenPlanner(),
        critic=Critic(),
        guardian=Guardian(),
    )

    result = runtime.run("x", ("plan",), "agent", ())

    assert result.error_code == "PLANNER_FAILED"
    assert "private provider detail" not in repr(result)


def test_runtime_blocks_when_global_deadline_expires_during_planning():
    now = [0.0]

    class SlowPlanner(Planner):
        def plan(self, task, skills):
            now[0] = 4.0
            return ExecutionPlan(task.objective, (), "plan")

    runtime = CognitiveRuntime(
        skills=SkillRegistry([SkillSpec("planning", 1, ("plan",))]),
        tools=ToolRegistry([]),
        planner=SlowPlanner(),
        critic=Critic(),
        guardian=Guardian(),
        limits=RuntimeLimits(timeout_seconds=3.0),
        clock=lambda: now[0],
    )

    result = runtime.run("x", ("plan",), "agent", ())

    assert result.error_code == "RUNTIME_TIMEOUT"


def test_runtime_emits_observable_tool_events_with_explicit_run_id(tmp_path):
    store = KronaraStore(tmp_path / "runtime.db")
    store.initialize()

    def draft(_):
        return {
            "artifact": "story-1",
            "claims": ["originality_checked"],
            "evidence": [
                EvidenceRef("ev-1", "kronara://qc/1", ("originality_checked",), 0.95)
            ],
        }

    runtime = CognitiveRuntime(
        skills=SkillRegistry([SkillSpec("narrative_planning", 1, ("plan_story",))]),
        tools=ObservableToolRegistry(
            ToolRegistry([ToolSpec("story.draft", draft)]),
            store=store,
        ),
        planner=Planner(),
        critic=Critic(),
        guardian=Guardian(),
        limits=RuntimeLimits(max_steps=4, max_tool_calls=4, max_revisions=1),
    )

    result = runtime.run(
        objective="Crear historia",
        required_capabilities=("plan_story",),
        agent_id="concept_architect",
        allowed_tools=("story.draft",),
        run_id="run_observable",
    )

    assert result.status == "completed"
    assert [event.status for event in store.list_tool_traces("run_observable")] == [
        "started",
        "completed",
        "started",
        "completed",
    ]
    store.close()
