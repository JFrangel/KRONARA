from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph


class WorkflowState(TypedDict, total=False):
    stage: str
    value: int
    payload: dict[str, Any]
    evidence: list[dict[str, Any]]
    warnings: list[str]


@contextmanager
def persistent_graph(
    database: Path,
    nodes: Mapping[str, Callable[[WorkflowState], dict[str, Any]]],
    workflow: Sequence[str],
) -> Iterator[Any]:
    if not workflow:
        raise ValueError("workflow must contain at least one node")
    builder = StateGraph(WorkflowState)
    for name in workflow:
        builder.add_node(name, nodes[name])
    builder.add_edge(START, workflow[0])
    for current, following in zip(workflow, workflow[1:]):
        builder.add_edge(current, following)
    builder.add_edge(workflow[-1], END)
    with SqliteSaver.from_conn_string(str(database)) as checkpointer:
        yield builder.compile(checkpointer=checkpointer)

