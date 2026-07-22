from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROGRAM_RESOURCE_LABELS: dict[str, str] = {
    "decisiones-dificiles": "Lunes - Decisiones Difíciles",
    "confesiones-anonimas": "Martes - Confesiones Anónimas",
    "cronicas-de-justicia": "Miércoles - Crónicas de Justicia",
    "mentes-ocultas": "Jueves - Mentes Ocultas",
    "viernes-paranormal": "Viernes - Paranormal",
    "historias-medianoche": "Sábado - Historias de Medianoche",
    "caso-de-la-semana": "Domingo - El Caso de la Semana",
}


@dataclass(frozen=True)
class StoryResourceItem:
    title: str
    length: str
    focus: str


def default_story_resource_path(resource_root: Path) -> Path:
    return resource_root / "knowledge" / "narrative" / "program-story-templates.md"


def story_resource_text(
    program_id: str,
    resource_root: Path,
    override_path: Path | str | None = None,
) -> str:
    override = _override_text(program_id, override_path)
    if override:
        return override
    return _base_section(program_id, resource_root)


def story_resource_source(program_id: str, override_path: Path | str | None = None) -> str:
    return "manual" if _override_text(program_id, override_path) else "base"


def story_resource_items(text: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    blocks = list(re.finditer(r"(?m)^###\s+(.+?)\s*$", text))
    for index, match in enumerate(blocks):
        start = match.end()
        end = blocks[index + 1].start() if index + 1 < len(blocks) else len(text)
        heading = match.group(1).strip()
        body = text[start:end].strip()
        items.append(
            {
                "title": _clean_title(heading),
                "length": _length_label(heading),
                "focus": _focus_line(body),
            }
        )
    return items


def save_story_resource_override(
    program_id: str,
    text: str,
    override_path: Path | str,
) -> str:
    if program_id not in PROGRAM_RESOURCE_LABELS:
        raise KeyError(program_id)
    cleaned = _clean_resource_text(text)
    if len(cleaned) < 80:
        raise ValueError("program story resource requires useful story text")
    path = Path(override_path)
    payload = _load_override_payload(path)
    payload.setdefault("schema_version", 1)
    payload.setdefault("programs", {})
    payload["programs"][program_id] = {
        "text": cleaned,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return cleaned


def reset_story_resource_override(
    program_id: str,
    resource_root: Path,
    override_path: Path | str,
) -> str:
    if program_id not in PROGRAM_RESOURCE_LABELS:
        raise KeyError(program_id)
    path = Path(override_path)
    payload = _load_override_payload(path)
    programs = dict(payload.get("programs", {}))
    programs.pop(program_id, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema_version": 1, "programs": programs}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return _base_section(program_id, resource_root)


def combined_story_resources_markdown(
    resource_root: Path,
    override_path: Path | str | None = None,
) -> str:
    source = default_story_resource_path(resource_root)
    if not source.exists():
        return ""
    parsed = _parse_markdown(source.read_text(encoding="utf-8"))
    overrides = _load_override_payload(Path(override_path)) if override_path else {"programs": {}}
    sections = dict(parsed["sections"])
    for program_id, raw_value in dict(overrides.get("programs", {})).items():
        label = PROGRAM_RESOURCE_LABELS.get(program_id)
        if not label:
            continue
        heading = _matching_heading(parsed["order"], label) or label
        text = str(raw_value.get("text", "")) if isinstance(raw_value, dict) else str(raw_value)
        if text.strip():
            sections[heading] = _clean_resource_text(text)
    lines = [parsed["intro"].rstrip()]
    for heading in parsed["order"]:
        body = sections.get(heading, "").strip()
        lines.append(f"## {heading}\n\n{body}")
    return "\n\n".join(part for part in lines if part.strip()).strip() + "\n"


def _base_section(program_id: str, resource_root: Path) -> str:
    label = PROGRAM_RESOURCE_LABELS.get(program_id)
    if not label:
        return ""
    source = default_story_resource_path(resource_root)
    if not source.exists():
        return ""
    parsed = _parse_markdown(source.read_text(encoding="utf-8"))
    heading = _matching_heading(parsed["order"], label)
    return parsed["sections"].get(heading or label, "").strip()


def _parse_markdown(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    intro: list[str] = []
    order: list[str] = []
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        if line.startswith("## ") and not line.startswith("### "):
            current = line[3:].strip()
            order.append(current)
            sections.setdefault(current, [])
            continue
        if current is None:
            intro.append(line)
        else:
            sections[current].append(line)
    return {
        "intro": "\n".join(intro).strip(),
        "order": order,
        "sections": {key: "\n".join(value).strip() for key, value in sections.items()},
    }


def _matching_heading(headings: list[str], label: str) -> str | None:
    wanted = _label_key(label)
    for heading in headings:
        if _label_key(heading) == wanted:
            return heading
    return None


def _label_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_marks).strip().casefold()


def _override_text(program_id: str, override_path: Path | str | None = None) -> str:
    if not override_path:
        return ""
    payload = _load_override_payload(Path(override_path))
    raw = dict(payload.get("programs", {})).get(program_id)
    if isinstance(raw, dict):
        return str(raw.get("text", "")).strip()
    if isinstance(raw, str):
        return raw.strip()
    return ""


def _load_override_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "programs": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"schema_version": 1, "programs": {}}
    if not isinstance(payload, dict) or int(payload.get("schema_version", 1)) != 1:
        return {"schema_version": 1, "programs": {}}
    if not isinstance(payload.get("programs", {}), dict):
        payload["programs"] = {}
    return payload


def _clean_resource_text(text: str) -> str:
    lines = [line.rstrip() for line in str(text).replace("\r\n", "\n").split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _clean_title(heading: str) -> str:
    title = re.sub(r"^\d+\.\s*", "", heading)
    title = re.sub(
        r"^Historia\s+(?:muy\s+)?(?:larga|mediana|corta|cinematografica|cinematográfica)\s*(?:\d+)?:?\s*",
        "",
        title,
        flags=re.I,
    )
    title = title.strip(" -–:")
    quoted = re.search(r'["“](.+?)["”]', title)
    return quoted.group(1).strip() if quoted else title.strip()


def _length_label(heading: str) -> str:
    low = heading.casefold()
    if "muy larga" in low:
        return "muy larga"
    if "larga" in low:
        return "larga"
    if "mediana" in low:
        return "mediana"
    if "corta" in low:
        return "corta"
    return "molde"


def _focus_line(body: str) -> str:
    for raw_line in body.splitlines():
        line = raw_line.strip().lstrip("- ").strip()
        if len(line) >= 30:
            return line[:220]
    return "Recurso narrativo editable para RAG."
