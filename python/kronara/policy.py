from __future__ import annotations

from kronara.contracts import (
    AuthorizationDecision,
    AutonomyMode,
    AutonomyPolicy,
    RiskDecision,
    RiskLevel,
)


NON_OVERRIDABLE = {
    "rights_insufficient",
    "credentials_invalid",
    "platform_policy_violation",
    "render_defective",
    "publication_ambiguous",
    "budget_exhausted",
    "critical_reputational_risk",
}


class AutonomyGuard:
    def __init__(self, policy: AutonomyPolicy):
        self.policy = policy

    def authorize(self, action: str, risk: RiskDecision) -> AuthorizationDecision:
        if self.policy.paused:
            return AuthorizationDecision(False, reason="globally_paused")
        blocked_code = next((code for code in risk.codes if code in NON_OVERRIDABLE), None)
        if blocked_code:
            return AuthorizationDecision(False, reason=blocked_code)
        if risk.level is RiskLevel.CRITICAL:
            return AuthorizationDecision(False, reason="critical_risk")
        if self.policy.mode is AutonomyMode.MANUAL and action in {
            "approve_concept",
            "approve_script",
            "approve_render",
            "publish",
        }:
            return AuthorizationDecision(False, requires_human=True, reason="manual_gate")
        if self.policy.mode is AutonomyMode.SUPERVISED_AUTO and action == "publish":
            return AuthorizationDecision(False, requires_human=True, reason="publication_gate")
        return AuthorizationDecision(True)

