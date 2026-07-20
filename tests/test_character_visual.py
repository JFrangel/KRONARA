from kronara.character_visual import (
    CharacterVisualProfile,
    GraphBackedCharacterVisualStore,
    InMemoryCharacterVisualStore,
    derive_seed,
    resolve_character_visual,
)
from kronara.graph_memory import KronaraGraph
from kronara.image_gen import ImageGenerationResult
from kronara.series import SeriesCanonBuilder, StoryPart


class FakeImageProvider:
    def __init__(self, output_dir):
        self.output_dir = output_dir
        self.calls = []

    def generate(self, request):
        self.calls.append(request)
        # Write a real tiny file so sha256 hashing has something to read.
        import os

        os.makedirs(self.output_dir, exist_ok=True)
        full_path = os.path.join(self.output_dir, f"{request.cache_key()}.png")
        with open(full_path, "wb") as handle:
            handle.write(b"fake-png-bytes")
        return ImageGenerationResult(
            image_path=full_path, seed=request.seed, width=request.width, height=request.height,
            quality_tier=request.quality_tier, generation_ms=1,
        )


# ---- derive_seed -------------------------------------------------------------


def test_derive_seed_is_deterministic():
    assert derive_seed("s1", "Mara") == derive_seed("s1", "Mara")


def test_derive_seed_differs_by_name_and_series():
    assert derive_seed("s1", "Mara") != derive_seed("s1", "Luisa")
    assert derive_seed("s1", "Mara") != derive_seed("s2", "Mara")


# ---- InMemoryCharacterVisualStore --------------------------------------------


def test_in_memory_store_roundtrip():
    store = InMemoryCharacterVisualStore()
    assert store.get("Mara") is None
    profile = CharacterVisualProfile("Mara", 123, "restauradora de cuarenta años")
    store.put(profile, now=100)
    assert store.get("mara") == profile  # case-insensitive lookup


# ---- GraphBackedCharacterVisualStore -----------------------------------------


def test_graph_store_roundtrip(tmp_path):
    graph = KronaraGraph(tmp_path / "kg.db").initialize()
    store = GraphBackedCharacterVisualStore(graph, "serie-1")
    assert store.get("Mara") is None

    profile = CharacterVisualProfile("Mara", 999, "descripcion", "ref.png", "abc123")
    store.put(profile, now=100)

    fetched = store.get("Mara")
    assert fetched == profile
    graph.close()


def test_graph_store_preserves_ingest_attributes_when_adding_visual(tmp_path):
    """The character entity SeriesCanonBuilder.ingest() writes (introduced_part)
    must survive when the visual store later adds its own attributes -- neither
    write path may clobber the other's keys."""
    graph = KronaraGraph(tmp_path / "kg.db").initialize()
    canon = SeriesCanonBuilder(graph)
    canon.ingest(
        StoryPart("serie-1", 1, "story1", cliffhanger="gancho"),
        characters=("Mara",), facts=(), now=100,
    )
    visual_store = GraphBackedCharacterVisualStore(graph, "serie-1")
    visual_store.put(CharacterVisualProfile("Mara", 1, "desc", "ref.png", "hash"), now=101)

    entity = visual_store._find_entity("Mara")
    assert entity.attributes["introduced_part"] == "1"
    assert entity.attributes["visual_seed"] == "1"
    graph.close()


def test_graph_store_versions_increment_on_update(tmp_path):
    graph = KronaraGraph(tmp_path / "kg.db").initialize()
    store = GraphBackedCharacterVisualStore(graph, "serie-1")
    store.put(CharacterVisualProfile("Mara", 1, "v1"), now=100)
    store.put(CharacterVisualProfile("Mara", 1, "v2 updated"), now=200)

    fetched = store.get("Mara")
    assert fetched.appearance_description == "v2 updated"
    graph.close()


# ---- resolve_character_visual -------------------------------------------------


def test_new_character_generates_exactly_once(tmp_path):
    provider = FakeImageProvider(str(tmp_path))
    store = InMemoryCharacterVisualStore()

    profile = resolve_character_visual(
        store, "Mara", series_id="serie-1", appearance_description="pelo corto, chaqueta gris",
        image_provider=provider, now=100,
    )

    assert len(provider.calls) == 1
    assert provider.calls[0].quality_tier == "premium"
    assert profile.reference_image_path is not None
    assert profile.reference_image_sha256 is not None


def test_existing_character_calls_provider_zero_times(tmp_path):
    """The core consistency guarantee: reusing a resolved character makes NO
    image-generation calls."""
    provider = FakeImageProvider(str(tmp_path))
    store = InMemoryCharacterVisualStore()
    resolve_character_visual(
        store, "Mara", series_id="serie-1", appearance_description="pelo corto",
        image_provider=provider, now=100,
    )
    assert len(provider.calls) == 1

    resolve_character_visual(
        store, "Mara", series_id="serie-1", appearance_description="pelo corto",
        image_provider=provider, now=200,
    )

    assert len(provider.calls) == 1  # unchanged -> zero additional calls


def test_character_visual_persists_across_series_parts_via_graph(tmp_path):
    """The end-to-end guarantee: a character resolved in Part 1 (one store
    instance) is reused with the SAME seed/reference in Part 2 (a fresh store
    instance backed by the same graph) -- proving persistence, not just
    in-process caching."""
    graph = KronaraGraph(tmp_path / "kg.db").initialize()
    provider = FakeImageProvider(str(tmp_path))

    part1_store = GraphBackedCharacterVisualStore(graph, "serie-1")
    part1_profile = resolve_character_visual(
        part1_store, "Mara", series_id="serie-1", appearance_description="restauradora, pelo corto",
        image_provider=provider, now=100,
    )
    assert len(provider.calls) == 1

    part2_store = GraphBackedCharacterVisualStore(graph, "serie-1")  # fresh instance
    part2_profile = resolve_character_visual(
        part2_store, "Mara", series_id="serie-1", appearance_description="restauradora, pelo corto",
        image_provider=provider, now=200,
    )

    assert len(provider.calls) == 1  # still just one -> Part 2 reused Part 1's profile
    assert part2_profile.visual_seed == part1_profile.visual_seed
    assert part2_profile.reference_image_path == part1_profile.reference_image_path
    graph.close()
