from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from kronara.contracts import AgentResult, AutonomyPolicy
from kronara.store import KronaraStore

Node = Callable[[dict[str, Any]], dict[str, Any]]

DEFAULT_WORKFLOW = (
    "opportunity_intelligence",
    "editorial_decision",
    "research_and_rights",
    "story_architecture",
    "writing_room",
    "production_direction",
    "automated_qc",
    "packaging_and_distribution",
    "performance_learning",
)


class ExecutiveOrchestrator:
    def __init__(
        self,
        store: KronaraStore,
        policy: AutonomyPolicy,
        nodes: Mapping[str, Node],
        workflow: Sequence[str] = DEFAULT_WORKFLOW,
    ):
        self.store = store
        self.policy = policy
        self.nodes = nodes
        self.workflow = tuple(workflow)

    def run(self, run_id: str, initial_state: dict[str, Any]) -> AgentResult:
        state = dict(initial_state)
        self.store.append_event(run_id, "workflow.started", {"mode": self.policy.mode})
        for name in self.workflow:
            node = self.nodes[name]
            self.store.append_event(run_id, "node.started", {"node": name})
            state = node(state)
            self.store.save_checkpoint(run_id, name, state)
            self.store.append_event(run_id, "node.completed", {"node": name})
        self.store.append_event(run_id, "workflow.completed", {})
        return AgentResult(status="completed", state=state)

