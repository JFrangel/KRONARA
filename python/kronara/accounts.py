"""Multi-cuenta de publicación (Fase 5): qué canal/plataforma publica cada modo.

SEGURIDAD: los tokens no viven aquí. Cada cuenta referencia el NOMBRE de la
variable de entorno que la respalda (``token_env``); ``account_status`` solo
reporta si esa variable ESTÁ PRESENTE (bool), nunca su valor. La autoridad Node
es la única que lee el valor real al publicar.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from kronara.resource_root import resource_root


def _default_path() -> Path:
    return resource_root() / "config" / "accounts" / "accounts.v1.json"


@dataclass(frozen=True)
class Account:
    id: str
    platform: str
    label: str
    token_env: str
    id_env: str
    content_kinds: tuple[str, ...]
    enabled: bool


def _account(raw: dict[str, Any]) -> Account:
    return Account(
        id=str(raw.get("id", "")),
        platform=str(raw.get("platform", "")),
        label=str(raw.get("label", raw.get("id", ""))),
        token_env=str(raw.get("token_env", "")),
        id_env=str(raw.get("id_env", "")),
        content_kinds=tuple(str(k) for k in raw.get("content_kinds", ())),
        enabled=bool(raw.get("enabled", False)),
    )


@lru_cache(maxsize=4)
def load_accounts(path: str | None = None) -> tuple[Account, ...]:
    target = Path(path) if path else _default_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    return tuple(_account(item) for item in data.get("accounts", ()))


def account_status(account: Account, env: dict[str, str]) -> dict[str, Any]:
    """Vista segura de una cuenta: incluye si el token/credencial está presente
    (bool), NUNCA el valor. ``configured`` = habilitada y con token presente."""
    token_present = bool(account.token_env and env.get(account.token_env))
    id_present = bool(account.id_env and env.get(account.id_env)) if account.id_env else True
    return {
        "id": account.id,
        "platform": account.platform,
        "label": account.label,
        "content_kinds": list(account.content_kinds),
        "enabled": account.enabled,
        "token_env": account.token_env,
        "token_present": token_present,
        "id_present": id_present,
        "configured": account.enabled and token_present and id_present,
    }


def accounts_for_content_kind(content_kind: str, env: dict[str, str], path: str | None = None) -> list[dict[str, Any]]:
    """Cuentas configuradas que publican este modo -- lo que el scheduler/producer
    consultaría para saber a dónde enviar cada episodio."""
    out = []
    for account in load_accounts(path):
        if content_kind in account.content_kinds:
            status = account_status(account, env)
            if status["configured"]:
                out.append(status)
    return out
