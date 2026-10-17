import threading

import pytest
import yt_dlp

from core import ytdl


def test_postprocessors_lossy_has_quality_and_thumbnail():
    pps = ytdl.build_audio_postprocessors("mp3", "320")
    assert pps[0] == {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'}
    assert [p['key'] for p in pps] == ['FFmpegExtractAudio', 'FFmpegMetadata', 'FFmpegThumbnailsConvertor', 'EmbedThumbnail']


def test_postprocessors_flac_has_no_quality():
    pps = ytdl.build_audio_postprocessors("flac", "320")
    assert 'preferredquality' not in pps[0]
    assert 'EmbedThumbnail' in [p['key'] for p in pps]


def test_postprocessors_wav_has_no_thumbnail():
    keys = [p['key'] for p in ytdl.build_audio_postprocessors("wav", "320")]
    assert keys == ['FFmpegExtractAudio', 'FFmpegMetadata']


def test_info_options_is_a_fresh_dict_each_call():
    a, b = ytdl.info_options(), ytdl.info_options()
    a['quiet'] = False
    assert b['quiet'] is True


def test_playlist_videos_keep_real_position():
    # Regression: a deleted video before a song used to shift every later checkbox by one
    entries = [{'title': 'A'}, {'title': '[Deleted video]'}, {'title': 'C'},
               {'title': None}, {'title': '[Private video]'}, {'title': ' E '}]
    assert ytdl.extract_playlist_videos(entries) == [
        {'title': 'A', 'playlistIndex': 1},
        {'title': 'C', 'playlistIndex': 3},
        {'title': 'E', 'playlistIndex': 6},
    ]


def test_playlist_videos_empty():
    assert ytdl.extract_playlist_videos(None) == []


def test_session_forwards_progress_and_records_stem():
    seen = []
    session = ytdl.DownloadSession(threading.Event(), on_progress=seen.append)
    d = {'status': 'downloading', 'filename': r'C:\dl\My Song.webm'}
    session.hook(d)
    assert seen == [d]
    assert session.stems == {'My Song'}


def test_session_cancel_records_stem_before_raising():
    # Regression: cancelling on the very first hook call left .part/.webp behind
    cancel = threading.Event()
    cancel.set()
    session = ytdl.DownloadSession(cancel)
    with pytest.raises(yt_dlp.utils.DownloadCancelled):
        session.hook({'status': 'downloading', 'filename': 'Song.webm'})
    assert session.stems == {'Song'}


def test_cancel_cleanup_only_removes_own_files(tmp_path):
    # Regression: cancel used to delete EVERY new file in the folder (e.g. browser downloads)
    (tmp_path / "already_there.mp3").write_text("")
    before = ytdl.list_folder(str(tmp_path))
    for name in ["Song.webm.part", "Song.webp", "Song.webm.ytdl", "browser_download.jpg"]:
        (tmp_path / name).write_text("")

    session = ytdl.DownloadSession(threading.Event())
    session.stems.add("Song")
    session.remove_cancelled_files(str(tmp_path), before)

    assert sorted(p.name for p in tmp_path.iterdir()) == ["already_there.mp3", "browser_download.jpg"]


def test_list_folder_missing(tmp_path):
    assert ytdl.list_folder(str(tmp_path / "nope")) == set()
