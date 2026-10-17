import os
import threading
from unittest import mock

import pytest

from core import downloader, ytdl


""" Stands in for yt_dlp.YoutubeDL: writes the file yt-dlp would leave after conversion
("<video title>.<format>") and drives the progress hook, without any network access. """
class FakeYoutubeDL:
    def __init__(self, opts):
        self.opts = opts
        self.folder = os.path.dirname(opts['outtmpl'])
        self.ext = opts['postprocessors'][0]['preferredcodec']

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download):
        title = "Original Video Title"
        hook = self.opts['progress_hooks'][0]
        partial = os.path.join(self.folder, f"{title}.webm.part")
        open(partial, "w").close()
        hook({'status': 'downloading', 'filename': os.path.join(self.folder, f"{title}.webm")})  # may raise
        os.remove(partial)
        open(os.path.join(self.folder, f"{title}.{self.ext}"), "w").close()
        return {'title': title, 'ext': 'webm'}

    def prepare_filename(self, info):
        return os.path.join(self.folder, f"{info['title']}.{info['ext']}")


@pytest.fixture
def fake_ytdl():
    with mock.patch.object(downloader.yt_dlp, "YoutubeDL", FakeYoutubeDL), \
         mock.patch.object(downloader.tagging, "write_tags") as write_tags:
        yield write_tags


def _download(folder, cancel=False, title="Edited Title", uploader="AC/DC"):
    event = threading.Event()
    if cancel:
        event.set()
    return downloader.download_single(
        "https://youtu.be/x", title, uploader, "Album", str(folder), "mp3", "192",
        ytdl.DownloadSession(event),
    )


def test_download_renames_to_clean_name_and_tags(tmp_path, fake_ytdl):
    result = _download(tmp_path)

    assert result["success"] is True
    assert result["filename"] == "ACDC - Edited Title.mp3"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ACDC - Edited Title.mp3"]
    fake_ytdl.assert_called_once()
    assert fake_ytdl.call_args.args[1:] == ("Edited Title", "AC/DC", "Album")


def test_tag_failure_still_counts_as_downloaded(tmp_path, fake_ytdl):
    fake_ytdl.side_effect = RuntimeError("bad tags")
    result = _download(tmp_path)
    assert result["success"] is True
    assert result["tagError"] == "bad tags"


def test_cancel_removes_partial_but_keeps_other_files(tmp_path, fake_ytdl):
    (tmp_path / "user_file.jpg").write_text("")
    result = _download(tmp_path, cancel=True)

    assert result["cancelled"] is True
    assert result["success"] is False
    assert sorted(p.name for p in tmp_path.iterdir()) == ["user_file.jpg"]
    fake_ytdl.assert_not_called()


def test_redownload_overwrites_existing(tmp_path, fake_ytdl):
    (tmp_path / "ACDC - Edited Title.mp3").write_text("old")
    assert _download(tmp_path)["success"] is True
    assert (tmp_path / "ACDC - Edited Title.mp3").read_text() == ""
