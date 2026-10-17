import shutil
import subprocess

import pytest
from mutagen import File

from core import tagging


pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _make_audio(path):
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "0.2", str(path)],
        check=True,
    )


@pytest.mark.parametrize("ext", ["mp3", "m4a", "flac"])
def test_tags_written(tmp_path, ext):
    path = tmp_path / f"song.{ext}"
    _make_audio(path)

    assert tagging.write_tags(str(path), "Title", "Artist", "Album", track_number=3) is True

    tags = File(str(path), easy=True)
    assert tags["title"] == ["Title"]
    assert tags["artist"] == ["Artist"]
    assert tags["albumartist"] == ["Artist"]
    assert tags["album"] == ["Album"]
    assert tags["tracknumber"][0].split("/")[0] == "3"


def test_wav_is_skipped(tmp_path):
    path = tmp_path / "song.wav"
    _make_audio(path)
    assert tagging.write_tags(str(path), "T", "A", "B") is False


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        tagging.write_tags(str(tmp_path / "nope.mp3"), "T", "A", "B")
