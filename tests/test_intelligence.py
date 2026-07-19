from kronara.intelligence import (
    Candidate,
    ModelCapabilityRegistry,
    ModelProfile,
    reciprocal_rank_fusion,
)


def test_rrf_combines_lexical_vector_and_graph_rankings():
    rankings = [["a", "b"], ["b", "c"], ["b", "a"]]

    fused = reciprocal_rank_fusion(rankings)

    assert fused[0].item_id == "b"


def test_model_router_selects_healthy_capable_candidate():
    registry = ModelCapabilityRegistry(
        [
            ModelProfile("qwen-planner", ("planning",), quality=0.9, cost=0.4, healthy=True),
            ModelProfile("cheap-writer", ("writing",), quality=0.8, cost=0.1, healthy=True),
            ModelProfile("offline-planner", ("planning",), quality=1.0, cost=0.0, healthy=False),
        ]
    )

    selected = registry.select(Candidate(capability="planning", max_cost=0.5))

    assert selected.alias == "qwen-planner"

