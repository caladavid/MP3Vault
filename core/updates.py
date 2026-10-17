import re
import subprocess
import sys

import requests
import yt_dlp


""" yt-dlp's own __version__ (e.g. "2026.07.04") and PyPI's info.version (e.g. "2026.7.4") are
the SAME release formatted differently — comparing them as strings says they differ forever,
even right after updating. Parse into an int tuple so equal versions compare equal. """
def parse_version_tuple(version_string: str):
    return tuple(int(part) for part in re.split(r'\D+', version_string) if part != '')


""" Returns the newer yt-dlp version string available on PyPI, or None if already up to date.
Network/format errors propagate; the caller decides whether to swallow them. """
def newer_ytdlp_version(timeout=5):
    response = requests.get("https://pypi.org/pypi/yt-dlp/json", timeout=timeout)
    latestVersion = response.json()["info"]["version"]
    if parse_version_tuple(latestVersion) > parse_version_tuple(yt_dlp.version.__version__):
        return latestVersion
    return None


""" True when running as a PyInstaller-packaged .exe, which has no pip to call """
def is_frozen():
    return getattr(sys, 'frozen', False)


""" Runs pip to upgrade yt-dlp in the current interpreter. Returns a user-facing message. """
def update_ytdlp(timeout=120):
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-U", "yt-dlp"],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0:
            return "yt-dlp updated. Restart MP3Vault for the change to take effect."
        return f"Update failed:\n{result.stderr[-500:]}"
    except Exception as e:
        return f"Update failed: {e}"
