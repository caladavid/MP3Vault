import os
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
    session.hook({'status': 'downloading', 'filename': r'C:\dl\My Song.webm', 'info_dict': {'title': 'My Song'}})
    assert [p.title for p in seen] == ['My Song']
    assert session.stems == {'My Song'}


def test_progress_from_hook_uses_numbers_not_console_strings():
    d = {'status': 'downloading', 'downloaded_bytes': 25, 'total_bytes': 100, 'speed': 1536000, 'eta': 75,
         '_percent_str': '[0;94m 99.9%[0m',  # must be ignored
         'info_dict': {'title': 'T', 'playlist_index': 2, 'n_entries': 9}}
    p = ytdl.progress_from_hook(d)
    assert (p.fraction, p.speed, p.eta, p.title, p.playlist_index, p.playlist_count) == (0.25, "1.46MiB/s", "1:15", "T", 2, 9)


def test_progress_from_hook_unknown_sizes():
    p = ytdl.progress_from_hook({'status': 'downloading', 'total_bytes_estimate': 0})
    assert (p.fraction, p.speed, p.eta, p.title, p.playlist_index) == (0.0, "-", "N/A", "", None)


def test_progress_finished_is_full_and_title_override():
    p = ytdl.progress_from_hook({'status': 'finished', 'info_dict': {'title': 'Original'}}, title="Edited")
    assert (p.fraction, p.title) == (1.0, "Edited")


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
    session.remove_leftovers(str(tmp_path), before)

    assert sorted(p.name for p in tmp_path.iterdir()) == ["already_there.mp3", "browser_download.jpg"]


def test_list_folder_missing(tmp_path):
    assert ytdl.list_folder(str(tmp_path / "nope")) == set()


def test_error_cleanup_keeps_finished_audio(tmp_path):
    before = ytdl.list_folder(str(tmp_path))
    for name in ["Song.mp3", "Song.webp", "Song.webm.part", "Other.jpg"]:
        (tmp_path / name).write_text("")
    session = ytdl.DownloadSession(threading.Event())
    session.stems.add("Song")
    session.remove_leftovers(str(tmp_path), before, partial_only=True)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["Other.jpg", "Song.mp3"]


def test_attach_records_name_before_any_progress_hook(tmp_path):
    # Real yt-dlp objects, no network: the pre_process recorder must use yt-dlp's own filename
    session = ytdl.DownloadSession(threading.Event())
    with yt_dlp.YoutubeDL({'quiet': True, 'outtmpl': f'{tmp_path}/%(title)s.%(ext)s'}) as ydl:
        session.attach(ydl)
        recorder = ydl._pps['pre_process'][-1]
        recorder.run({'id': 'x', 'title': 'A: B?', 'ext': 'webm'})
    assert session.stems == {os.path.splitext(os.path.basename(ydl.prepare_filename({'id': 'x', 'title': 'A: B?', 'ext': 'webm'})))[0]}
    assert session.stems != {'A: B?'}  # sanitized like the real file, not the raw title
