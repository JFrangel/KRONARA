from kronara.graph_memory import GraphEntity, GraphRelation, KronaraGraph, OPEN


def graph(tmp_path):
    return KronaraGraph(tmp_path / "kg.db").initialize()


def test_entities_and_relations_round_trip(tmp_path):
    kg = graph(tmp_path)
    kg.upsert_entity(
        GraphEntity("s1:character:mara", "character", "Mara", "s1", valid_from=100, recorded_at=100)
    )
    kg.upsert_entity(
        GraphEntity("s1:place:hotel", "place", "Hotel Arcadia", "s1", valid_from=100, recorded_at=100)
    )
    kg.add_relation(
        GraphRelation("r1", "s1:character:mara", "visits", "s1:place:hotel", "s1", valid_from=100, recorded_at=100)
    )
    canon = kg.canon("s1", as_of=150)
    assert "Mara" in canon.entity_names()
    assert len(canon.relations) == 1
    assert kg.neighbors("s1:character:mara") == ("s1:place:hotel",)
    kg.close()


def test_bitemporal_supersede_keeps_history(tmp_path):
    kg = graph(tmp_path)
    kg.upsert_entity(
        GraphEntity("s1:fact:door", "fact", "La puerta 307 está cerrada", "s1", valid_from=100, recorded_at=100)
    )
    # Later a revelation changes the fact; the old version is bounded, not erased.
    kg.supersede_entity(
        "s1:fact:door",
        GraphEntity("s1:fact:door", "fact", "La puerta 307 nunca existió", "s1",
                    valid_from=200, recorded_at=200, version=2),
        at=200,
    )
    early = kg.canon("s1", as_of=150).facts()
    late = kg.canon("s1", as_of=250).facts()
    assert "La puerta 307 está cerrada" in early
    assert "La puerta 307 nunca existió" in late
    assert "La puerta 307 está cerrada" not in late
    kg.close()


def test_neighbors_traverses_multiple_hops(tmp_path):
    kg = graph(tmp_path)
    for name in ("a", "b", "c"):
        kg.upsert_entity(GraphEntity(f"s1:topic:{name}", "topic", name, "s1", recorded_at=0))
    kg.add_relation(GraphRelation("r_ab", "s1:topic:a", "related", "s1:topic:b", "s1", recorded_at=0))
    kg.add_relation(GraphRelation("r_bc", "s1:topic:b", "related", "s1:topic:c", "s1", recorded_at=0))
    reached = kg.neighbors("s1:topic:a", max_hops=2)
    assert set(reached) == {"s1:topic:b", "s1:topic:c"}
    assert kg.neighbors("s1:topic:a", max_hops=1) == ("s1:topic:b",)
    kg.close()


def test_open_valid_to_is_visible_without_as_of(tmp_path):
    kg = graph(tmp_path)
    kg.upsert_entity(GraphEntity("s1:character:mara", "character", "Mara", "s1", valid_from=0, recorded_at=0))
    assert kg.canon("s1").entity_names() == ("Mara",)
    assert OPEN > 0
    kg.close()
