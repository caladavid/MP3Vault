import json
import logging
import os
from dataclasses import asdict, dataclass

from core import ytdl


log = logging.getLogger(__name__)


""" Per-user folder for MP3Vault's own files (settings, logs): %APPDATA%\\MP3Vault on Windows,
~/.config/MP3Vault elsewhere. Never next to the .exe, which may live in a read-only folder. """
def app_data_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "MP3Vault")


def settings_path():
    return os.path.join(app_data_dir(), "settings.json")


""" What survives a restart. Defaults match the app's historical behavior (mp3, 192kbps). """
@dataclass
class Settings:
    last_folder: str = ""
    audio_format: str = "mp3"
    audio_quality: str = "192"


""" Reads settings, falling back to defaults per field: a missing/corrupt file, an unknown value
(hand-edited JSON, an option removed in a later version) or a folder that no longer exists must
never stop the app from opening. """
def load_settings(path=None):
    path = path or settings_path()
    defaults = Settings()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("settings root is not an object")
    except FileNotFoundError:
        return defaults
    except (OSError, ValueError) as e:
        log.warning("Ignoring unreadable settings file %s: %s", path, e)
        return defaults

    folder = data.get("last_folder")
    audioFormat = data.get("audio_format")
    quality = data.get("audio_quality")
    return Settings(
        last_folder=folder if isinstance(folder, str) and os.path.isdir(folder) else defaults.last_folder,
        audio_format=audioFormat if audioFormat in ytdl.AUDIO_FORMATS else defaults.audio_format,
        audio_quality=quality if quality in ytdl.AUDIO_QUALITIES else defaults.audio_quality,
    )


""" Writes settings atomically (temp file + os.replace), so a crash or full disk mid-write leaves
the previous file intact instead of a truncated one. Failures are logged, not raised: losing a
preference is not worth interrupting the user. """
def save_settings(settings: Settings, path=None):
    path = path or settings_path()
    tmpPath = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmpPath, "w", encoding="utf-8") as f:
            json.dump(asdict(settings), f, indent=2, ensure_ascii=False)
        os.replace(tmpPath, path)
    except OSError as e:
        log.warning("Could not save settings to %s: %s", path, e)
