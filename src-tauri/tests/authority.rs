use kronara_authority::{Authority, AuthorityError, Effect, RiskDecision};

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
