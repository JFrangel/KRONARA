//! Governed neural-voice synthesis (`voice.synthesize`).
//!
//! Rust owns the effect: it validates the voice against an allowlist, builds the
//! edge-tts arguments itself (no shell interpolation), runs the bundled/available
//! `edge-tts` binary under its control, and parses the returned subtitle track to
//! report the **real** audio duration plus per-word timings. Python only asks for
//! this; it never opens the network path itself.
//!
//! When the `edge-tts` binary is not present the call returns a structured error
//! and the Python measurer degrades explicitly to the words-per-minute estimate.

use serde::Deserialize;
use serde_json::{json, Value};
use std::process::Command;

/// Spanish neural voices Kronara is allowed to request. No arbitrary voice ids.
const ALLOWED_VOICES: &[&str] = &[
    "es-BO-MarceloNeural",
    "es-CL-LorenzoNeural",
    "es-BO-SofiaNeural",
    "es-CO-GonzaloNeural",
    "es-CO-SalomeNeural",
];

#[derive(Debug, Deserialize)]
pub struct VoiceRequest {
    pub text: String,
    pub voice_id: String,
    #[serde(default)]
    pub rate: f64,
    #[serde(default)]
    pub pitch: f64,
}

/// Format a fractional rate (e.g. -0.04) as the edge-tts percent string ("-4%").
pub fn format_rate(value: f64) -> String {
    let pct = (value * 100.0).round() as i64;
    format!("{}{}%", if pct >= 0 { "+" } else { "" }, pct)
}

/// Format a fractional pitch as the edge-tts Hz string ("+0Hz").
pub fn format_pitch(value: f64) -> String {
    let hz = (value * 100.0).round() as i64;
    format!("{}{}Hz", if hz >= 0 { "+" } else { "" }, hz)
}

/// Parse a WebVTT/SRT timestamp (HH:MM:SS.mmm or HH:MM:SS,mmm) to milliseconds.
pub fn parse_timestamp(token: &str) -> Option<u64> {
    let cleaned = token.trim().replace(',', ".");
    let (hms, millis) = match cleaned.split_once('.') {
        Some((left, right)) => (left, right),
        None => (cleaned.as_str(), "0"),
    };
    let parts: Vec<&str> = hms.split(':').collect();
    let (h, m, s) = match parts.as_slice() {
        [h, m, s] => (h.parse::<u64>().ok()?, m.parse::<u64>().ok()?, s.parse::<u64>().ok()?),
        [m, s] => (0, m.parse::<u64>().ok()?, s.parse::<u64>().ok()?),
        _ => return None,
    };
    let ms: u64 = format!("{:0<3}", &millis[..millis.len().min(3)])
        .parse()
        .ok()?;
    Some(((h * 3600 + m * 60 + s) * 1000) + ms)
}

/// Parse edge-tts subtitle output into (word_boundaries, total_duration_ms).
///
/// Accepts the WebVTT and SRT cue shapes edge-tts emits: a `start --> end` line
/// followed by the spoken word on the next line.
pub fn parse_cues(content: &str) -> (Vec<Value>, u64) {
    let mut boundaries = Vec::new();
    let mut duration_ms = 0_u64;
    let lines: Vec<&str> = content.lines().collect();
    let mut index = 0;
    while index < lines.len() {
        let line = lines[index].trim();
        if let Some((start_token, end_token)) = line.split_once("-->") {
            if let (Some(start), Some(end)) =
                (parse_timestamp(start_token), parse_timestamp(end_token))
            {
                let word = lines.get(index + 1).map(|value| value.trim()).unwrap_or("");
                if !word.is_empty() {
                    boundaries.push(json!({
                        "word": word,
                        "offset_ms": start,
                        "duration_ms": end.saturating_sub(start),
                    }));
                }
                duration_ms = duration_ms.max(end);
                index += 2;
                continue;
            }
        }
        index += 1;
    }
    (boundaries, duration_ms)
}

/// Validate the request and (if `edge-tts` is available) synthesize, returning
/// `{voice_id, duration_ms, word_boundaries, audio_ref}`.
pub fn synthesize(arguments: Value) -> Result<Value, String> {
    let request: VoiceRequest = serde_json::from_value(arguments)
        .map_err(|_| "invalid voice request".to_string())?;
    if request.text.trim().is_empty() {
        return Err("voice_empty_text".to_string());
    }
    if !ALLOWED_VOICES.contains(&request.voice_id.as_str()) {
        return Err("voice_not_allowed".to_string());
    }

    let stamp = {
        // A content-derived name keeps temp files distinct without a clock.
        let mut hash = 0xcbf29ce484222325_u64;
        for byte in format!("{}|{}", request.voice_id, request.text).bytes() {
            hash ^= byte as u64;
            hash = hash.wrapping_mul(0x100000001b3);
        }
        format!("{hash:016x}")
    };
    let dir = std::env::temp_dir().join("kronara-voice");
    if std::fs::create_dir_all(&dir).is_err() {
        return Err("voice_tempdir_failed".to_string());
    }
    let media = dir.join(format!("{stamp}.mp3"));
    let subs = dir.join(format!("{stamp}.vtt"));

    let output = Command::new("edge-tts")
        .arg("--voice")
        .arg(&request.voice_id)
        .arg("--text")
        .arg(&request.text)
        .arg("--rate")
        .arg(format_rate(request.rate))
        .arg("--pitch")
        .arg(format_pitch(request.pitch))
        .arg("--write-media")
        .arg(&media)
        .arg("--write-subtitles")
        .arg(&subs)
        .output();

    let output = match output {
        Ok(value) => value,
        // Binary missing / not on PATH -> let Python degrade to the estimate.
        Err(_) => return Err("voice_synthesis_unavailable".to_string()),
    };
    if !output.status.success() {
        return Err("voice_synthesis_failed".to_string());
    }
    let subtitle_text = std::fs::read_to_string(&subs).unwrap_or_default();
    let (boundaries, duration_ms) = parse_cues(&subtitle_text);
    Ok(json!({
        "schema_version": 1,
        "voice_id": request.voice_id,
        "duration_ms": duration_ms,
        "word_boundaries": boundaries,
        "audio_ref": media.to_string_lossy(),
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn formats_rate_and_pitch() {
        assert_eq!(format_rate(-0.04), "-4%");
        assert_eq!(format_rate(0.0), "+0%");
        assert_eq!(format_rate(0.1), "+10%");
        assert_eq!(format_pitch(0.0), "+0Hz");
        assert_eq!(format_pitch(-0.02), "-2Hz");
    }

    #[test]
    fn parses_timestamps() {
        assert_eq!(parse_timestamp("00:00:01.500"), Some(1500));
        assert_eq!(parse_timestamp("00:01:02,250"), Some(62250));
        assert_eq!(parse_timestamp("nope"), None);
    }

    #[test]
    fn parses_vtt_cues_into_boundaries_and_duration() {
        let vtt = "WEBVTT\n\n00:00:00.000 --> 00:00:00.400\nMara\n\n00:00:00.400 --> 00:00:01.000\nescucha\n";
        let (boundaries, duration) = parse_cues(vtt);
        assert_eq!(boundaries.len(), 2);
        assert_eq!(duration, 1000);
        assert_eq!(boundaries[0]["word"], "Mara");
        assert_eq!(boundaries[1]["offset_ms"], 400);
    }

    #[test]
    fn rejects_unknown_voice() {
        let err = synthesize(json!({"text": "hola", "voice_id": "en-US-Guy"})).unwrap_err();
        assert_eq!(err, "voice_not_allowed");
    }

    #[test]
    fn rejects_empty_text() {
        let err = synthesize(json!({"text": "  ", "voice_id": "es-BO-SofiaNeural"})).unwrap_err();
        assert_eq!(err, "voice_empty_text");
    }
}
