from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Track:
    kind: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class MediaTimeline:
    width: int
    height: int
    duration_ms: int
    tracks: tuple[Track, ...]


class TimelineValidator:
    def validate_reel(self, timeline: MediaTimeline) -> bool:
        if timeline.height <= timeline.width:
            raise ValueError("reel requires a vertical canvas")
        if timeline.duration_ms <= 0:
            raise ValueError("duration must be positive")
        voice_tracks = [track for track in timeline.tracks if track.kind == "voice"]
        if not voice_tracks:
            raise ValueError("voice track is required")
        for track in timeline.tracks:
            if track.start_ms < 0 or track.end_ms > timeline.duration_ms:
                raise ValueError("track is outside timeline duration")
            if track.start_ms >= track.end_ms:
                raise ValueError("track duration must be positive")
        return True

