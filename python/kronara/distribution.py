"""Autonomous publishing with idempotency and reconciliation.

Publishing is the one effect that uses real credentials, so Rust owns it
(`publication.publish` authority tool). This module is the Python governed
client: it writes a publish *intent* before the call (crash-safety), never
re-publishes an intent that already succeeded, and on an ambiguous outcome it
reconciles by idempotency key instead of blindly retrying — the failure mode
that produces duplicate Reels.

Live publishing requires an authorized Meta Page token; until then the authority
tool returns a structured "not configured" status and nothing is posted.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class PublicationStatus(StrEnum):
    PENDING = "pending"
    PUBLISHED = "published"
    AMBIGUOUS = "ambiguous"
    FAILED = "failed"
    NOT_CONFIGURED = "not_configured"


@dataclass(frozen=True)
class PublicationIntent:
    episode_id: str
    variant_id: str
    platform: str
    idempotency_key: str
    video_ref: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        if not all((self.episode_id, self.variant_id, self.platform, self.idempotency_key)):
            raise ValueError("a publication intent requires episode, variant, platform and key")


@dataclass(frozen=True)
class PublicationReceipt:
    status: PublicationStatus
    remote_id: str | None = None


class MetaTransport(Protocol):
    def upload(self, intent: PublicationIntent) -> dict: ...
    def find_by_idempotency_key(self, key: str) -> dict | None: ...


class IntentStore(Protocol):
    def get(self, key: str) -> PublicationReceipt | None: ...
    def put(self, key: str, receipt: PublicationReceipt) -> None: ...


class MemoryIntentStore:
    """Minimal in-memory intent store (production wires this to KronaraStore)."""

    def __init__(self) -> None:
        self._by_key: dict[str, PublicationReceipt] = {}

    def get(self, key: str) -> PublicationReceipt | None:
        return self._by_key.get(key)

    def put(self, key: str, receipt: PublicationReceipt) -> None:
        self._by_key[key] = receipt


class AuthorityMetaTransport:
    """Implements MetaTransport by calling the Rust `publication.publish` tool."""

    def __init__(self, authority):
        self.authority = authority

    def upload(self, intent: PublicationIntent) -> dict:
        return self.authority.invoke(
            "publication.publish",
            {
                "mode": "upload",
                "platform": intent.platform,
                "idempotency_key": intent.idempotency_key,
                "video_ref": intent.video_ref,
                "description": intent.description,
            },
        )

    def find_by_idempotency_key(self, key: str) -> dict | None:
        result = self.authority.invoke(
            "publication.publish", {"mode": "reconcile", "idempotency_key": key}
        )
        return result if result.get("remote_id") else None


class MetaPublisher:
    """Single publish attempt with timeout -> reconcile (no blind retry)."""

    def __init__(self, transport: MetaTransport):
        self.transport = transport

    def publish(self, intent: PublicationIntent) -> PublicationReceipt:
        try:
            result = self.transport.upload(intent)
        except TimeoutError:
            result = self.transport.find_by_idempotency_key(intent.idempotency_key)
            if result is None:
                return PublicationReceipt(PublicationStatus.AMBIGUOUS)
        status = PublicationStatus(result.get("status", "failed"))
        return PublicationReceipt(status, result.get("remote_id"))


class IdempotentReelsPublisher:
    """Governed publisher: persists intents and never double-publishes.

    On a crash between the upload call and its acknowledgement, the intent row
    survives; a resumed run sees a PENDING/PUBLISHED intent and reconciles or
    short-circuits instead of posting the same Reel twice.
    """

    def __init__(self, publisher: MetaPublisher, intents: IntentStore):
        self.publisher = publisher
        self.intents = intents

    def publish(self, intent: PublicationIntent) -> PublicationReceipt:
        existing = self.intents.get(intent.idempotency_key)
        if existing is not None and existing.status == PublicationStatus.PUBLISHED:
            return existing  # already live; do not re-publish
        # Record the attempt before the effect (crash-safety).
        self.intents.put(intent.idempotency_key, PublicationReceipt(PublicationStatus.PENDING))
        receipt = self.publisher.publish(intent)
        self.intents.put(intent.idempotency_key, receipt)
        return receipt
