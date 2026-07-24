"""Per-program visual identity — style/negative prompts, motion character, and
asset-selection tags, loaded from ``config/programs/visual_style.v1.json``
(same registry pattern as ``EmbeddingRegistry``).

Keeps program identity distinguishable end to end: Viernes Paranormal reads
as fog and sickly green dread, Cronicas de Justicia reads as documentary
offices and evidence, without the image-generation or composition code
knowing anything about specific programs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from kronara.resource_root import resource_root

MOTION_BIASES = frozenset({"subtle", "standard", "dynamic"})


@dataclass(frozen=True)
class VisualStyleDescriptor:
    program_id: str
    display_name: str
    weekday: str
    style_prompt: str
    negative_prompt: str
    motion_bias: str
    music_moods: tuple[str, ...]
    asset_tags: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.program_id or not self.display_name:
            raise ValueError("visual style identity is required")
        if not self.style_prompt.strip():
            raise ValueError("style_prompt is required")
        if self.motion_bias not in MOTION_BIASES:
            raise ValueError(f"unknown motion_bias: {self.motion_bias}")


class VisualStyleRegistry:
    def __init__(self, descriptors: tuple[VisualStyleDescriptor, ...]):
        self._descriptors = {item.program_id: item for item in descriptors}
        if len(self._descriptors) != len(descriptors):
            raise ValueError("duplicate program_id")

    @classmethod
    def load(cls, path: Path) -> "VisualStyleRegistry":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if int(payload.get("schema_version", 0)) != 1:
            raise ValueError("unsupported visual style registry schema")
        return cls(
            tuple(
                VisualStyleDescriptor(
                    program_id=str(item["program_id"]),
                    display_name=str(item["display_name"]),
                    weekday=str(item["weekday"]),
                    style_prompt=str(item["style_prompt"]),
                    negative_prompt=str(item.get("negative_prompt", "")),
                    motion_bias=str(item.get("motion_bias", "standard")),
                    music_moods=tuple(str(value) for value in item.get("music_moods", ())),
                    asset_tags=tuple(str(value) for value in item.get("asset_tags", ())),
                )
                for item in payload["programs"]
            )
        )

    def get(self, program_id: str) -> VisualStyleDescriptor:
        return self._descriptors[program_id]

    @property
    def program_ids(self) -> tuple[str, ...]:
        return tuple(self._descriptors.keys())


def default_registry_path() -> Path:
    return resource_root() / "config" / "programs" / "visual_style.v1.json"


# ---- Named style library (v0.8) -----------------------------------------
# The per-program registry above ties one style to one program. The named
# library below is program-independent: a catalog of reusable styles keyed
# by ``style_id`` (anime-neo-noir, acuarela-melancolica, ...). A program (or
# a per-episode override) references a style_id; users can also add custom
# styles from Configuración. Both share ``apply_style`` because a
# NamedVisualStyle exposes ``.style_prompt`` / ``.negative_prompt`` just like
# VisualStyleDescriptor.


@dataclass(frozen=True)
class NamedVisualStyle:
    style_id: str
    name: str
    identidad: str
    style_prompt: str
    negative_prompt: str
    motion_bias: str
    music_moods: tuple[str, ...]
    asset_tags: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.style_id or not self.name:
            raise ValueError("named style identity is required")
        if not self.style_prompt.strip():
            raise ValueError("style_prompt is required")
        if self.motion_bias not in MOTION_BIASES:
            raise ValueError(f"unknown motion_bias: {self.motion_bias}")

    @property
    def is_master_style(self) -> bool:
        """A named style's ``style_prompt`` is a complete master prompt that
        already fixes the medium, palette, composition and 9:16 framing. The
        shot builder reads this flag to *suppress* its photographic-realism
        defaults ("cinematic photograph", "35mm film stock") so a pixel-art or
        watercolor style isn't muddied by film-grain wording it never asked
        for. Legacy VisualStyleDescriptor lacks this attribute (its prompt is
        additive), so ``getattr(style, "is_master_style", False)`` keeps the
        per-program path untouched."""
        return True


class StyleLibrary:
    """Catalog of reusable named visual styles (config/visual_styles/styles.v1.json).

    Each style's ``style_prompt``/``negative_prompt`` already includes the
    registry-wide universal base and consistency note, composed at load time,
    so ``apply_style`` needs no changes and every shot inherits the shared
    9:16/no-text/consistency guidance automatically."""

    def __init__(
        self,
        styles: "tuple[NamedVisualStyle, ...]",
        *,
        universal_base: str = "",
        universal_negative: str = "",
        consistency_note: str = "",
    ):
        self._styles = {item.style_id: item for item in styles}
        if len(self._styles) != len(styles):
            raise ValueError("duplicate style_id")
        self.universal_base = universal_base
        self.universal_negative = universal_negative
        self.consistency_note = consistency_note

    @classmethod
    def load(cls, path: Path) -> "StyleLibrary":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls._from_payload(payload)

    @classmethod
    def load_merged(cls, base_path: Path, custom_path: "Path | None") -> "StyleLibrary":
        """Base 10 styles overlaid with the user's custom styles (data_dir).
        A custom style sharing a base style_id shadows it (lets users edit a
        built-in); a new style_id is added. Custom styles inherit the base
        file's universal_base/negative/consistency_note."""
        payload = json.loads(Path(base_path).read_text(encoding="utf-8"))
        return cls._from_payload(payload, extra_styles=read_custom_styles(custom_path))

    @classmethod
    def _from_payload(
        cls, payload: dict, *, extra_styles: "tuple[dict, ...] | list[dict]" = ()
    ) -> "StyleLibrary":
        if int(payload.get("schema_version", 0)) != 1:
            raise ValueError("unsupported style library schema")
        base = str(payload.get("universal_base", ""))
        base_negative = str(payload.get("universal_negative", ""))
        note = str(payload.get("consistency_note", ""))

        def compose_prompt(master: str) -> str:
            parts = [master.strip(), base.strip(), note.strip()]
            return ", ".join(part for part in parts if part)

        def compose_negative(negative: str) -> str:
            parts = [negative.strip(), base_negative.strip()]
            return ", ".join(part for part in parts if part)

        # Merge raw styles by style_id so a custom style overrides its base twin
        # (dict preserves base insertion order, then custom updates in place).
        merged: dict[str, dict] = {}
        for item in list(payload["styles"]) + list(extra_styles):
            merged[str(item["style_id"])] = item

        styles = tuple(
            NamedVisualStyle(
                style_id=str(item["style_id"]),
                name=str(item["name"]),
                identidad=str(item.get("identidad", "")),
                style_prompt=compose_prompt(str(item["style_prompt"])),
                negative_prompt=compose_negative(str(item.get("negative_prompt", ""))),
                motion_bias=str(item.get("motion_bias", "standard")),
                music_moods=tuple(str(value) for value in item.get("music_moods", ())),
                asset_tags=tuple(str(value) for value in item.get("asset_tags", ())),
            )
            for item in merged.values()
        )
        return cls(
            styles,
            universal_base=base,
            universal_negative=base_negative,
            consistency_note=note,
        )

    def get(self, style_id: str) -> NamedVisualStyle:
        return self._styles[style_id]

    def find(self, style_id: str | None) -> "NamedVisualStyle | None":
        """Non-raising lookup: None when style_id is missing/unknown, so the
        pipeline degrades to no-style instead of failing a whole run over a
        typo'd override."""
        if not style_id:
            return None
        return self._styles.get(style_id)

    def list(self) -> "tuple[NamedVisualStyle, ...]":
        return tuple(self._styles.values())

    @property
    def style_ids(self) -> tuple[str, ...]:
        return tuple(self._styles.keys())


def default_style_library_path() -> Path:
    return resource_root() / "config" / "visual_styles" / "styles.v1.json"


# ---- Custom styles: user-added / edited styles persisted in data_dir --------
# Mirrors the program-template override pattern: shipped base styles live in
# resource_root/config, the user's additions/edits live in a JSON file under
# the runtime data_dir. Stored RAW (uncomposed) so the editor round-trips the
# exact text the user typed; StyleLibrary composes the universal base on load.

REQUIRED_STYLE_FIELDS = ("style_id", "name", "style_prompt")


def read_custom_styles(path: "Path | None") -> list[dict]:
    """The user's custom styles (raw dicts), or [] when the file is absent or
    unreadable -- a corrupt override never breaks the shipped base styles."""
    if not path:
        return []
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return []
    styles = payload.get("styles", [])
    return [dict(item) for item in styles] if isinstance(styles, list) else []


def _write_custom_styles(path: Path, styles: list[dict]) -> None:
    payload = {"schema_version": 1, "styles": styles}
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _normalize_style_payload(style: dict) -> dict:
    """Validate + coerce a raw style dict into the canonical shape, raising
    ValueError on anything a NamedVisualStyle would reject (empty id/name/
    prompt, bad motion_bias). Building the dataclass reuses that validation."""
    missing = [field for field in REQUIRED_STYLE_FIELDS if not str(style.get(field, "")).strip()]
    if missing:
        raise ValueError(f"style is missing required fields: {', '.join(missing)}")
    normalized = {
        "style_id": str(style["style_id"]).strip(),
        "name": str(style["name"]).strip(),
        "identidad": str(style.get("identidad", "")).strip(),
        "style_prompt": str(style["style_prompt"]).strip(),
        "negative_prompt": str(style.get("negative_prompt", "")).strip(),
        "motion_bias": str(style.get("motion_bias", "standard")).strip() or "standard",
        "music_moods": [str(v) for v in style.get("music_moods", []) if str(v).strip()],
        "asset_tags": [str(v) for v in style.get("asset_tags", []) if str(v).strip()],
    }
    # Reuse the dataclass validators (motion_bias membership, non-empty prompt).
    NamedVisualStyle(
        style_id=normalized["style_id"],
        name=normalized["name"],
        identidad=normalized["identidad"],
        style_prompt=normalized["style_prompt"],
        negative_prompt=normalized["negative_prompt"],
        motion_bias=normalized["motion_bias"],
        music_moods=tuple(normalized["music_moods"]),
        asset_tags=tuple(normalized["asset_tags"]),
    )
    return normalized


def upsert_custom_style(custom_path: Path, style: dict) -> dict:
    """Add or replace a custom style by style_id; returns the normalized dict."""
    normalized = _normalize_style_payload(style)
    styles = read_custom_styles(custom_path)
    styles = [item for item in styles if str(item.get("style_id")) != normalized["style_id"]]
    styles.append(normalized)
    _write_custom_styles(custom_path, styles)
    return normalized


def delete_custom_style(custom_path: Path, style_id: str) -> bool:
    """Remove a custom style; returns True if one was removed. Base styles are
    never touched (they don't live in this file)."""
    styles = read_custom_styles(custom_path)
    kept = [item for item in styles if str(item.get("style_id")) != str(style_id)]
    if len(kept) == len(styles):
        return False
    _write_custom_styles(custom_path, kept)
    return True


def list_styles(base_path: Path, custom_path: "Path | None") -> list[dict]:
    """The catalog for the UI: shipped base styles plus custom ones, RAW (for
    editing), each tagged ``source`` = base | custom | custom-override so the
    frontend can show which are built-in, user-added, or user-edited built-ins.
    A custom style shadowing a base style_id reports ``custom-override``."""
    base_payload = json.loads(Path(base_path).read_text(encoding="utf-8"))
    base_ids = {str(item["style_id"]) for item in base_payload.get("styles", [])}
    custom = {str(item["style_id"]): item for item in read_custom_styles(custom_path)}

    def shape(item: dict, source: str) -> dict:
        return {
            "style_id": str(item["style_id"]),
            "name": str(item.get("name", "")),
            "identidad": str(item.get("identidad", "")),
            "style_prompt": str(item.get("style_prompt", "")),
            "negative_prompt": str(item.get("negative_prompt", "")),
            "motion_bias": str(item.get("motion_bias", "standard")),
            "music_moods": list(item.get("music_moods", [])),
            "asset_tags": list(item.get("asset_tags", [])),
            "source": source,
        }

    rows: list[dict] = []
    for item in base_payload.get("styles", []):
        sid = str(item["style_id"])
        if sid in custom:
            rows.append(shape(custom[sid], "custom-override"))
        else:
            rows.append(shape(item, "base"))
    for sid, item in custom.items():
        if sid not in base_ids:
            rows.append(shape(item, "custom"))
    return rows


class StyleResolver:
    """Picks the one visual style an episode renders under, newest signal first:

    1. an explicit per-episode ``style_id`` override (user picked it in Estudio
       or the chat guided flow),
    2. else the program's configured ``visual_style_id``,

    both looked up in the named :class:`StyleLibrary`. If neither resolves to a
    known named style, it falls back to the legacy per-program
    :class:`VisualStyleRegistry` so the seven original programs keep working
    even before their config points at a named style. Returns ``None`` when
    nothing matches (standalone stories with no program and no override), which
    ``apply_style`` treats as "no styling"."""

    def __init__(
        self,
        *,
        library: "StyleLibrary | None" = None,
        program_styles: "dict[str, str] | None" = None,
        legacy_registry: "VisualStyleRegistry | None" = None,
    ):
        self._library = library
        self._program_styles = dict(program_styles or {})
        self._legacy = legacy_registry

    def resolve(
        self, *, program_id: str | None = None, style_id: str | None = None
    ) -> "NamedVisualStyle | VisualStyleDescriptor | None":
        chosen = style_id or (self._program_styles.get(program_id) if program_id else None)
        if chosen and self._library is not None:
            named = self._library.find(chosen)
            if named is not None:
                return named
        if self._legacy is not None and program_id:
            try:
                return self._legacy.get(program_id)
            except KeyError:
                return None
        return None


def default_style_resolver(custom_styles_path: "Path | None" = None) -> StyleResolver:
    """Build the resolver from the three shipped configs: the named style
    library (base 10 + the user's custom styles when ``custom_styles_path`` is
    given), the program→style_id map (programs.v1.json), and the legacy
    per-program registry as a safety net. Best-effort per source so a missing
    or malformed config degrades one layer instead of crashing the sidecar."""
    library = None
    try:
        if custom_styles_path is not None:
            library = StyleLibrary.load_merged(default_style_library_path(), custom_styles_path)
        else:
            library = StyleLibrary.load(default_style_library_path())
    except Exception:
        library = None
    program_styles: dict[str, str] = {}
    try:
        from kronara.programs import ProgramRegistry, default_registry_path as programs_path

        registry = ProgramRegistry.load(programs_path())
        program_styles = {
            pid: registry.get(pid).visual_style_id for pid in registry.program_ids
        }
    except Exception:
        program_styles = {}
    legacy = None
    try:
        legacy = VisualStyleRegistry.load(default_registry_path())
    except Exception:
        legacy = None
    return StyleResolver(
        library=library, program_styles=program_styles, legacy_registry=legacy
    )


def apply_style(
    base_prompt: str, base_negative_prompt: str, style: VisualStyleDescriptor | None
) -> tuple[str, str]:
    """Combine a shot's creative prompt with a program's visual identity. A
    ``None`` style (standalone stories with no program_id) returns the base
    prompts unchanged, so styling stays fully optional."""
    if style is None:
        return base_prompt, base_negative_prompt
    prompt = f"{base_prompt}, {style.style_prompt}" if base_prompt.strip() else style.style_prompt
    negatives = [text for text in (base_negative_prompt.strip(), style.negative_prompt.strip()) if text]
    return prompt, ", ".join(negatives)
