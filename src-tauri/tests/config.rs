use std::collections::BTreeMap;

use kronara_authority::config::{AppConfig, ProviderState, RedditState};

#[test]
fn missing_optional_provider_keys_disable_provider_without_failing_app() {
    let values = BTreeMap::from([
        ("KRONARA_ENV".into(), "development".into()),
        ("KRONARA_DATA_DIR".into(), ".kronara".into()),
    ]);

    let config = AppConfig::from_values(&values).expect("base config should load");
    let qwen = config
        .provider_status()
        .into_iter()
        .find(|provider| provider.provider == "qwen")
        .expect("qwen status");

    assert_eq!(qwen.state, ProviderState::DisabledMissingCredential);
}

#[test]
fn debug_output_never_contains_provider_secrets() {
    let values = BTreeMap::from([
        ("KRONARA_ENV".into(), "development".into()),
        ("KRONARA_DATA_DIR".into(), ".kronara".into()),
        ("KRONARA_QWEN_API_KEY".into(), "super-secret-key".into()),
        ("KRONARA_QWEN_MODEL".into(), "qwen-planner".into()),
    ]);

    let config = AppConfig::from_values(&values).expect("config should load");
    let debug = format!("{config:?}");

    assert!(!debug.contains("super-secret-key"));
    assert!(debug.contains("[REDACTED]"));
}

#[test]
fn invalid_budget_is_rejected_at_configuration_boundary() {
    let values = BTreeMap::from([
        ("KRONARA_ENV".into(), "development".into()),
        ("KRONARA_DATA_DIR".into(), ".kronara".into()),
        ("KRONARA_MAX_RESEARCH_COST_USD".into(), "-1".into()),
    ]);

    let error = AppConfig::from_values(&values).expect_err("negative budget must fail");

    assert_eq!(error.variable(), "KRONARA_MAX_RESEARCH_COST_USD");
}

#[test]
fn reddit_enabled_requires_credentials_and_contract_reference() {
    let values = BTreeMap::from([
        ("KRONARA_REDDIT_ENABLED".into(), "true".into()),
        ("KRONARA_REDDIT_CLIENT_ID".into(), "client".into()),
        ("KRONARA_REDDIT_CLIENT_SECRET".into(), "secret".into()),
        ("KRONARA_REDDIT_USER_AGENT".into(), "kronara/0.4".into()),
    ]);

    let error = AppConfig::from_values(&values).expect_err("contract reference is mandatory");

    assert_eq!(error.variable(), "KRONARA_REDDIT_CONTRACT_REFERENCE");
}

#[test]
fn reddit_ready_state_keeps_credentials_redacted() {
    let values = BTreeMap::from([
        ("KRONARA_REDDIT_ENABLED".into(), "true".into()),
        ("KRONARA_REDDIT_CLIENT_ID".into(), "client".into()),
        (
            "KRONARA_REDDIT_CLIENT_SECRET".into(),
            "reddit-super-secret".into(),
        ),
        ("KRONARA_REDDIT_USER_AGENT".into(), "kronara/0.4".into()),
        (
            "KRONARA_REDDIT_CONTRACT_REFERENCE".into(),
            "reddit-contract-1".into(),
        ),
    ]);

    let config = AppConfig::from_values(&values).expect("Reddit config should load");

    assert_eq!(config.reddit_status(), RedditState::Ready);
    assert!(!format!("{config:?}").contains("reddit-super-secret"));
}
