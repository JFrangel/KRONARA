use kronara_authority::{
    ActionIntent, Authority, AuthorityError, Effect, IntentDecision, RiskDecision,
};
use serde_json::json;

#[test]
fn globally_paused_authority_denies_effects() {
    let authority = Authority::new(true, "full_auto");
    let decision = authority.authorize(Effect::Publish, RiskDecision::low());

    assert_eq!(decision, Err(AuthorityError::GloballyPaused));
}

#[test]
fn critical_rights_failure_cannot_be_overridden_in_full_auto() {
    let authority = Authority::new(false, "full_auto");
    let risk = RiskDecision::critical("rights_insufficient");

    assert_eq!(
        authority.authorize(Effect::Publish, risk),
        Err(AuthorityError::Blocked("rights_insufficient".into()))
    );
}

#[test]
fn administrative_action_intent_always_requires_explicit_approval() {
    let authority = Authority::new(false, "full_auto");
    let intent = ActionIntent {
        schema_version: 1,
        intent_id: "intent_1".into(),
        kind: "set_budget".into(),
        arguments: json!({"requested_maximum_usd": 100.0}),
        risk_level: "administrative".into(),
        status: "requires_approval".into(),
        idempotency_key: "operations:1".into(),
    };

    assert_eq!(
        authority.validate_action_intent(&intent),
        IntentDecision::RequiresApproval
    );
}

#[test]
fn action_intent_cannot_carry_secrets_or_claim_prior_authorization() {
    let authority = Authority::new(false, "full_auto");
    let intent = ActionIntent {
        schema_version: 1,
        intent_id: "intent_2".into(),
        kind: "set_budget".into(),
        arguments: json!({"token": "must-not-pass"}),
        risk_level: "administrative".into(),
        status: "authorized".into(),
        idempotency_key: "operations:2".into(),
    };

    assert_eq!(
        authority.validate_action_intent(&intent),
        IntentDecision::Denied("invalid_action_intent".into())
    );
}
