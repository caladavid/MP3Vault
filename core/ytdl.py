import logging
import os

import yt_dlp
from yt_dlp.postprocessor import PostProcessor

from core.models import Progress


# yt-dlp sends its own warnings/errors here (e.g. "HTTP Error 403") instead of only printing
# them; its per-line progress output arrives as debug and is filtered out at INFO level.
YTDLP_LOGGER = logging.getLogger("yt_dlp")

# Plain-text output: otherwise yt-dlp wraps errors in ANSI color codes ("[0;31mERROR:"),
# which end up both in the log and in the error text shown to the user (verified). Note the
# old 'nocolor' key is not a yt-dlp option at all and was silently ignored.
NO_COLOR = {'stdout': 'no_color', 'stderr': 'no_color'}


# Player clients that still serve audio without a PO token; the default client answers
# HTTP 403 on the actual media download (verified).
EXTRACTOR_ARGS = {'youtube': {'player_client': ['web_embedded', 'tv', 'android']}}

LOSSLESS_FORMATS = ('flac', 'wav')
AUDIO_FORMATS = ["mp3", "m4a", "flac", "wav"]
AUDIO_QUALITIES = ["128", "192", "320"]

# Titles YouTube uses for playlist entries that can no longer be downloaded
UNAVAILABLE_TITLES = ("[Deleted video]", "[Private video]", "")


""" yt-dlp options for a metadata-only (no download) lookup. Returns a fresh dict on every call:
lookups run on several threads at once, and a shared dict would race between them. """
def info_options():
    return {
        'quiet': True,
        'extract_flat': True,
        'socket_timeout': 10,
        'extractor_args': EXTRACTOR_ARGS,
        'logger': YTDLP_LOGGER,
        'color': NO_COLOR,
    }


""" Builds the yt_dlp postprocessors list for the given format/quality """
def build_audio_postprocessors(audio_format: str, audio_quality: str):
    postprocessors = [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': audio_format,
    }]
    # Bitrate is meaningless for lossless/uncompressed formats — omitting preferredquality
    # there lets FFmpegExtractAudio use its own lossless default instead of misapplying a kbps
    # target to flac/wav.
    if audio_format not in LOSSLESS_FORMATS:
        postprocessors[0]['preferredquality'] = audio_quality

    postprocessors.append({'key': 'FFmpegMetadata'})  # Añade metadatos

    # WAV has no standard place to embed cover art, so skip the thumbnail steps entirely for it
    if audio_format != 'wav':
        postprocessors.append({'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'})
        postprocessors.append({'key': 'EmbedThumbnail'})

    return postprocessors


""" Names currently in a folder (empty set if it doesn't exist) """
def list_folder(folder: str):
    return set(os.listdir(folder)) if os.path.isdir(folder) else set()


""" Turns a flat-extracted playlist's entries into the list of downloadable videos.
The position is counted over ALL entries, including the skipped ones: yt_dlp's playlist_items
refers to the real playlist position, so storing it per video keeps a selection pointing at the
right song even when a deleted video sits before it (flat-extracted entries carry no
playlist_index of their own, verified). """
def extract_playlist_videos(entries):
    videos = []
    for position, video in enumerate(entries or [], start=1):
        title = (video.get('title') or '').strip()
        if title not in UNAVAILABLE_TITLES:
            videos.append({'title': title, 'playlistIndex': position})
    return videos


# Extensions of the temporary/intermediate files yt-dlp writes next to the final audio
LEFTOVER_EXTENSIONS = ('.part', '.ytdl', '.webp', '.jpg', '.jpeg', '.png')


""" Translates yt-dlp's raw progress-hook dict into a Progress. Uses the numeric fields rather
than yt-dlp's preformatted "_percent_str"/"_speed_str" strings, whose format (and ANSI colors)
belong to yt-dlp's console output. `title` overrides the video's own title when given. """
def progress_from_hook(d, title=None):
    info = d.get('info_dict') or {}
    total = d.get('total_bytes') or d.get('total_bytes_estimate')
    if d.get('status') == 'finished':
        fraction = 1.0
    elif total:
        fraction = min(max(d.get('downloaded_bytes', 0) / total, 0.0), 1.0)
    else:
        fraction = 0.0

    speed = d.get('speed')
    eta = d.get('eta')
    return Progress(
        status=d.get('status', ''),
        fraction=fraction,
        speed=f"{yt_dlp.utils.format_bytes(speed)}/s" if speed else "-",
        eta=yt_dlp.utils.formatSeconds(eta) if eta is not None else "N/A",
        title=title or info.get('title') or '',
        # playlist_index lives in info_dict, not at the top level of the hook dict (verified)
        playlist_index=info.get('playlist_index'),
        playlist_count=info.get('playlist_count') or info.get('n_entries'),
    )


""" Records each video's base name as soon as yt-dlp starts processing it. Registered as a
'pre_process' postprocessor, it runs BEFORE the thumbnail is written and before the first
progress hook, so a failure right at the start of a video (e.g. HTTP 403) still leaves a known
name to clean up (verified: the progress hook alone missed the .webp in that case). """
class _StemRecorder(PostProcessor):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def run(self, info):
        filename = self._downloader.prepare_filename(info)
        self.session.stems.add(os.path.splitext(os.path.basename(filename))[0])
        return [], info


""" State of one download run: the cancel flag the UI sets, plus the base names yt-dlp reported
writing, so a cleanup only deletes this run's files. Its hook() goes in progress_hooks; the UI's
on_progress callback receives Progress objects. `title` (optional) is shown instead of the
video's own title, e.g. the name the user typed in the Edit popup. """
class DownloadSession:
    def __init__(self, cancel_event, on_progress=None, title=None):
        self.cancel_event = cancel_event
        self.on_progress = on_progress
        self.title = title
        self.stems = set()

    """ Call right after creating the YoutubeDL instance, so names get recorded early """
    def attach(self, ydl):
        ydl.add_post_processor(_StemRecorder(self), when='pre_process')

    def hook(self, d):
        # Runs on the download worker thread. Remember the base name yt-dlp is writing ("Title"
        # for Title.webm/.part/.ytdl/.webp), so a cleanup never touches unrelated files that
        # happened to land in the same folder (e.g. a browser download into ~/Downloads).
        # Recorded BEFORE the cancel check: a cancel raised on the very first hook call would
        # otherwise leave its .part/.webp behind (verified).
        if d.get('filename'):
            self.stems.add(os.path.splitext(os.path.basename(d['filename']))[0])

        # Raising here is yt_dlp's documented way to abort a download cleanly from inside a hook
        if self.cancel_event.is_set():
            raise yt_dlp.utils.DownloadCancelled("Cancelled by user")

        if self.on_progress:
            self.on_progress(progress_from_hook(d, self.title))

    """ Best-effort removal of the files this run left behind: only files that are new since the
    snapshot AND belong to a name the hook saw being written. One failed removal shouldn't stop
    the rest.
    partial_only=False (cancel): everything this run wrote goes, finished tracks included.
    partial_only=True (error): only temp files/thumbnails go, so songs that did finish before
    the error (e.g. an HTTP 403 halfway through a playlist) are kept. """
    def remove_leftovers(self, folder: str, files_before: set, partial_only=False):
        for newFile in list_folder(folder) - files_before:
            if not any(newFile.startswith(stem) for stem in self.stems):
                continue
            if partial_only and not newFile.lower().endswith(LEFTOVER_EXTENSIONS):
                continue
            try:
                os.remove(os.path.join(folder, newFile))
            except OSError:
                pass
