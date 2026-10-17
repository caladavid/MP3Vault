import os

import pytest

from core import ffmpeg


def _install(folder, ffprobe=True):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ffmpeg.FFMPEG_EXE).write_text("")
    if ffprobe:
        (folder / ffmpeg.FFPROBE_EXE).write_text("")
    return str(folder)


def test_finds_first_absolute_path_entry(tmp_path):
    first, second = _install(tmp_path / "a"), _install(tmp_path / "b")
    assert ffmpeg.search_path(os.pathsep.join([str(tmp_path / "empty"), first, second])) == first


@pytest.mark.parametrize("entry", [".", "", "bin", "./tools", '""'])
def test_relative_entries_are_ignored(tmp_path, monkeypatch, entry):
    # A relative PATH entry resolves against the current folder: exactly where a planted
    # ffmpeg.exe would be. Even with one there, it must not be picked.
    _install(tmp_path / "bin")
    _install(tmp_path / "tools")
    _install(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert ffmpeg.search_path(entry) is None


def test_quoted_absolute_entry_is_accepted(tmp_path):
    folder = _install(tmp_path / "with space")
    assert ffmpeg.search_path(f'"{folder}"') == folder


def test_not_found(tmp_path):
    assert ffmpeg.search_path(str(tmp_path)) is None


def test_bundled_copy_wins_over_path(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    _install(bundle / "ffmpeg")
    monkeypatch.setattr(ffmpeg.sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setenv("PATH", _install(tmp_path / "onpath"))
    assert ffmpeg.find_ffmpeg() == str(bundle / "ffmpeg")


def test_bundle_without_ffmpeg_falls_back_to_path(tmp_path, monkeypatch):
    monkeypatch.setattr(ffmpeg.sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
    onPath = _install(tmp_path / "onpath")
    monkeypatch.setenv("PATH", onPath)
    assert ffmpeg.find_ffmpeg() == onPath


def test_missing_ffprobe_is_only_a_warning(tmp_path, monkeypatch, caplog):
    monkeypatch.delattr(ffmpeg.sys, "_MEIPASS", raising=False)
    folder = _install(tmp_path / "onpath", ffprobe=False)
    monkeypatch.setenv("PATH", folder)
    assert ffmpeg.find_ffmpeg() == folder
    assert "ffprobe not found" in caplog.text
