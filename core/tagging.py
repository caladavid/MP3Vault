import os

from mutagen.easyid3 import EasyID3
from mutagen.easymp4 import EasyMP4
from mutagen.flac import FLAC


""" Writes title/artist/album (and optionally track number) tags into an audio file.
Raises FileNotFoundError if the file is missing; any mutagen error propagates to the caller.

mutagen has no single tag class that covers every format — EasyID3 only understands ID3 (mp3),
EasyMP4 only MP4 atoms (m4a), FLAC only Vorbis comments. WAV has no well-supported standard
tagging scheme, so it's skipped rather than failing or writing something most players won't
read back. Returns False when the format was skipped, True when tags were written. """
def write_tags(file_path: str, title: str, artist: str, album: str, track_number=None):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found - {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".mp3":
        audioMetadata = EasyID3(file_path)
    elif ext == ".m4a":
        audioMetadata = EasyMP4(file_path)
    elif ext == ".flac":
        audioMetadata = FLAC(file_path)
    else:
        return False

    audioMetadata['title'] = title
    audioMetadata['artist'] = artist
    audioMetadata['albumartist'] = artist
    audioMetadata['album'] = str(album)
    if track_number is not None:
        audioMetadata['tracknumber'] = str(track_number)

    audioMetadata.save()
    return True
