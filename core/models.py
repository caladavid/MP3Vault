from dataclasses import dataclass, field
from typing import Optional


""" What the user chose for a download. Snapshotted on the main thread before a worker starts,
so the worker never reads Tk variables (not thread-safe) and a mid-download change in the UI
can't affect a running download. Also what core.settings persists. """
@dataclass(frozen=True)
class DownloadOptions:
    folder: str
    audio_format: str = "mp3"
    audio_quality: str = "192"


""" Outcome of downloading one video """
@dataclass
class TrackResult:
    status: str                         # "ok" | "cancelled" | "error"
    filename: Optional[str] = None
    error: Optional[str] = None
    tag_error: Optional[str] = None     # set when the file downloaded fine but tagging failed

    @property
    def ok(self):
        return self.status == "ok"

    @property
    def cancelled(self):
        return self.status == "cancelled"


""" Outcome of a playlist or queue download (many tracks) """
@dataclass
class BatchResult:
    attempted: int = 0                  # tracks actually sent to yt-dlp
    downloaded: int = 0
    skipped_existing: int = 0           # already in the folder, not downloaded again
    failed: int = 0
    cancelled: bool = False
    error: Optional[str] = None         # a failure that stopped the whole batch
    tag_errors: list = field(default_factory=list)


""" One progress update, already translated from yt-dlp's internal hook dict, so the UI never
depends on its key names or its formatted (and colorable) strings. """
@dataclass(frozen=True)
class Progress:
    status: str                         # "downloading" | "finished"
    fraction: float                     # 0.0 .. 1.0
    speed: str                          # e.g. "1.46MiB/s", "-" when unknown
    eta: str                            # e.g. "1:15", "N/A" when unknown
    title: str
    playlist_index: Optional[int] = None
    playlist_count: Optional[int] = None
