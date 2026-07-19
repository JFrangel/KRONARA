from pathlib import Path

from kronara.contracts import AutonomyMode, AutonomyPolicy
from kronara.orchestrator import ExecutiveOrchestrator
from kronara.store import KronaraStore


def test_orchestrator_runs_declared_nodes_and_checkpoints(tmp_path: Path):
    calls: list[str] = []

    def node(state):
        calls.append("opportunity_intelligence")
        return {**state, "opportunity": "original paranormal premise"}

    store = KronaraStore(tmp_path / "runtime.db")
    store.initialize()
    orchestrator = ExecutiveOrchestrator(
        store=store,
        policy=AutonomyPolicy(mode=AutonomyMode.FULL_AUTO),
        nodes={"opportunity_intelligence": node},
        workflow=("opportunity_intelligence",),
    )

    result = orchestrator.run("run_1", {"channel": "facebook_reels"})

    assert result.status == "completed"
    assert result.state["opportunity"] == "original paranormal premise"
    assert calls == ["opportunity_intelligence"]
    assert store.load_checkpoint("run_1").node == "opportunity_intelligence"

