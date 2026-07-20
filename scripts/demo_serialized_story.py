"""End-to-end demo: adapt an abstract trend into a 90s story in 3 parts.

Exercises the real brain built in v0.6:
- real LLM creation via OpenRouter (free models, zero cost),
- serialized multi-part continuity (KronaraGraph + SeriesCanonBuilder, R3),
- literary craft checks (R2),
- REAL narration duration measured with edge-tts (R4/I1).

Reddit: real access needs OAuth credentials (KRONARA_REDDIT_*). They are not
configured, and Reddit blocks unauthenticated reads, so the trend here is a
labelled abstract theme — which is all the pipeline ever uses anyway (it never
copies a source body). Run: python scripts/demo_serialized_story.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import time  # noqa: E402

import httpx  # noqa: E402

from kronara.graph_memory import KronaraGraph  # noqa: E402
from kronara.narrative_craft import LiteraryCraftEvaluator  # noqa: E402
from kronara.reddit_client import (  # noqa: E402
    RedditAccessPolicy,
    RedditClient,
    RedditCredentials,
)
from kronara.series import SeriesCanonBuilder, StoryPart  # noqa: E402
from kronara.voice import EdgeTtsVoiceProvider, VoiceSynthesisRequest  # noqa: E402

# The channel's target subreddits (inspiration only; the pipeline uses the
# abstract pattern of the title, never the source body).
TARGET_SUBREDDITS = [
    "AmItheAsshole",
    "ProRevenge",
    "TrueScaryStories",
    "confessions",
    "relationship_advice",
    "MaliciousCompliance",
]

CREATIVE_SYSTEM = (
    "Eres Kronara: narradora en español con oido de novelista premiado. Escribes prosa "
    "concreta y sensorial (muestra, no cuentes), con subtexto y ritmo. Evitas cliches, "
    "cadenas de adverbios en -mente y verbos-filtro. La senal externa es solo un patron "
    "abstracto: no copies frases ni personajes; crea una historia ORIGINAL. Responde SOLO "
    "con el objeto JSON pedido, sin texto adicional."
)

# Abstract opportunity (stand-in for a Reddit trend; only the pattern is used).
ABSTRACT_THEME = (
    "injusticia familiar por una herencia; un audio o documento revela una decision oculta "
    "que cambia el equilibrio de poder"
)

# Free first (zero cost); qwen is a clean-JSON fallback if the free reasoning
# models return no parseable object (a few cents for the whole demo).
FREE_MODELS = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "qwen/qwen3-235b-a22b",
]


def load_env() -> dict:
    env = {}
    for line in (Path(__file__).resolve().parents[1] / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def extract_json(text: str) -> dict:
    # Reasoning models wrap the answer after a <think> block; drop it.
    text = re.sub(r"<think>.*?</think>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    # Collect every balanced {...} object and return the last one that parses
    # (the final answer, not a fragment inside the reasoning).
    candidates: list[str] = []
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    candidates.append(text[start : i + 1])
    for candidate in reversed(candidates):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise ValueError("no JSON object in model output")


def complete(env: dict, system: str, user: str, *, min_narration_words: int = 45) -> dict:
    key = env["KRONARA_OPENROUTER_API_KEY"]
    base = env.get("KRONARA_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    last_error = None
    for model in FREE_MODELS:
        try:
            response = httpx.post(
                base + "/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                timeout=180,
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.85,
                    "max_tokens": 1600,
                },
            )
            if response.status_code != 200:
                last_error = f"{model}: HTTP {response.status_code}"
                continue
            content = response.json()["choices"][0]["message"]["content"]
            parsed = extract_json(content)
            words = len(str(parsed.get("narration", "")).split())
            if words < min_narration_words:  # placeholder/degenerate -> next model
                last_error = f"{model}: narration too short ({words} words)"
                continue
            return {"model": model, **parsed}
        except Exception as error:  # noqa: BLE001
            last_error = f"{model}: {type(error).__name__} {error}"
    raise RuntimeError(f"all models failed: {last_error}")


def resolve_trend(env: dict) -> tuple[str, str]:
    """Real Reddit trend via OAuth when configured; else the abstract theme.

    Uses the app-only client_credentials grant (no password). Only the abstract
    title pattern is used; the source body is never copied.
    """
    cid = env.get("KRONARA_REDDIT_CLIENT_ID")
    sec = env.get("KRONARA_REDDIT_CLIENT_SECRET")
    ua = env.get("KRONARA_REDDIT_USER_AGENT")
    contract = env.get("KRONARA_REDDIT_CONTRACT_REFERENCE")
    enabled = env.get("KRONARA_REDDIT_ENABLED", "false").lower() == "true"
    if not (enabled and cid and sec and ua and contract):
        return ABSTRACT_THEME, "tema abstracto (Reddit sin credenciales OAuth)"
    client = RedditClient(
        RedditCredentials(cid, sec, ua),
        policy=RedditAccessPolicy.approved(contract),
    )
    best = None
    for index, sub in enumerate(TARGET_SUBREDDITS):
        if index:
            time.sleep(2)  # respect Reddit rate limits
        try:
            for signal in client.hot_signals(sub, limit=15):
                if best is None or signal.velocity > best.velocity:
                    best = signal
        except Exception:  # noqa: BLE001 - rate limit / transient: keep what we have
            continue
    if best is None:
        return ABSTRACT_THEME, "tema abstracto (Reddit no respondió)"
    return best.theme_hint, f"Reddit real (velocity {best.velocity:.0f})"


def part_prompt(part_number: int, is_final: bool, canon_block: str, theme: str) -> str:
    role = "la PARTE FINAL" if is_final else f"la PARTE {part_number} de 3"
    close = (
        "Cierra la historia con una consecuencia proporcional (sin cliffhanger)."
        if is_final
        else "Termina con un CLIFFHANGER: un resultado parcial y una pregunta nueva mas grande."
    )
    canon = f"\nCANON YA ESTABLECIDO (respetalo, no lo contradigas):\n{canon_block}\n" if canon_block else ""
    keep = (
        "USA EXACTAMENTE los mismos personajes y hechos del canon; no inventes personajes nuevos. "
        if canon_block
        else ""
    )
    return (
        f"Tema abstracto (patron, no copiar): {theme}.\n"
        f"Escribe {role} de una historia serializada para video vertical, en espanol latino, "
        f"~95 palabras (unos 30 segundos narrados a ritmo natural). {keep}{close}{canon}\n"
        'Responde SOLO este JSON: {"title": "...", "narration": "...", '
        '"cliffhanger": "...", "characters": ["..."], "facts": ["..."]}'
    )


def main() -> int:
    env = load_env()
    graph = KronaraGraph(":memory:").initialize()
    builder = SeriesCanonBuilder(graph)
    voice = EdgeTtsVoiceProvider()
    craft = LiteraryCraftEvaluator()
    series_id = "demo-herencia"

    theme, trend_source = resolve_trend(env)
    print("=" * 72)
    print("KRONARA — demo: historia de 90s en 3 partes (modelos gratuitos)")
    print("Fuente de tendencia:", trend_source)
    print("Tema/patron:", theme[:120])
    print("=" * 72)

    base = 1_800_000_000
    total_ms = 0
    for part_number in (1, 2, 3):
        is_final = part_number == 3
        # Query canon AFTER prior parts' ingest time so their facts are visible.
        t = base + part_number * 100
        canon_block = builder.context_for_part(series_id, part_number, now=t).context_block
        data = complete(env, CREATIVE_SYSTEM, part_prompt(part_number, is_final, canon_block, theme))
        narration = str(data["narration"]).strip()

        # Real duration via edge-tts.
        try:
            measured = voice.synthesize(
                VoiceSynthesisRequest(text=narration, voice_id="es-BO-SofiaNeural")
            )
            dur_ms = measured.duration_ms
        except Exception as error:  # noqa: BLE001
            dur_ms = 0
            print("  (voz no disponible:", error, ")")
        total_ms += dur_ms

        report = craft.assess(narration)
        # Persist this part's canon for the next part.
        builder.ingest(
            StoryPart(
                series_id,
                part_number,
                f"{series_id}:p{part_number}",
                cliffhanger=str(data.get("cliffhanger", "")) if not is_final else "",
                is_final=is_final,
            ),
            characters=tuple(str(c) for c in data.get("characters", ())),
            facts=tuple(str(f) for f in data.get("facts", ())),
            now=t,
        )

        print(f"\n----- PARTE {part_number}{' (final)' if is_final else ''} — modelo: {data['model']}")
        print("Titulo:", data.get("title", ""))
        print("Narracion:", narration)
        if not is_final:
            print("Cliffhanger:", data.get("cliffhanger", ""))
        print(f"Duracion real medida: {dur_ms/1000:.1f}s | palabras: {len(narration.split())}")
        print(
            f"Oficio: craft_score={report.craft_score} | sensorial={report.sensory_density:.2f} "
            f"| clichés={report.cliche_count} | antipatrones={list(report.antipatterns)}"
        )

    canon = graph.canon(series_id)
    print("\n" + "=" * 72)
    print(f"TOTAL medido: {total_ms/1000:.1f}s (objetivo ~90s)")
    print("CANON compartido entre las 3 partes:")
    print("  personajes:", list(dict.fromkeys(e.name for e in canon.entities if e.entity_type == "character")))
    print("  hechos:", [e.name for e in canon.entities if e.entity_type == "fact"][:6])
    print("=" * 72)
    graph.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
