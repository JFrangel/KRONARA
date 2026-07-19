from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RightsMode(StrEnum):
    OWNED_ORIGINAL = "owned_original"
    LICENSED_ADAPTATION = "licensed_adaptation"
    REFERENCE_ONLY = "reference_only"


@dataclass(frozen=True)
class TrainingAsset:
    asset_id: str
    rights_mode: RightsMode
    source_uri: str
    permission_evidence_uri: str | None = None
    allows_training: bool = False
    allows_commercial: bool = False


@dataclass(frozen=True)
class TrainingRightsDecision:
    allowed: bool
    code: str
    evidence_uri: str | None = None


class TrainingRightsPolicy:
    def decide(
        self, asset: TrainingAsset, *, commercial_use: bool = False
    ) -> TrainingRightsDecision:
        if asset.rights_mode is RightsMode.REFERENCE_ONLY:
            return TrainingRightsDecision(False, "REFERENCE_ONLY")
        if asset.rights_mode is RightsMode.OWNED_ORIGINAL:
            if not asset.source_uri.startswith("kronara://artifacts/"):
                return TrainingRightsDecision(False, "OWNERSHIP_PROVENANCE_MISSING")
            return TrainingRightsDecision(True, "OWNED_ORIGINAL", asset.source_uri)
        if not asset.permission_evidence_uri:
            return TrainingRightsDecision(False, "PERMISSION_EVIDENCE_MISSING")
        if not asset.allows_training:
            return TrainingRightsDecision(False, "TRAINING_SCOPE_MISSING")
        if commercial_use and not asset.allows_commercial:
            return TrainingRightsDecision(False, "COMMERCIAL_SCOPE_MISSING")
        return TrainingRightsDecision(
            True, "LICENSED_ADAPTATION", asset.permission_evidence_uri
        )
