"""Learns the real narration speech rate (words/second) from measured voice
synthesis, in place of the fixed "words / 2.5" guess that turned out to be
~43% off real edge-tts output (measured ~3.59 words/sec, not 2.5).

Every real (non-degraded) SceneDurationMeasurer.measure() call is a data
point that already cost nothing extra to obtain: `word_count` words really
took `seconds` seconds to speak. This module folds those observations into
a running average per voice_id, persisted across runs (SQLite, the same
"observe once, use forever" pattern as OpportunityStore/AssetLibraryStore),
so duration targeting keeps improving with real production instead of
guessing the same fixed number forever. Estimated/degraded measurements are
never recorded -- only genuine synthesized audio informs the average.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

# Cold-start prior: what the pipeline assumed before this module existed.
# Used only until real samples accumulate for a given voice.
DEFAULT_WORDS_PER_SECOND = 2.5


@dataclass(frozen=True)
class SpeechRateEstimate:
    words_per_second: float
    sample_count: int
    learned: bool


class SpeechRateLearner:
    """Persistent running average of real words-per-second, keyed by voice_id."""

    def __init__(self, db_path: "str | Path"):
        self._path = str(db_path)
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path)

    def initialize(self) -> "SpeechRateLearner":
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS speech_rate_totals (
                voice_id TEXT PRIMARY KEY,
                total_words INTEGER NOT NULL,
                total_seconds REAL NOT NULL,
                sample_count INTEGER NOT NULL
            )
            """
        )
        self._conn.commit()
        return self

    def record(self, voice_id: str, word_count: int, seconds: float) -> None:
        """Fold one real, measured (word_count, seconds) observation into
        the running average for this voice.

        Callers must only pass genuine synthesized measurements -- never an
        estimated/degraded duration, or the average would just re-learn the
        old guess instead of correcting it.
        """
        if word_count <= 0 or seconds <= 0:
            return
        self._conn.execute(
            """
            INSERT INTO speech_rate_totals (voice_id, total_words, total_seconds, sample_count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(voice_id) DO UPDATE SET
                total_words = total_words + excluded.total_words,
                total_seconds = total_seconds + excluded.total_seconds,
                sample_count = sample_count + 1
            """,
            (voice_id, word_count, seconds),
        )
        self._conn.commit()

    def estimate(self, voice_id: str) -> SpeechRateEstimate:
        row = self._conn.execute(
            "SELECT total_words, total_seconds, sample_count FROM speech_rate_totals WHERE voice_id = ?",
            (voice_id,),
        ).fetchone()
        if row is None or row[1] <= 0:
            return SpeechRateEstimate(DEFAULT_WORDS_PER_SECOND, 0, learned=False)
        total_words, total_seconds, sample_count = row
        return SpeechRateEstimate(total_words / total_seconds, sample_count, learned=True)

    def close(self) -> None:
        self._conn.close()
