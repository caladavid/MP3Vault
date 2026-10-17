import os
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yt_dlp


# NOTE: the "|" between these first two lines is required — without it Python's adjacent-string
# concatenation turns them into a single 2-char sequence pattern instead of an OR, and invalid
# filename chars like : ? " < > | stop being stripped from downloaded titles.
VALID_FILENAME_CHARS = re.compile(
    r'[^\w\s\-\'.()&,]'  # Caracteres no permitidos
    r'|[\\/:*?"<>|]' # Caracteres no válidos en nombres de archivo
    r'|\(Official Audio\)'  # Elimina "(Official Audio)"
    r'|\(\s-\sTopic\)'  # Elimina "( - Topic)"
    r'|\(official\)'  # Elimina "(official)" (case-sensitive)
    r'|\((?i:video)\)'  # Elimina "(video)" o "(Video)" (case-insensitive)
    r'|\((?i:audio)\)'  # Elimina "(audio)" o "(Audio)" (case-insensitive)
    r'|\((Remaster|Remastered)\)'  # Elimina "(Remaster)" o "(Remastered)"
    r'|\(\)',  # Elimina paréntesis vacíos "()"
)

INVALID_PATH_CHARS = r'[<>:"/\\|?*]'

# Accepts youtube.com/youtu.be with or without a www./m./music. subdomain, http or https,
# watch/shorts links for single videos, and playlist links.
YOUTUBE_VIDEO_URL_RE = re.compile(
    r'^https?://(?:www\.|m\.|music\.)?(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)(?P<id>[\w-]+)'
)
YOUTUBE_PLAYLIST_URL_RE = re.compile(
    r'^https?://(?:www\.|m\.|music\.)?youtube\.com/playlist\?list='
)

# Query parameters YouTube adds when a video is opened from a playlist/mix
PLAYLIST_QUERY_PARAMS = {"list", "index", "start_radio"}


""" A video URL opened from a playlist ("watch?v=X&list=Y", or the Share button's
"youtu.be/X?list=Y") means THIS video: strips the playlist parameters, whatever their order.
Needed because with extract_flat yt-dlp answers such a URL with a redirect to the playlist
(_type "url", no title for youtu.be links) instead of the video (verified). """
def video_only_url(url: str):
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in PLAYLIST_QUERY_PARAMS]
    return urlunsplit(parts._replace(query=urlencode(query)))


# Common channel-name suffixes that shouldn't end up in the artist/filename
UNWANTED_UPLOADER_SUFFIXES = [
    " - Topic",
    " - Official",
    " - YouTube",
    " - VEVO",
    " - Lyrics",
]


""" Clean a filename by removing special characters based on a regex pattern """
def clean_filename(filename: str):
    return re.sub(VALID_FILENAME_CHARS, "", filename).strip()


""" Strips common channel suffixes (" - Topic", " - VEVO"...) and then the same special characters
as clean_filename """
def clean_uploader(uploader: str):
    for suffix in UNWANTED_UPLOADER_SUFFIXES:
        if suffix in uploader:
            uploader = uploader.replace(suffix, "")

    return clean_filename(uploader)


""" Removes any number of leading "Uploader - " repetitions from a name """
def strip_uploader_prefix(uploader: str, name: str):
    pattern = rf"^(?:{re.escape(uploader)}\s*-\s*)+"
    return re.sub(pattern, "", name)


""" Single source of truth for the final filename a single-video download will produce —
used both to predict it BEFORE downloading (duplicate-file check) and to build it after the
download. Keeping this in one place means the prediction can never drift out of sync with the
real result. Returns (cleanTitle, finalFilename). """
def build_clean_title_and_filename(uploader: str, title: str, audio_format: str):
    cleanTitle = re.sub(INVALID_PATH_CHARS, '', clean_filename(title))

    # The uploader comes from YouTube metadata (channel/artist) or the Edit popup, so it must be
    # cleaned too: a raw "AC/DC" creates a subfolder, "..\" escapes the download folder, and ":"
    # on NTFS writes into an alternate data stream. Dedup against the CLEANED name so it matches
    # the cleaned title ("AC/DC - X" -> "ACDC - X", not "AC/DC - ACDC - X").
    cleanUploader = re.sub(INVALID_PATH_CHARS, '', clean_filename(uploader))

    remainder = strip_uploader_prefix(cleanUploader, cleanTitle)
    return cleanTitle, f"{cleanUploader} - {remainder}.{audio_format}"


""" Final filename of one PLAYLIST-mode track, built from the name yt-dlp wrote. Unlike the
single-video scheme this does NOT run the title through clean_filename, only dedupes a leading
uploader prefix on yt-dlp's own sanitized name, so the playlist prediction and the real rename
must both go through here or already-downloaded tracks stop being detected. """
def playlist_filename(uploader_clean: str, downloaded_base: str, audio_format: str):
    remainder = strip_uploader_prefix(uploader_clean, f"{downloaded_base}.{audio_format}")
    # basename: ensures there is no path info in the filename
    return os.path.basename(f"{uploader_clean} - {remainder}")


""" Predicts the filename a PLAYLIST-mode download will produce for one video, before downloading
(yt-dlp sanitizes the raw title the same way when it writes the file) """
def predict_playlist_filename(uploader_clean: str, raw_title: str, audio_format: str):
    baseFilename = yt_dlp.utils.sanitize_filename(raw_title, restricted=False)
    return playlist_filename(uploader_clean, baseFilename, audio_format)


""" Joins a filename onto the download folder and refuses any result that lands outside it —
last line of defense if a future naming change ever lets a path separator through again. """
def safe_join(folder: str, filename: str):
    base = os.path.realpath(folder)
    fullPath = os.path.realpath(os.path.join(base, filename))
    if os.path.dirname(fullPath) != base:
        raise ValueError(f"Unsafe filename rejected: {filename}")
    return fullPath
