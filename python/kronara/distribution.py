from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class PublicationStatus(StrEnum):
    PENDING = "pending"
    PUBLISHED = "published"
    AMBIGUOUS = "ambiguous"
    FAILED = "failed"


@dataclass(frozen=True)
class PublicationIntent:
    episode_id: str
    variant_id: str
    platform: str
    idempotency_key: str


@dataclass(frozen=True)
class PublicationReceipt:
    status: PublicationStatus
    remote_id: str | None = None


class MetaTransport(Protocol):
    def upload(self, intent: PublicationIntent) -> dict: ...
    def find_by_idempotency_key(self, key: str) -> dict | None: ...


class MetaPublisher:
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

