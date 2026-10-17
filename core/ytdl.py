import os

import yt_dlp


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


""" State of one download run: the cancel flag the UI sets, plus the base names yt-dlp reported
writing, so a cancel cleanup only deletes this run's files. Its hook() goes in progress_hooks. """
class DownloadSession:
    def __init__(self, cancel_event, on_progress=None):
        self.cancel_event = cancel_event
        self.on_progress = on_progress
        self.stems = set()

    def hook(self, d):
        # Runs on the download worker thread. Remember the base name yt-dlp is writing ("Title"
        # for Title.webm/.part/.ytdl/.webp), so a cancel cleanup never touches unrelated files that
        # happened to land in the same folder (e.g. a browser download into ~/Downloads).
        # Recorded BEFORE the cancel check: a cancel raised on the very first hook call would
        # otherwise leave its .part/.webp behind (verified).
        if d.get('filename'):
            self.stems.add(os.path.splitext(os.path.basename(d['filename']))[0])

        # Raising here is yt_dlp's documented way to abort a download cleanly from inside a hook
        if self.cancel_event.is_set():
            raise yt_dlp.utils.DownloadCancelled("Cancelled by user")

        if self.on_progress:
            self.on_progress(d)

    """ Best-effort removal of the partial/temp files a cancelled download left behind: only files
    that are new since the snapshot AND belong to a name the hook saw being written. One failed
    removal shouldn't stop the rest. """
    def remove_cancelled_files(self, folder: str, files_before: set):
        for newFile in list_folder(folder) - files_before:
            if any(newFile.startswith(stem) for stem in self.stems):
                try:
                    os.remove(os.path.join(folder, newFile))
                except OSError:
                    pass
