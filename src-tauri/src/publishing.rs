//! Governed publishing (`publication.publish`).
//!
//! Publishing uses a real Page credential, so Rust owns it. This module holds the
//! host-pinned URL construction and the reconciliation matcher (find an already
//! published Reel by its idempotency marker, so an ambiguous timeout never
//! double-posts). The live resumable upload connects to an **authorized Meta
//! Page**; until a Page token is configured, `publish` returns a structured
//! `not_configured` status and nothing is posted.

use serde_json::{json, Value};

/// The Reels publishing endpoint for a page.
pub fn video_reels_url(graph_version: &str, page_id: &str) -> String {
    format!("https://graph.facebook.com/{graph_version}/{page_id}/video_reels")
}

/// Embed marker so a published Reel can be matched back to its intent.
pub fn idempotency_marker(key: &str) -> String {
    format!("[kri:{key}]")
}

/// Reconciliation: given recent Reels (Graph `data` rows) and an idempotency key,
/// return the remote id whose description carries the marker.
pub fn reconcile_match(recent: &[Value], key: &str) -> Option<String> {
    let marker = idempotency_marker(key);
    for row in recent {
        let description = row
            .get("description")
            .and_then(Value::as_str)
            .unwrap_or("");
        if description.contains(&marker) {
            if let Some(id) = row.get("id").and_then(Value::as_str) {
                return Some(id.to_owned());
            }
        }
    }
    None
}

/// Dispatch entry for the `publication.publish` authority tool.
///
/// `page` is `Some((page_id, graph_version))` only when a Meta Page credential is
/// configured. The live upload is performed against that authorized Page; without
/// it, the call is a no-op that reports `not_configured` so the pipeline blocks
/// instead of pretending to publish.
pub fn publish(page: Option<(&str, &str)>, arguments: Value) -> Result<Value, String> {
    let key = arguments
        .get("idempotency_key")
        .and_then(Value::as_str)
        .ok_or_else(|| "idempotency_key is required".to_string())?;
    if key.trim().is_empty() {
        return Err("idempotency_key is required".to_string());
    }
    match page {
        None => Ok(json!({
            "status": "not_configured",
            "reason": "authorized_meta_page_required",
            "idempotency_key": key,
        })),
        Some((page_id, graph_version)) => {
            // The resumable upload runs here once a sandbox Page is authorized.
            // The endpoint and marker are constructed under host pinning; the
            // byte-upload + finish phases attach on integration with a live token.
            let _endpoint = video_reels_url(graph_version, page_id);
            Err("publication_upload_pending_authorized_page".to_string())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn builds_host_pinned_reels_url() {
        let url = video_reels_url("v25.0", "1234567890");
        assert_eq!(
            url,
            "https://graph.facebook.com/v25.0/1234567890/video_reels"
        );
        assert!(url.starts_with("https://graph.facebook.com/v"));
    }

    #[test]
    fn reconcile_matches_by_idempotency_marker() {
        let rows = vec![
            json!({"id": "fb_1", "description": "otra cosa"}),
            json!({"id": "fb_2", "description": "Historia [kri:idem-42] final"}),
        ];
        assert_eq!(reconcile_match(&rows, "idem-42"), Some("fb_2".to_string()));
        assert_eq!(reconcile_match(&rows, "idem-99"), None);
    }

    #[test]
    fn not_configured_when_no_page() {
        let result = publish(None, json!({"idempotency_key": "k1"})).unwrap();
        assert_eq!(result["status"], "not_configured");
    }

    #[test]
    fn requires_idempotency_key() {
        assert!(publish(None, json!({})).is_err());
    }
}
