from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path


TEMPLATE_OVERRIDE_ENV = "KRONARA_PROGRAM_TEMPLATE_OVERRIDES"


@dataclass(frozen=True)
class ProgramNarrativeContract:
    program_id: str
    directives: tuple[str, ...]
    required_signals: tuple[str, ...]
    minimum_signals: int
    secondary_signals: tuple[str, ...] = ()
    minimum_secondary_signals: int = 0
    forbidden_if_unmotivated: tuple[str, ...] = ()


PROGRAM_NARRATIVE_CONTRACTS: dict[str, ProgramNarrativeContract] = {
    "decisiones-dificiles": ProgramNarrativeContract(
        program_id="decisiones-dificiles",
        directives=(
            "Programa Lunes - Decisiones Dificiles: la historia debe girar alrededor de un dilema moral personal, no de accion externa.",
            "Estructura obligatoria: vida normal, peticion o descubrimiento que rompe la paz, dos opciones malas, presion familiar/social, decision irreversible, costo emocional visible y pregunta final sin respuesta facil.",
            "El protagonista debe elegir activamente entre lealtad, verdad, ley, culpa, perdon o supervivencia emocional.",
            "Evita finales limpios: el cierre debe dejar una cicatriz moral, como culpa, perdida de familia, soledad o duda persistente.",
        ),
        required_signals=("decid", "eleg", "opcion", "opciones", "dilema", "promesa", "denunci", "callar", "perdon", "culpa"),
        minimum_signals=2,
        secondary_signals=("madre", "padre", "hermana", "familia", "amigo", "novia", "hospital", "policia", "policía", "ilegal"),
        minimum_secondary_signals=1,
        forbidden_if_unmotivated=("fantasma", "entidad", "aparicion", "aparición", "sobrenatural"),
    ),
    "confesiones-anonimas": ProgramNarrativeContract(
        program_id="confesiones-anonimas",
        directives=(
            "Programa Martes - Confesiones Anonimas: debe sentirse como una confesion en primera persona, intima y vergonzosa.",
            "Estructura obligatoria: secreto inicial, mentira sostenida, dano causado, casi descubrimiento, confesion interna, consecuencia emocional y cierre con miedo a decir la verdad.",
            "La historia no busca justicia externa; busca el peso de vivir con algo que nadie sabe.",
            "Debe incluir culpa concreta, autoengaño y un detalle cotidiano que se vuelva insoportable.",
        ),
        required_signals=("confes", "secreto", "menti", "nunca dije", "nadie sabe", "culpa", "verdad", "fing"),
        minimum_signals=2,
        secondary_signals=("yo", "mi ", "me ", "padres", "amiga", "hermano", "relacion", "relación"),
        minimum_secondary_signals=2,
    ),
    "cronicas-de-justicia": ProgramNarrativeContract(
        program_id="cronicas-de-justicia",
        directives=(
            "Programa Miercoles - Cronicas de Justicia: debe ser una cadena de traicion, pruebas y consecuencias.",
            "Estructura obligatoria: abuso o traicion verificable, decision de no confrontar todavia, recoleccion de pruebas, jugada legal/laboral/social, caida del culpable y costo de la victoria.",
            "El placer narrativo esta en ver como la evidencia cambia el poder; no basta con venganza impulsiva.",
            "Incluye pruebas concretas: mensajes, correos, fotos, transferencias, abogados, policia, auditoria o testigos.",
        ),
        required_signals=("prueba", "evidencia", "mensaje", "correo", "abogado", "policia", "policía", "demanda", "investig", "document"),
        minimum_signals=2,
        secondary_signals=("traicion", "traición", "consecuencia", "despid", "arrest", "juicio", "empresa", "reputacion", "reputación"),
        minimum_secondary_signals=1,
        forbidden_if_unmotivated=("fantasma", "entidad", "sobrenatural", "aparicion", "aparición"),
    ),
    "mentes-ocultas": ProgramNarrativeContract(
        program_id="mentes-ocultas",
        directives=(
            "Programa Jueves - Mentes Ocultas: debe explorar manipulacion psicologica, percepcion, control o una mente que se quiebra lentamente.",
            "Estructura obligatoria: relacion aparentemente normal, patron raro, aislamiento, duda de la propia memoria, prueba de manipulacion, intento de escapar y residuo psicologico.",
            "La amenaza principal no es un monstruo: es una persona, sistema o dinamica que distorsiona la realidad del protagonista.",
            "Debe mostrar señales de gaslighting, dependencia, identidad robada, control, paranoia racional o abuso psicologico.",
        ),
        required_signals=("manipul", "control", "gaslight", "memoria", "paranoi", "ansiedad", "identidad", "mentira", "dudar", "psicolog"),
        minimum_signals=2,
        secondary_signals=("pareja", "jefe", "hermana", "trabajo", "terapia", "aisl", "amenaz", "culpa"),
        minimum_secondary_signals=1,
        forbidden_if_unmotivated=("fantasma", "entidad", "aparicion", "aparición", "casa embrujada"),
    ),
    "viernes-paranormal": ProgramNarrativeContract(
        program_id="viernes-paranormal",
        directives=(
            "Programa Viernes Paranormal: debe ser terror sobrenatural, no cuento literario abstracto.",
            "La amenaza debe ser una presencia paranormal clara: fantasma, entidad, figura oscura, casa embrujada, pasos sin cuerpo, puerta que se abre sola, voz imposible, aparicion o posesion.",
            "La trama debe entenderse en una primera escucha: quien narra, donde esta, que quiere, que aparece, que empeora y por que huye o queda marcado.",
            "Usa una estructura tipo relato paranormal: normalidad inicial, primera senal, repeticion, intento de explicacion, escalada, testigo/dato externo, confrontacion, acercamiento, huida y residuo final.",
            "Evita metaforas opacas, contratos magicos vagos, frases cortadas como 'El.' o 'Un.', y objetos simbolicos que no expliquen la amenaza.",
            "Cada escena debe tener un ancla visual concreta para imagen: habitacion, esquina oscura, armario, pasillo, puerta, escalera, sombra, telefono, ventana o sofa.",
        ),
        required_signals=(
            "fantasma", "aparicion", "aparición", "entidad", "sombra", "figura", "casa embrujada",
            "embrujad", "pasos", "puerta", "armario", "esquina", "habitacion", "habitación",
            "pasillo", "respiracion", "respiración", "voz", "3:00", "3 de la mañana",
            "sobrenatural", "paranormal", "pose", "presencia",
        ),
        minimum_signals=3,
        secondary_signals=("casa", "habitacion", "habitación", "cuarto", "sala", "pasillo", "armario", "esquina", "sofa", "sofá", "puerta", "escalera", "ventana"),
        minimum_secondary_signals=2,
    ),
    "historias-medianoche": ProgramNarrativeContract(
        program_id="historias-medianoche",
        directives=(
            "Programa Sabado - Historias de Medianoche: relato largo, cinematografico y nocturno, con misterio de alto concepto.",
            "Estructura obligatoria: escenario memorable, regla imposible, exploracion, escalada por escenas, descubrimiento del origen, decision final y giro visual de cierre.",
            "Puede ser sobrenatural o fantastico, pero siempre debe sentirse como una pelicula: tren nocturno, mansion, pueblo, carretera, hotel, cuarto imposible o bucle temporal.",
            "Cada escena debe ampliar el mundo y dejar una imagen fuerte para video vertical.",
        ),
        required_signals=("noche", "medianoche", "madrugada", "3:", "tren", "mansion", "mansión", "pueblo", "carretera", "hotel", "habitacion", "habitación", "bucle", "mapa"),
        minimum_signals=2,
        secondary_signals=("regla", "escapar", "descub", "luces", "reloj", "estacion", "estación", "espejo", "puerta", "final"),
        minimum_secondary_signals=1,
    ),
    "caso-de-la-semana": ProgramNarrativeContract(
        program_id="caso-de-la-semana",
        directives=(
            "Programa Domingo - El Caso de la Semana: episodio premium serio, profundo y con peso emocional.",
            "Estructura obligatoria: caso central, contexto humano, secreto o delito, investigacion progresiva, evidencia, consecuencias legales/familiares, reflexion final.",
            "Debe sentirse como caso documentado o reconstruccion dramatizada, no como cuento abstracto ni creepypasta.",
            "Si toca violencia, abuso o crimen, maneja el tema con gravedad y evita sensacionalismo.",
        ),
        required_signals=("caso", "investig", "evidencia", "denunci", "policia", "policía", "juicio", "familia", "secreto", "delito", "victima", "víctima"),
        minimum_signals=2,
        secondary_signals=("conden", "prision", "prisión", "terapia", "madre", "padre", "abuso", "asesin", "legal", "verdad"),
        minimum_secondary_signals=1,
        forbidden_if_unmotivated=("fantasma", "entidad", "sobrenatural", "casa embrujada"),
    ),
}


def narrative_contract(program_id: str | None, override_path: Path | str | None = None) -> list[str]:
    override = _override_contract(program_id, override_path)
    if override:
        return override
    contract = PROGRAM_NARRATIVE_CONTRACTS.get(program_id or "")
    return list(contract.directives) if contract else []


def save_narrative_contract_override(
    program_id: str,
    directives: list[str],
    override_path: Path | str,
) -> list[str]:
    if program_id not in PROGRAM_NARRATIVE_CONTRACTS:
        raise KeyError(program_id)
    cleaned = [str(item).strip() for item in directives if str(item).strip()]
    if len(cleaned) < 3:
        raise ValueError("program narrative template requires at least three lines")
    path = Path(override_path)
    payload = _load_override_payload(path)
    payload.setdefault("schema_version", 1)
    payload.setdefault("programs", {})
    payload["programs"][program_id] = cleaned
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return cleaned


def reset_narrative_contract_override(program_id: str, override_path: Path | str) -> list[str]:
    path = Path(override_path)
    payload = _load_override_payload(path)
    programs = dict(payload.get("programs", {}))
    programs.pop(program_id, None)
    payload = {"schema_version": 1, "programs": programs}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return narrative_contract(program_id, override_path=None)


def narrative_contract_source(program_id: str | None, override_path: Path | str | None = None) -> str:
    return "manual" if _override_contract(program_id, override_path) else "base"


def program_quality_findings(
    program_id: str | None, script_text: str, scene_texts: tuple[str, ...]
) -> tuple[str, ...]:
    contract = PROGRAM_NARRATIVE_CONTRACTS.get(program_id or "")
    if contract is None:
        return ()
    text = f"{script_text}\n" + "\n".join(scene_texts)
    low = text.casefold()
    findings: list[str] = []
    if re.search(r"(^|\s)(el|la|un|una)\.\s*($|\n)", low):
        findings.append("fragmented_articles")
    if _signal_count(low, contract.required_signals) < contract.minimum_signals:
        findings.append(
            "missing_clear_paranormal_threat"
            if program_id == "viernes-paranormal"
            else f"missing_{program_id}_core_signals"
        )
    if (
        contract.minimum_secondary_signals
        and _signal_count(low, contract.secondary_signals) < contract.minimum_secondary_signals
    ):
        findings.append(
            "missing_haunted_place_anchors"
            if program_id == "viernes-paranormal"
            else f"missing_{program_id}_specific_anchors"
        )
    if _has_unmotivated_forbidden_terms(low, contract):
        findings.append(f"off_brand_{program_id}_elements")
    if program_id == "viernes-paranormal":
        if not any("?" in scene or "quiere" in scene.casefold() for scene in scene_texts):
            findings.append("weak_story_question")
        if "contrato" in low and not any(term in low for term in ("entidad", "fantasma", "sombra", "aparicion", "aparición")):
            findings.append("abstract_bargain_not_paranormal")
    return tuple(dict.fromkeys(findings))


def _signal_count(text: str, signals: tuple[str, ...]) -> int:
    return sum(1 for signal in signals if signal.casefold() in text)


def _has_unmotivated_forbidden_terms(text: str, contract: ProgramNarrativeContract) -> bool:
    if not any(term.casefold() in text for term in contract.forbidden_if_unmotivated):
        return False
    return _signal_count(text, contract.required_signals) < contract.minimum_signals


def _override_contract(program_id: str | None, override_path: Path | str | None = None) -> list[str]:
    if not program_id:
        return []
    path = _resolved_override_path(override_path)
    if path is None:
        return []
    payload = _load_override_payload(path)
    raw = dict(payload.get("programs", {})).get(program_id)
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _resolved_override_path(override_path: Path | str | None = None) -> Path | None:
    if override_path:
        return Path(override_path)
    env_path = os.environ.get(TEMPLATE_OVERRIDE_ENV)
    return Path(env_path) if env_path else None


def _load_override_payload(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": 1, "programs": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"schema_version": 1, "programs": {}}
    if not isinstance(payload, dict):
        return {"schema_version": 1, "programs": {}}
    if int(payload.get("schema_version", 1)) != 1:
        return {"schema_version": 1, "programs": {}}
    if not isinstance(payload.get("programs", {}), dict):
        payload["programs"] = {}
    return payload
