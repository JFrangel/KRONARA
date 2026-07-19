from pathlib import Path

from kronara.langgraph_runtime import persistent_graph


def test_langgraph_runtime_persists_node_checkpoints(tmp_path: Path):
    def opportunity(state):
        return {"stage": "opportunity", "value": state.get("value", 0) + 1}

    with persistent_graph(
        tmp_path / "graph.db",
        nodes={"opportunity": opportunity},
        workflow=("opportunity",),
    ) as graph:
        config = {"configurable": {"thread_id": "run-1"}}
        result = graph.invoke({"stage": "start", "value": 0}, config)
        history = list(graph.get_state_history(config))

    assert result["stage"] == "opportunity"
    assert len(history) >= 2

