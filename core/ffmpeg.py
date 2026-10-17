import logging
import os
import sys


log = logging.getLogger(__name__)

FFMPEG_EXE = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
FFPROBE_EXE = "ffprobe.exe" if os.name == "nt" else "ffprobe"


""" Folder holding an ffmpeg shipped INSIDE the PyInstaller bundle (<_MEIPASS>/ffmpeg/), if any.
That folder is created by the bundle's own bootloader, unlike the folder the .exe sits in. """
def bundled_dir():
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return None
    folder = os.path.join(base, "ffmpeg")
    return folder if os.path.isfile(os.path.join(folder, FFMPEG_EXE)) else None


""" First folder on PATH that contains ffmpeg, considering ABSOLUTE entries only: an empty, "."
or relative entry resolves against the current folder, which is exactly where a planted
ffmpeg.exe would sit. """
def search_path(path_env=None):
    path_env = os.environ.get("PATH", "") if path_env is None else path_env
    for entry in path_env.split(os.pathsep):
        entry = entry.strip().strip('"')
        if not entry or not os.path.isabs(entry):
            continue
        if os.path.isfile(os.path.join(entry, FFMPEG_EXE)):
            return entry
    return None


""" Absolute folder of the ffmpeg to use, or None. Passed to yt-dlp as ffmpeg_location so it
never runs a bare "ffmpeg": on Windows that name is looked up in the current folder and the
program's folder BEFORE PATH, so a planted ffmpeg.exe (e.g. in Downloads next to the .exe) would
run instead of the real one (verified with a harmless fake ffmpeg.exe). """
def find_ffmpeg():
    folder = bundled_dir() or search_path()
    if folder and not os.path.isfile(os.path.join(folder, FFPROBE_EXE)):
        log.warning("ffprobe not found next to %s; some conversions may fail", os.path.join(folder, FFMPEG_EXE))
    return folder
