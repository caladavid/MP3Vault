import os
import threading
from unittest import mock

import pytest
import yt_dlp

from core import downloader, ytdl
from core.models import DownloadOptions


PLAYLIST = ["Song A", "Song B", "Song C"]


""" Stands in for yt_dlp.YoutubeDL without any network access: for each video it writes a .part
and a .webp thumbnail, drives the progress hook, then leaves "<video title>.<format>" like a real
conversion would. In playlist mode it downloads only `playlist_items` and also writes the
playlist-level thumbnail. `fail_after` raises a DownloadError after that many videos. """
class FakeYoutubeDL:
    fail_after = None

    def __init__(self, opts):
        self.opts = opts
        self.pre_process = []
        self.folder = os.path.dirname(opts['outtmpl'])
        self.ext = opts['postprocessors'][0]['preferredcodec']

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    # The real _StemRecorder was verified against yt-dlp itself; here only its effect is
    # simulated (recording the name before the thumbnail/hook), to avoid faking yt-dlp internals.
    def add_post_processor(self, pp, when):
        assert when == 'pre_process'
        self.pre_process.append(pp)

    def _pre_process(self, title):
        for pp in self.pre_process:
            pp.session.stems.add(title)

    def _download_video(self, title, playlist_index=None):
        self._pre_process(title)
        hook = self.opts['progress_hooks'][0]
        partial = os.path.join(self.folder, f"{title}.webm.part")
        open(partial, "w").close()
        open(os.path.join(self.folder, f"{title}.webp"), "w").close()
        info = {'title': title, 'playlist_index': playlist_index, 'playlist_count': len(PLAYLIST)}
        hook({'status': 'downloading', 'filename': os.path.join(self.folder, f"{title}.webm"),
              'downloaded_bytes': 50, 'total_bytes': 100, 'speed': 2048, 'eta': 3, 'info_dict': info})  # may raise
        os.remove(partial)
        os.remove(os.path.join(self.folder, f"{title}.webp"))  # embedded by EmbedThumbnail
        open(os.path.join(self.folder, f"{title}.{self.ext}"), "w").close()
        return {'title': title, 'ext': 'webm', 'playlist_index': playlist_index}

    def extract_info(self, url, download):
        if 'playlist_items' not in self.opts:
            return self._download_video("Original Video Title")

        open(os.path.join(self.folder, "My Playlist.jpg"), "w").close()  # playlist-level thumbnail
        entries = []
        for n, index in enumerate(int(i) for i in self.opts['playlist_items'].split(",")):
            if self.fail_after is not None and n >= self.fail_after:
                # the next video gets as far as its thumbnail (no progress hook yet), then fails (e.g. HTTP 403)
                self._pre_process(PLAYLIST[index - 1])
                open(os.path.join(self.folder, f"{PLAYLIST[index - 1]}.webp"), "w").close()
                raise yt_dlp.utils.DownloadError("ERROR: HTTP Error 403: Forbidden")
            entries.append(self._download_video(PLAYLIST[index - 1], playlist_index=index))
        return {'title': 'My Playlist', 'entries': entries}

    def prepare_filename(self, info):
        return os.path.join(self.folder, f"{info['title']}.{info.get('ext', 'NA')}")


@pytest.fixture
def write_tags():
    FakeYoutubeDL.fail_after = None
    with mock.patch.object(downloader.yt_dlp, "YoutubeDL", FakeYoutubeDL), \
         mock.patch.object(downloader.tagging, "write_tags") as write_tags:
        yield write_tags


def _names(folder):
    return sorted(p.name for p in folder.iterdir())


def _session(cancel=False, progress=None):
    event = threading.Event()
    if cancel:
        event.set()
    return ytdl.DownloadSession(event, on_progress=progress.append if progress is not None else None)


def _download(folder, cancel=False, title="Edited Title", uploader="AC/DC", progress=None):
    session = _session(cancel, progress)
    session.title = title
    return downloader.download_single("https://youtu.be/x", title, uploader, "Album",
                                      DownloadOptions(str(folder)), session)


# --- single video

def test_download_renames_to_clean_name_and_tags(tmp_path, write_tags):
    result = _download(tmp_path)

    assert result.ok
    assert result.filename == "ACDC - Edited Title.mp3"
    assert _names(tmp_path) == ["ACDC - Edited Title.mp3"]
    assert write_tags.call_args.args[1:] == ("Edited Title", "AC/DC", "Album")


def test_progress_uses_edited_title(tmp_path, write_tags):
    progress = []
    _download(tmp_path, progress=progress)
    assert progress[0].title == "Edited Title"
    assert progress[0].fraction == 0.5


def test_tag_failure_still_counts_as_downloaded(tmp_path, write_tags):
    write_tags.side_effect = RuntimeError("bad tags")
    result = _download(tmp_path)
    assert result.ok
    assert result.tag_error == "bad tags"


def test_cancel_removes_partial_but_keeps_other_files(tmp_path, write_tags):
    (tmp_path / "user_file.jpg").write_text("")
    result = _download(tmp_path, cancel=True)

    assert result.cancelled
    assert _names(tmp_path) == ["user_file.jpg"]
    write_tags.assert_not_called()


def test_redownload_overwrites_existing(tmp_path, write_tags):
    (tmp_path / "ACDC - Edited Title.mp3").write_text("old")
    assert _download(tmp_path).ok
    assert (tmp_path / "ACDC - Edited Title.mp3").read_text() == ""


# --- playlist

def _playlist(folder, videos, cancel=False, progress=None):
    return downloader.download_playlist("https://youtube.com/playlist?list=PL", videos, "Band - Topic", "Album",
                                        DownloadOptions(str(folder)), _session(cancel, progress))


def test_playlist_downloads_selected_at_real_positions(tmp_path, write_tags):
    progress = []
    selected = [{'title': 'Song A', 'playlistIndex': 1}, {'title': 'Song C', 'playlistIndex': 3}]
    result = _playlist(tmp_path, selected, progress=progress)

    assert (result.attempted, result.downloaded, result.failed) == (2, 2, 0)
    # playlist thumbnail removed, uploader " - Topic" stripped, real track numbers tagged
    assert _names(tmp_path) == ["Band - Song A.mp3", "Band - Song C.mp3"]
    assert [c.kwargs['track_number'] for c in write_tags.call_args_list] == [1, 3]
    assert [(p.title, p.playlist_index, p.playlist_count) for p in progress] == [("Song A", 1, 3), ("Song C", 3, 3)]


def test_playlist_skips_existing(tmp_path, write_tags):
    (tmp_path / "Band - Song A.mp3").write_text("old")
    result = _playlist(tmp_path, [{'title': 'Song A', 'playlistIndex': 1}, {'title': 'Song B', 'playlistIndex': 2}])
    assert (result.skipped_existing, result.attempted, result.downloaded) == (1, 1, 1)
    assert (tmp_path / "Band - Song A.mp3").read_text() == "old"


def test_playlist_all_existing_attempts_nothing(tmp_path, write_tags):
    (tmp_path / "Band - Song A.mp3").write_text("")
    result = _playlist(tmp_path, [{'title': 'Song A', 'playlistIndex': 1}])
    assert (result.skipped_existing, result.attempted) == (1, 0)


def test_playlist_cancel_removes_this_runs_files_only(tmp_path, write_tags):
    (tmp_path / "user_file.jpg").write_text("")
    result = _playlist(tmp_path, [{'title': 'Song A', 'playlistIndex': 1}], cancel=True)
    assert result.cancelled
    assert _names(tmp_path) == ["My Playlist.jpg", "user_file.jpg"]


def test_playlist_error_keeps_finished_songs_and_removes_partials(tmp_path, write_tags):
    # Regression: an HTTP 403 halfway through used to leave .webp leftovers behind
    FakeYoutubeDL.fail_after = 1
    (tmp_path / "user_file.jpg").write_text("")
    progress = []
    result = _playlist(tmp_path, [{'title': 'Song A', 'playlistIndex': 1}, {'title': 'Song B', 'playlistIndex': 2}],
                       progress=progress)

    assert "403" in result.error
    # finished-but-unrenamed Song A is kept; Song B's half-written thumbnail is gone
    assert "Song A.mp3" in _names(tmp_path)
    assert "Song B.webp" not in _names(tmp_path)
    assert "user_file.jpg" in _names(tmp_path)


# --- queue

def _queue(folder, infos, cancel=False):
    event = threading.Event()
    if cancel:
        event.set()
    items = []
    with mock.patch.object(downloader, "fetch_info", side_effect=lambda url: infos[url]):
        result = downloader.download_queue(list(infos), DownloadOptions(str(folder)),
                                           lambda: ytdl.DownloadSession(event),
                                           on_item=lambda i, total: items.append((i, total)))
    return result, items


def test_queue_downloads_each_and_reports_items(tmp_path, write_tags):
    infos = {"u1": {'title': 'One', 'channel': 'Chan'}, "u2": {'title': 'Two', 'channel': 'Chan', 'artist': 'Art'}}
    result, items = _queue(tmp_path, infos)
    assert (result.attempted, result.downloaded, result.failed) == (2, 2, 0)
    assert items == [(1, 2), (2, 2)]
    # artist falls back to channel
    assert [c.args[2] for c in write_tags.call_args_list] == ["Chan", "Art"]


def test_queue_counts_failed_lookups(tmp_path, write_tags):
    infos = {"u1": {'title': 'One', 'channel': 'Chan'}}
    with mock.patch.object(downloader, "fetch_info", side_effect=RuntimeError("offline")):
        result = downloader.download_queue(list(infos), DownloadOptions(str(tmp_path)),
                                           lambda: ytdl.DownloadSession(threading.Event()))
    assert (result.failed, result.attempted) == (1, 0)


def test_queue_skips_existing(tmp_path, write_tags):
    (tmp_path / "Chan - One.mp3").write_text("")
    result, _ = _queue(tmp_path, {"u1": {'title': 'One', 'channel': 'Chan'}})
    assert (result.skipped_existing, result.attempted) == (1, 0)


def test_queue_cancel_before_start_downloads_nothing(tmp_path, write_tags):
    result, items = _queue(tmp_path, {"u1": {'title': 'One', 'channel': 'Chan'}}, cancel=True)
    assert result.cancelled
    assert items == []
    assert _names(tmp_path) == []


def test_queue_strips_playlist_from_video_links(tmp_path, write_tags):
    seen = []
    def fake_fetch(url):
        seen.append(url)
        return {'title': 'One', 'channel': 'Chan'}
    with mock.patch.object(downloader, "fetch_info", side_effect=fake_fetch):
        result = downloader.download_queue(["https://youtu.be/jNQXAC9IVRw?list=PL123"], DownloadOptions(str(tmp_path)),
                                           lambda: ytdl.DownloadSession(threading.Event()))
    assert seen == ["https://youtu.be/jNQXAC9IVRw"]
    assert result.downloaded == 1
