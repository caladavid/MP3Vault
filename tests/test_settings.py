import json

from core import settings


def test_missing_file_gives_defaults(tmp_path):
    assert settings.load_settings(str(tmp_path / "settings.json")) == settings.Settings()


def test_round_trip(tmp_path):
    path = str(tmp_path / "sub" / "settings.json")  # parent folder created on save
    saved = settings.Settings(last_folder=str(tmp_path), audio_format="flac", audio_quality="320")
    settings.save_settings(saved, path)
    assert settings.load_settings(path) == saved


def test_unicode_folder_round_trip(tmp_path):
    folder = tmp_path / "Música Ñandú"
    folder.mkdir()
    path = str(tmp_path / "settings.json")
    settings.save_settings(settings.Settings(last_folder=str(folder)), path)
    assert settings.load_settings(path).last_folder == str(folder)


def test_corrupt_file_gives_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    assert settings.load_settings(str(path)) == settings.Settings()


def test_non_object_json_gives_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("[1, 2]", encoding="utf-8")
    assert settings.load_settings(str(path)) == settings.Settings()


def test_invalid_values_fall_back_per_field(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({
        "last_folder": str(tmp_path / "deleted_folder"),
        "audio_format": "exe",
        "audio_quality": "320",
    }), encoding="utf-8")
    loaded = settings.load_settings(str(path))
    assert loaded.last_folder == ""
    assert loaded.audio_format == "mp3"
    assert loaded.audio_quality == "320"   # the valid field survives


def test_wrong_types_fall_back(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"last_folder": 5, "audio_format": None, "audio_quality": 192}), encoding="utf-8")
    assert settings.load_settings(str(path)) == settings.Settings()


def test_save_is_atomic_leaves_no_temp_file(tmp_path):
    path = tmp_path / "settings.json"
    settings.save_settings(settings.Settings(), str(path))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["settings.json"]


def test_save_failure_does_not_raise(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("")
    settings.save_settings(settings.Settings(), str(blocker / "settings.json"))  # parent is a file
