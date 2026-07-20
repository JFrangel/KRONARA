"""Character visual consistency across scenes and serialized parts.

Combines a fixed per-character seed, a persisted text appearance description,
and a reference "character sheet" image (IP-Adapter conditioning) — the
practical, fully-free alternative to per-character LoRA training (needs
15-30 curated images + a training run, incompatible with unattended weekly
production) or FaceID (adds an insightface/onnxruntime dependency with real
Windows install friction and licensing ambiguity).

``GraphBackedCharacterVisualStore`` persists via the SAME character entity
``SeriesCanonBuilder.ingest()`` already writes (entity_id =
``f"{series_id}:character:{slug(name)}"``), read-merging its visual
attributes so neither write path clobbers the other's keys (ingest() keeps
writing ``introduced_part``; this store adds ``visual_seed``,
``appearance_description``, ``reference_image_path``,
``reference_image_sha256`` on top). ``InMemoryCharacterVisualStore`` gives
standalone (non-series) stories the same within-episode consistency.

This is a "family resemblance" mechanism, not photographic identity — some
drift across many generations is expected and acceptable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from kronara.graph_memory import GraphEntity, KronaraGraph, OPEN
from kronara.series import _slug


@dataclass(frozen=True)
class CharacterVisualProfile:
    name: str
    visual_seed: int
    appearance_description: str
    reference_image_path: str | None = None
    reference_image_sha256: str | None = None


class CharacterVisualStore(Protocol):
    def get(self, name: str) -> CharacterVisualProfile | None: ...
    def put(self, profile: CharacterVisualProfile, *, now: int) -> None: ...


def derive_seed(series_id: str, name: str) -> int:
    """Deterministic per-character seed: same (series, name) always yields the
    same seed, so re-resolving a character (e.g. after a cache miss) is stable
    even before a reference image exists."""
    digest = hashlib.sha256(f"{series_id}:{name}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


class InMemoryCharacterVisualStore:
    """Consistency within a single run (no cross-run persistence) — for
    standalone stories that are not part of a series."""

    def __init__(self) -> None:
        self._profiles: dict[str, CharacterVisualProfile] = {}

    def get(self, name: str) -> CharacterVisualProfile | None:
        return self._profiles.get(name.casefold())

    def put(self, profile: CharacterVisualProfile, *, now: int) -> None:
        del now  # no temporal dimension in memory-only storage
        self._profiles[profile.name.casefold()] = profile


class GraphBackedCharacterVisualStore:
    """Persists via the bitemporal graph so a character generated in Part 1
    of a series looks the same (same seed/reference) in Part 2+."""

    def __init__(self, graph: KronaraGraph, series_id: str):
        self.graph = graph
        self.series_id = series_id

    def get(self, name: str) -> CharacterVisualProfile | None:
        entity = self._find_entity(name)
        if entity is None or "visual_seed" not in entity.attributes:
            return None
        return CharacterVisualProfile(
            name=entity.name,
            visual_seed=int(entity.attributes["visual_seed"]),
            appearance_description=entity.attributes.get("appearance_description", ""),
            reference_image_path=entity.attributes.get("reference_image_path") or None,
            reference_image_sha256=entity.attributes.get("reference_image_sha256") or None,
        )

    def put(self, profile: CharacterVisualProfile, *, now: int) -> None:
        entity_id = f"{self.series_id}:character:{_slug(profile.name)}"
        existing = self._find_entity(profile.name)
        attributes = dict(existing.attributes) if existing else {}
        attributes.update(
            {
                "visual_seed": str(profile.visual_seed),
                "appearance_description": profile.appearance_description,
                "reference_image_path": profile.reference_image_path or "",
                "reference_image_sha256": profile.reference_image_sha256 or "",
            }
        )
        entity = GraphEntity(
            entity_id=entity_id,
            entity_type="character",
            name=profile.name,
            series_id=self.series_id,
            attributes=attributes,
            valid_from=now,
            valid_to=OPEN,
            recorded_at=now,
            version=(existing.version + 1) if existing else 1,
        )
        if existing:
            self.graph.supersede_entity(entity_id, entity, at=now)
        else:
            self.graph.upsert_entity(entity)

    def _find_entity(self, name: str):
        """The currently-valid version only (as_of=OPEN-1, matching
        KronaraGraph.canon()'s "now" convention) -- entities() without as_of
        returns every historical version unfiltered, including ones a prior
        supersede_entity() call already closed out."""
        entity_id = f"{self.series_id}:character:{_slug(name)}"
        for entity in self.graph.entities(
            series_id=self.series_id, entity_type="character", as_of=OPEN - 1
        ):
            if entity.entity_id == entity_id:
                return entity
        return None


def resolve_character_visual(
    store: CharacterVisualStore,
    name: str,
    *,
    series_id: str,
    appearance_description: str,
    image_provider,
    style_prompt: str = "",
    negative_prompt: str = "",
    now: int,
):
    """Return the character's visual profile, generating a premium "character
    sheet" image ONLY on first appearance. Reusing an existing profile makes
    zero calls to `image_provider` — the core consistency guarantee."""
    existing = store.get(name)
    if existing is not None:
        return existing

    from kronara.image_gen import ImageGenerationRequest

    seed = derive_seed(series_id, name)
    prompt = f"character reference sheet, neutral pose, front facing, {appearance_description}"
    if style_prompt:
        prompt = f"{prompt}, {style_prompt}"
    request = ImageGenerationRequest(
        prompt=prompt,
        negative_prompt=negative_prompt,
        seed=seed,
        quality_tier="premium",
    )
    result = image_provider.generate(request)
    reference_sha256 = _sha256_of_file(result.image_path)
    profile = CharacterVisualProfile(
        name=name,
        visual_seed=seed,
        appearance_description=appearance_description,
        reference_image_path=result.image_path,
        reference_image_sha256=reference_sha256,
    )
    store.put(profile, now=now)
    return profile


def _sha256_of_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
